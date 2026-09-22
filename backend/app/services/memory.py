"""记忆系统服务（L2 会话摘要 + L3 长期记忆）。

L2 rolling summary：
- 触发：每轮对话完成后（chat.py done 收尾）投递 summarize_session 任务
- 策略：水位前留 6 条近期消息作缓冲（保证改写/指代连续性），仅当窗口外
  还有 ≥4 条消息时才值得摘要；摘要 = 旧摘要 + 新消息 → LLM 滚动压缩
- 消费：_load_history 只取水位后消息；summary 注入 system prompt

L3 memory_items：
- 触发：同上（每轮完成后投递 extract_memories 任务）
- 抽取：最近一轮 QA（+少量上文）→ LLM 判定是否含值得长期记住的
  用户事实/偏好，输出结构化条目（type/key/content）
- 落库：同 mem_key 覆盖更新（新值替换旧值），无 key 的独立成条；
  全量 ≤ 上限条数（防膨胀，超过删最旧）
- 消费：每轮检索时按当前 query 向量召回 top3 记忆，注入 system prompt

失败语义：摘要/抽取失败只丢记忆不丢对话（任务重试机制兜底）。
"""
import json
import logging
import math
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, func, select, update

from app.db import SessionLocal
from app.models.memory import MemoryItem
from app.models.message import Message
from app.models.session import Session
from app.services.deepseek import ModelCallError
from app.services.embedding import embed_texts
from app.services.model_configs import ProviderConfig

logger = logging.getLogger(__name__)

# 摘要触发条件：水位/会话开头之后还有 ≥4 条完整消息才摘要（太少不值一次 LLM 调用）
SUMMARY_MIN_MESSAGES = 4
# 摘摘要保留的近期消息缓冲（留在窗口内不进摘要，维持指代连贯）
SUMMARY_KEEP_RECENT = 6
# 单用户记忆条数上限（LRU 淘汰：按 last_used_at 删最久未用，而非创建时间——
# "老而常用"的记忆（如三个月前说的报销上限）不该被新话题挤掉）
MEMORY_MAX_ITEMS = 100
# 每轮注入 prompt 的记忆条数上限
MEMORY_RECALL_TOP = 3
# 近邻合并阈值：新记忆与已有记忆 embedding 余弦相似度 ≥ 此值视为同主题，
# 新值覆盖旧值（处理 key 提取不一致导致的矛盾并存，如"喜欢芒果"→"芒果过敏"）
MEMORY_MERGE_SIMILARITY = 0.82
# 抽取/摘要调用的独立超时
_MEMORY_TIMEOUT = 30.0


