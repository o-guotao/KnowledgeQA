"""应用版本号：单一来源为项目根 VERSION 文件。

前后端版本号保持一致：后端直接读取；前端经 /api/meta/version 展示，
package.json 在发版时同步 bump（仅作构建元数据）。

读取顺序：VERSION 文件（本地开发=项目根；容器= compose 挂载到 /VERSION）
→ APP_VERSION 环境变量 → "0.0.0-unknown" 兜底。版本文件缺失不允许导致启动失败。
"""
import os
from functools import lru_cache
from pathlib import Path

# backend/app/version.py -> 上两级 = 项目根（容器内 /app/app/version.py -> /VERSION，由 compose 挂载）
_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


@lru_cache
def get_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return os.getenv("APP_VERSION", "0.0.0-unknown")
