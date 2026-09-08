"""文档文本提取与切分。

切分策略：
- window：滑动窗口，按段落/句子边界切，保证 chunk 语义完整
- semantic：语义分块，按 Markdown 标题层级切父块（上下文完整），
  父块内再切小块（child，用于 embedding 召回）——小块召回 + 大块上下文
chunk_size/overlap 可配，评测时调整这两参数观察指标升降。
"""
import io
import re
from dataclasses import dataclass, field

_SENTENCE_END = re.compile(r"[。！？!?；;\n]")
_HARD_BREAK = re.compile(r"\n{2,}|\r\n{2,}")
_HEADING = re.compile(r"^(#{1,6})\s+\S", re.MULTILINE)


@dataclass
class ChunkData:
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int


@dataclass
class SemanticBlock:
    """语义分块结果：一个父块（上下文）+ 其下多个子块（用于 embedding 召回）。"""
    parent_content: str
    children: list[ChunkData] = field(default_factory=list)


def extract_text(filename: str, data: bytes) -> str:
    """按扩展名提取纯文本。支持 .txt/.md/.pdf。"""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader  # 懒加载

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    if name.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace").strip()
    raise ValueError(f"不支持的文件类型：{filename}（仅支持 .txt/.md/.pdf）")


def split_text(text: str, chunk_size: int, overlap: int) -> list[ChunkData]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正数")
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")

    chunks: list[ChunkData] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # 在窗口后 1/3 范围内寻找最近的句子/段落边界，避免切断语义
            window = text[start:end]
            cut = -1
            for m in _SENTENCE_END.finditer(window):
                if m.start() >= chunk_size * 2 // 3:
                    cut = m.end()
            if cut > 0:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            real_start = start + (len(text[start:end]) - len(text[start:end].lstrip()))
            chunks.append(
                ChunkData(
                    chunk_index=len(chunks),
                    content=piece,
                    start_offset=real_start,
                    end_offset=end,
                )
            )
        if end >= n:
            break
        start = end - overlap
        # 避免 overlap 回退到空白中造成微小推进死循环
        while start < n and start > 0 and text[start].isspace():
            start += 1
    return chunks


def _split_by_headings(text: str) -> list[str]:
    """按 Markdown 标题切分为大段（保留标题）。无标题时返回全文为单段。"""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [text] if text.strip() else []
    sections: list[str] = []
    # 标题前的内容（若有）
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        sections.append(text[: matches[0].start()])
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(text[m.start():end])
    return [s for s in sections if s.strip()]


def split_semantic(text: str, child_size: int, child_overlap: int, parent_max: int = 1200) -> list[SemanticBlock]:
    """语义分块：按标题层级切父块，父块内再切小块（child 用于 embedding 召回）。

    - 父块提供完整上下文（注入 prompt），过大父块会再按标题/窗口拆分
    - 子块是 embedding 与召回的粒度，召回后回取父块上下文
    """
    blocks: list[SemanticBlock] = []
    sections = _split_by_headings(text)
    for section in sections:
        # 父块过大：先尝试作为单父块，内容超 parent_max 时按窗口切成多个父块
        if len(section) <= parent_max:
            parents = [section]
        else:
            parents = [c.content for c in split_text(section, parent_max, parent_max // 6)]
        for parent in parents:
            parent = parent.strip()
            if not parent:
                continue
            children = split_text(parent, child_size, child_overlap)
            blocks.append(SemanticBlock(parent_content=parent, children=children))
    return blocks
