"""应用版本号：单一来源为项目根 VERSION 文件。

前后端版本号保持一致：后端直接读取；前端经 /api/meta/version 展示，
package.json 在发版时同步 bump（仅作构建元数据）。
"""
from functools import lru_cache
from pathlib import Path

# backend/app/version.py -> 上两级 = 项目根
_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


@lru_cache
def get_version() -> str:
    return _VERSION_FILE.read_text(encoding="utf-8").strip()
