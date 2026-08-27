"""导出 OpenAPI JSON（不启动服务、不连数据库），供 openapi-typescript 生成前端类型。

用法：python -m scripts.dump_openapi [输出路径]
"""
import json
import sys


def main() -> None:
    from app.main import app

    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
    print(f"openapi written to {out}")


if __name__ == "__main__":
    main()