async def _chat(provider: ProviderConfig, system: str, user: str, max_tokens: int) -> tuple[str, dict | None]:
    """记忆系统的最小 LLM 调用（非流式、低温度、短输出）。"""
    timeout = httpx.Timeout(min(provider.timeout_seconds, _MEMORY_TIMEOUT), connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{provider.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json={
                "model": provider.model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "temperature": 0,
                "max_tokens": max_tokens,
            },
        )
    if response.status_code != 200:
        raise ModelCallError(f"memory provider {response.status_code}")
    data = response.json()
    return (
        (data.get("choices") or [{}])[0].get("message", {}).get("content") or "",
        data.get("usage"),
    )


def _parse_json_array(raw: str) -> list[dict]:
    """宽容解析模型输出的 JSON 数组：截取首尾大括号间内容再 loads。"""
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


# ---------------- L2：会话滚动摘要 ----------------

_SUMMARY_SYSTEM = (
    "你是对话摘要器。把【已有摘要】与【新消息】合并成一份更新后的摘要，供后续对话作为上下文。规则：\n"
    "1. 保留用户的核心意图、关键事实、决定与未决问题；丢弃寒暄与重复。\n"
    "2. 中文输出，≤200 字，紧凑的要点式（分号或换行分隔），不要输出其他解释。\n"
    "3. 旧摘要中仍然有效的信息必须保留在结果里。"
)


async def summarize_session(session_id: uuid.UUID, provider: ProviderConfig) -> bool:
    """滚动摘要：成功更新 sessions.summary 与水位返回 True；无需摘要返回 False。"""
    async with SessionLocal() as db:
        session = await db.get(Session, session_id)
        if session is None:
            return False
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.status == "complete",
                Message.role.in_(("user", "assistant")),
                Message.content != "",
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        if session.summarized_until is not None:
            stmt = stmt.where(Message.created_at > session.summarized_until)
        msgs = (await db.execute(stmt)).scalars().all()

        # 摘要水位推进：只摘要“窗口外”部分（保留最近 KEEP 条不进摘要）
        to_summarize = msgs[: len(msgs) - SUMMARY_KEEP_RECENT] if len(msgs) > SUMMARY_KEEP_RECENT else []
        if len(to_summarize) < SUMMARY_MIN_MESSAGES:
            return False

        lines = []
        if session.summary:
            lines.append(f"【已有摘要】\n{session.summary}")
        lines.append("【新消息】")
        for m in to_summarize:
            who = "用户" if m.role == "user" else "助手"
            text = m.content[:400]  # 单条截断，控制 token
            lines.append(f"{who}：{text}")
        raw, _usage = await _chat(
            provider, _SUMMARY_SYSTEM, "\n".join(lines), max_tokens=400,
        )
        summary = raw.strip()
        if not summary:
            return False

        waterline = to_summarize[-1].created_at
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(summary=summary[:2000], summarized_until=waterline)
        )
        await db.commit()
        logger.info(
            "session summary updated",
            extra={"event": "session_summary", "extra": {"session_id": str(session_id), "msgs": len(to_summarize)}},
        )
        return True


# ---------------- L3：长期记忆抽取与召回 ----------------

