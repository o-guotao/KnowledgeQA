"""文档文本提取与切分。

切分策略：优先按段落/句子边界切，保证 chunk 语义完整；
chunk_size/overlap 可配，评测时调整这两参数观察指标升降。
"""
import io
import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"[。！？!?；;\n]")
_HARD_BREAK = re.compile(r"\n{2,}|\r\n{2,}")


@dataclass
class ChunkData:
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int


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
