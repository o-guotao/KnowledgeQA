"""RAG 评测：对运行中的后端执行 30 条问句，输出逐条明细与汇总指标。

用法（需先 docker compose up，并配置 DEEPSEEK_API_KEY）：
    python -m eval.run_eval --tag baseline                 # 上传文档 + 全量评测
    python -m eval.run_eval --tag tuned --skip-upload      # 同一知识库复测（调切分后需重建，见 README）
    python -m eval.run_eval --compare baseline tuned       # 输出两组对比 CSV

指标：
    recall_hit  — SSE citation 事件的来源文档集合包含 gold_doc
    answer_hit  — 回答文本命中任一 gold_keyword
"""
import argparse
import json
import time
import uuid
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"


class EvalClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(180.0, connect=10.0))
        resp = self.client.post("/api/auth/login", json={"username": username, "password": password})
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    def upload_docs(self, docs_dir: Path) -> None:
        for path in sorted(docs_dir.iterdir()):
            if path.suffix.lower() not in (".md", ".txt", ".pdf"):
                continue
            with path.open("rb") as f:
                resp = self.client.post("/api/documents", files={"file": (path.name, f)})
            resp.raise_for_status()
            print(f"[upload] {path.name}")

    def wait_ready(self, timeout_s: float = 600.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            docs = self.client.get("/api/documents").json()
            if docs and all(d["status"] in ("ready", "failed") for d in docs):
                failed = [d["filename"] for d in docs if d["status"] == "failed"]
                if failed:
                    raise RuntimeError(f"文档入库失败：{failed}")
                print(f"[ingest] {len(docs)} 篇文档全部 ready")
                return
            time.sleep(3)
        raise TimeoutError("等待文档入库超时")

    def ask(self, session_id: str, question: str) -> dict:
        """消费 SSE 流，返回 {answer, cited_docs, error, latency_s}。"""
        started = time.monotonic()
        answer_parts: list[str] = []
        cited_docs: set[str] = set()
        error: str | None = None
        with self.client.stream(
            "POST", "/api/chat/stream", json={"session_id": session_id, "content": question}
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                event = json.loads(data)
                etype = event.get("type")
                if etype == "delta":
                    answer_parts.append(event["content"])
                elif etype == "citation":
                    cited_docs.add(event["document_name"])
                elif etype == "error":
                    error = event["message"]
        return {
            "answer": "".join(answer_parts),
            "cited_docs": sorted(cited_docs),
            "error": error,
            "latency_s": round(time.monotonic() - started, 2),
        }

    def new_session(self) -> str:
        resp = self.client.post("/api/sessions", json={"title": f"eval-{uuid.uuid4().hex[:8]}"})
        resp.raise_for_status()
        return resp.json()["id"]


def run(tag: str, base_url: str, username: str, password: str, skip_upload: bool) -> None:
    client = EvalClient(base_url, username, password)
    if not skip_upload:
        client.upload_docs(BASE_DIR / "sample_docs")
        client.wait_ready()

    questions = [
        json.loads(line)
        for line in (BASE_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    RESULTS_DIR.mkdir(exist_ok=True)
    detail_path = RESULTS_DIR / f"eval_{tag}.jsonl"
    summary_path = RESULTS_DIR / f"eval_{tag}_summary.json"

    recall_hits = answer_hits = 0
    latencies: list[float] = []
    with detail_path.open("w", encoding="utf-8") as out:
        for i, item in enumerate(questions, 1):
            session_id = client.new_session()  # 每题独立会话，排除上下文干扰
            result = client.ask(session_id, item["q"])
            recall_hit = item["gold_doc"] in result["cited_docs"]
            answer_hit = any(kw in result["answer"] for kw in item["gold_keywords"])
            recall_hits += recall_hit
            answer_hits += answer_hit
            latencies.append(result["latency_s"])
            record = {
                "i": i, "q": item["q"], "gold_doc": item["gold_doc"],
                "cited_docs": result["cited_docs"], "recall_hit": recall_hit,
                "answer_hit": answer_hit, "answer": result["answer"][:500],
                "error": result["error"], "latency_s": result["latency_s"],
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[{i:02d}/{len(questions)}] recall={recall_hit} answer={answer_hit} {item['q'][:24]}")

    n = len(questions)
    summary = {
        "tag": tag,
        "total": n,
        "recall_hit_rate": round(recall_hits / n, 4),
        "answer_hit_rate": round(answer_hits / n, 4),
        "avg_latency_s": round(sum(latencies) / n, 2),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[summary] {json.dumps(summary, ensure_ascii=False)}")


def compare(tag_a: str, tag_b: str) -> None:
    def load(tag: str) -> tuple[dict, list[dict]]:
        summary = json.loads((RESULTS_DIR / f"eval_{tag}_summary.json").read_text(encoding="utf-8"))
        details = [
            json.loads(line)
            for line in (RESULTS_DIR / f"eval_{tag}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return summary, details

    sum_a, det_a = load(tag_a)
    sum_b, det_b = load(tag_b)
    det_b_by_q = {d["q"]: d for d in det_b}

    out_path = RESULTS_DIR / f"compare_{tag_a}_vs_{tag_b}.csv"
    lines = ["q,gold_doc,recall_a,recall_b,answer_a,answer_b"]
    for da in det_a:
        db = det_b_by_q.get(da["q"], {})
        lines.append(
            f"\"{da['q']}\",{da['gold_doc']},{int(da['recall_hit'])},{int(bool(db.get('recall_hit')))},"
            f"{int(da['answer_hit'])},{int(bool(db.get('answer_hit')))}"
        )
    lines.append(
        f"\"汇总（命中率）\",,{sum_a['recall_hit_rate']},{sum_b['recall_hit_rate']},"
        f"{sum_a['answer_hit_rate']},{sum_b['answer_hit_rate']}"
    )
    out_path.write_text("\n".join(lines), encoding="utf-8-sig")
    print(f"[compare] written to {out_path}")
    print(f"  recall : {sum_a['recall_hit_rate']:.2%} -> {sum_b['recall_hit_rate']:.2%}")
    print(f"  answer : {sum_a['answer_hit_rate']:.2%} -> {sum_b['answer_hit_rate']:.2%}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo1234")
    parser.add_argument("--tag", help="本次评测标签（如 baseline / tuned）")
    parser.add_argument("--skip-upload", action="store_true", help="跳过上传（复用已入库知识库）")
    parser.add_argument("--compare", nargs=2, metavar=("TAG_A", "TAG_B"), help="对比两组评测结果")
    args = parser.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1])
    elif args.tag:
        run(args.tag, args.base_url, args.username, args.password, args.skip_upload)
    else:
        parser.error("必须指定 --tag 或 --compare")


if __name__ == "__main__":
    main()
