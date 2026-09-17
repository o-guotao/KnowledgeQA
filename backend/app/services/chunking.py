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


def _extract_docx(data: bytes) -> str:
    """docx：段落 + 表格（逐行 tab 拼接单元格），保持阅读顺序。"""
    import docx  # 懒加载

    document = docx.Document(io.BytesIO(data))
    parts: list[str] = []
    # 按文档体顺序遍历（段落与表格交错），比先段落后表格更保序
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append("\t".join(cells))
    return "\n".join(parts).strip()


def _iter_block_items(parent):
    """按顺序产出 docx 文档体中的段落与表格（python-docx 未提供官方 API）。"""
    from docx.document import Document as _Document
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = parent.element.body if isinstance(parent, _Document) else parent._element
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _extract_xlsx(data: bytes) -> str:
    """xlsx：逐 sheet 提取，每行 tab 拼接，sheet 间以标题分隔保留表格语义。"""
    import openpyxl  # 懒加载

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        parts: list[str] = []
        for ws in wb.worksheets:
            lines: list[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [("" if v is None else str(v)).strip() for v in row]
                if any(cells):
                    lines.append("\t".join(cells))
            if lines:
                parts.append(f"## Sheet: {ws.title}\n" + "\n".join(lines))
        return "\n\n".join(parts).strip()
    finally:
        # read_only 模式也需显式关闭，释放打开的 zip 句柄
        wb.close()


def _in_any_bbox(word: dict, bboxes: list) -> bool:
    """词是否完全落在任一表格区域内（页内正文文字通常在表格框外）。"""
    for bx0, btop, bx1, bbottom in bboxes:
        if (
            word["x0"] >= bx0
            and word["x1"] <= bx1
            and word["top"] >= btop
            and word["bottom"] <= bbottom
        ):
            return True
    return False


def _words_to_text(words: list[dict]) -> str:
    """词按 top 聚成行、行内按 x 排序，还原页面正文（表格外区域）。"""
    if not words:
        return ""
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[str] = []
    cur: list[str] = []
    cur_top: float | None = None
    for w in ordered:
        if cur_top is None or abs(w["top"] - cur_top) <= 3:
            if cur_top is None:
                cur_top = w["top"]
            cur.append(w["text"])
        else:
            lines.append(" ".join(cur))
            cur = [w["text"]]
            cur_top = w["top"]
    lines.append(" ".join(cur))
    return "\n".join(lines)


def _rows_to_markdown(rows: list[list]) -> str:
    """表格行列表转 Markdown 管道表（首行为表头），保留行列语义便于检索。"""
    if not rows or not any(any(c is not None and str(c).strip() for c in r) for r in rows):
        return ""

    def cell(v) -> str:
        s = "" if v is None else str(v).replace("\n", " ").replace("|", "\\|").strip()
        return s if s else " "

    width = max(len(r) for r in rows)
    lines = ["| " + " | ".join(cell(c) for c in rows[0]) + " |"]
    lines.append("|" + " --- |" * width)
    for r in rows[1:]:
        padded = list(r) + [None] * (width - len(r))
        lines.append("| " + " | ".join(cell(c) for c in padded) + " |")
    return "\n".join(lines)


def _extract_pdf(data: bytes) -> str:
    """PDF：pdfplumber 逐页提取正文 + 表格。

    - 表格（含矢量线框的表格）转 Markdown 管道表，保留行列对应关系；
    - 正文文字排除表格区域后按行还原，避免表格内容在正文里重复出现；
    - 页与页之间空行分隔，表格紧随其所在位置之后。
    """
    import pdfplumber  # 懒加载

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            bboxes = [t.bbox for t in tables]
            words = [w for w in page.extract_words() if not _in_any_bbox(w, bboxes)]
            text = _words_to_text(words)
            if text.strip():
                parts.append(text.strip())
            for t in tables:
                md = _rows_to_markdown(t.extract() or [])
                if md:
                    parts.append(md)
    return "\n\n".join(parts).strip()


def pdf_has_text(data: bytes, max_pages: int = 3) -> bool:
    """上传探测：只看前几页是否存在文字层（纯图片/扫描 PDF 每页都没有文字）。

    pdfplumber 全量提取比 pypdf 慢，探测用它避免大 PDF 拖慢上传请求；
    探测不到而后续页有文字的极端混合 PDF 会由 worker 落入 failed 并可重试。
    """
    import pdfplumber  # 懒加载

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:max_pages]:
            if page.extract_words():
                return True
    return False


def extract_text(filename: str, data: bytes) -> str:
    """按扩展名提取纯文本。支持 .txt/.md/.pdf/.docx/.xlsx（PDF 表格结构化为 Markdown）。"""
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    if name.endswith(".xlsx"):
        return _extract_xlsx(data)
    if name.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace").strip()
    raise ValueError(f"不支持的文件类型：{filename}（仅支持 .txt/.md/.pdf/.docx/.xlsx/图片）")


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
