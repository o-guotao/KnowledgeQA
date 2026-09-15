"""版本与更新日志（免登录，非敏感信息）。

单一来源：根目录 VERSION 与 CHANGELOG.md；前端更新日志页与登录页版本号共用。
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, make_page, normalize_q
from app.schemas.common import Page
from app.version import get_version

router = APIRouter()

# backend/app/api/meta.py -> 上三级 = 项目根
_CHANGELOG_FILE = Path(__file__).resolve().parents[3] / "CHANGELOG.md"

_RELEASE_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\] - (?P<date>\d{4}-\d{2}-\d{2})")


def _parse_changelog(text: str) -> list[dict]:
    """解析 Keep a Changelog 格式：## [x.y.z] - date 为一版，### 为分组，- 为条目。"""
    releases: list[dict] = []
    current: dict | None = None
    group: dict | None = None
    for line in text.splitlines():
        m = _RELEASE_RE.match(line)
        if m:
            current = {"version": m["version"], "date": m["date"], "groups": []}
            releases.append(current)
            group = None
            continue
        if current is None:
            continue
        if line.startswith("### "):
            group = {"title": line[4:].strip(), "items": []}
            current["groups"].append(group)
            continue
        if line.startswith("- ") and group is not None:
            group["items"].append(line[2:].strip())
    return releases


@router.get("/meta/version")
async def meta_version() -> dict:
    return {"version": get_version()}


@router.get("/meta/changelog", response_model=Page[dict])
async def meta_changelog(q: str | None = None, params: PageParams = Depends()) -> Page[dict]:
    """更新日志：q 匹配版本号或任一条目文本，内存过滤后切片分页（解析顺序=新版本在前）。"""
    releases = (
        _parse_changelog(_CHANGELOG_FILE.read_text(encoding="utf-8"))
        if _CHANGELOG_FILE.exists()
        else []
    )
    term = normalize_q(q)
    if term is not None:
        lowered = term.lower()
        # 版本号容错：前端展示为 v0.3.0，用户常带前导 v 搜索
        version_term = lowered[1:] if lowered.startswith("v") else lowered
        releases = [
            release
            for release in releases
            if version_term in release["version"].lower()
            or any(
                lowered in item.lower()
                for group in release["groups"]
                for item in group["items"]
            )
        ]
    total = len(releases)
    return make_page(releases[params.offset : params.offset + params.page_size], total, params)
