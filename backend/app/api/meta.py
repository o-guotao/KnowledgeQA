"""版本与更新日志（免登录，非敏感信息）。

单一来源：根目录 VERSION 与 CHANGELOG.md；前端更新日志页与登录页版本号共用。
"""
import re
from pathlib import Path

from fastapi import APIRouter

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


@router.get("/meta/changelog")
async def meta_changelog() -> list[dict]:
    if not _CHANGELOG_FILE.exists():
        return []
    return _parse_changelog(_CHANGELOG_FILE.read_text(encoding="utf-8"))