_EXTRACT_SYSTEM = (
    "从对话中识别值得跨会话长期记住的【用户】事实或偏好。规则：\n"
    "1. 只记用户自己陈述的信息（背景、偏好、口径、约束），不记助手的回答内容。\n"
    "2. 每条给一个简短且稳定的主题 key（如“报销上限”“食物偏好-芒果”），"
    "同一主题必须始终用同一个 key 表述，同主题只输出最新值——用户改口时输出新值覆盖旧值。\n"
    "3. 知识库里已有的通用知识、临时性上下文（本会话才有效的指代）不要记。\n"
    "4. 没有值得记的就输出 []。只输出一行 JSON 数组，不要解释：\n"
    '[{"type": "preference|fact", "key": "主题或null", "content": "一句话"}]'
)


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def extract_memories(session_id: uuid.UUID, provider: ProviderConfig) -> int:
    """从最近一轮 QA 抽取记忆条目并落库（同 key 覆盖更新）。返回新增/更新条数。"""
    async with SessionLocal() as db:
        msgs = (
            await db.execute(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.status == "complete",
                    Message.role.in_(("user", "assistant")),
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(2)  # 最近一轮 QA
            )
        ).scalars().all()
        if len(msgs) < 2:
            return 0
        qa = list(reversed(msgs))  # 时间正序：user → assistant
        user_msg = qa[0]
        if user_msg.role != "user":
            return 0

        raw, _usage = await _chat(
            provider,
            _EXTRACT_SYSTEM,
            f"用户：{user_msg.content[:600]}\n助手：{qa[1].content[:600]}",
            max_tokens=300,
        )
        items = _parse_json_array(raw)
        saved = 0
        existing = (await db.execute(
            select(MemoryItem).where(MemoryItem.user_id == user_msg.user_id)
        )).scalars().all()
        for it in items:
            if not isinstance(it, dict):
                continue
            content = (it.get("content") or "").strip()
            if not content or len(content) > 500:
                continue
            mtype = it.get("type") if it.get("type") in ("preference", "fact") else "fact"
            key = (it.get("key") or None) if isinstance(it.get("key"), str) else None
            if key:
                key = key.strip()[:128] or None

            vec = (await embed_texts([content]))[0]

            # 覆盖目标定位（三重判定，命中即新值替换旧值）：
            # 1) 同 mem_key 精确匹配（key 提取一致时的正常覆盖路径）
            # 2) 无 key 条目与任意已有条目近邻（无 key 的碎片归并到同主题）
            # 3) 已有条目与新条目 embedding 近邻（key 提取不一致时的语义合并，
            #    处理"喜欢芒果"→"芒果过敏"这类 key 漂移导致的矛盾并存）
            victim_id: uuid.UUID | None = None
            if key is not None:
                victim_id = next((r.id for r in existing if r.mem_key == key), None)
            if victim_id is None:
                near = next(
                    (r for r in existing if _cos(vec, r.embedding or []) >= MEMORY_MERGE_SIMILARITY),
                    None,
                )
                if near is not None:
                    victim_id = near.id
                    logger.info(
                        "memory merged by semantic similarity",
                        extra={
                            "event": "memory_merge",
                            "extra": {"old_key": near.mem_key, "new_key": key, "similarity": round(_cos(vec, near.embedding or []), 3)},
                        },
                    )
            if victim_id is not None:
                await db.execute(delete(MemoryItem).where(MemoryItem.id == victim_id))
                existing = [r for r in existing if r.id != victim_id]

            db.add(MemoryItem(
                user_id=user_msg.user_id, type=mtype, mem_key=key, content=content,
                session_id=session_id, source_message_id=user_msg.id, embedding=vec,
            ))
            saved += 1
        if saved:
            # 容量控制：LRU 淘汰——按 last_used_at 删最久未被召回命中的条目。
            # （新插入行 last_used_at=now 不会立刻被淘汰；"老而常用"的记忆安全）
            count = (await db.execute(
                select(func.count(MemoryItem.id)).where(MemoryItem.user_id == user_msg.user_id)
            )).scalar_one()
            if count > MEMORY_MAX_ITEMS:
                lru = (await db.execute(
                    select(MemoryItem.id)
                    .where(MemoryItem.user_id == user_msg.user_id)
                    .order_by(MemoryItem.last_used_at.asc())
                    .limit(count - MEMORY_MAX_ITEMS)
                )).scalars().all()
                await db.execute(delete(MemoryItem).where(MemoryItem.id.in_(lru)))
                logger.info(
                    "memory lru evicted",
                    extra={"event": "memory_evict", "extra": {"count": len(lru)}},
                )
            await db.commit()
            logger.info(
                "memories extracted",
                extra={"event": "memory_extract", "extra": {"session_id": str(session_id), "saved": saved}},
            )
        return saved


async def recall_memories(
    db, user_id: uuid.UUID, query_embedding: list[float], top: int = MEMORY_RECALL_TOP
) -> list[MemoryItem]:
    """按当前问题向量召回该用户的长期记忆（余弦相似 top-N）。

    命中即刷新 last_used_at（LRU 淘汰的"使用"信号——被召回的记忆不会因
    创建得早而被容量淘汰）。失败降级空列表，不影响主流程。
    """
    try:
        stmt = select(MemoryItem).where(MemoryItem.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return []
        scored = sorted(rows, key=lambda r: _cos(query_embedding, r.embedding or []), reverse=True)
        hits = [r for r in scored[:top] if r.content]
        if hits:
            now = datetime.now(timezone.utc)
            await db.execute(
                update(MemoryItem)
                .where(MemoryItem.id.in_([h.id for h in hits]))
                .values(last_used_at=now)
            )
            await db.commit()
        return hits
    except Exception as exc:
        logger.warning("memory recall degraded: %s", exc, extra={"event": "memory_recall_degraded"})
        return []


def render_memories(items: list[MemoryItem]) -> str:
    """记忆条目渲染为 system prompt 片段。"""
    if not items:
        return ""
    lines = ["用户长期记忆（历史对话沉淀，回答时可参考）："]
    for r in items:
        prefix = "偏好" if r.type == "preference" else "事实"
        key = f"（{r.mem_key}）" if r.mem_key else ""
        lines.append(f"- [{prefix}]{key} {r.content}")
    return "\n".join(lines)
