"""
fraud-service OpenAPI 스펙을 JSON/YAML 파일로 덤프.

사용법:
  python scripts/export_openapi.py            # JSON (기본)
  python scripts/export_openapi.py --yaml     # YAML
  python scripts/export_openapi.py --out docs/openapi.yaml --yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAPI 스펙 덤프")
    parser.add_argument("--yaml", action="store_true", help="YAML 형식으로 출력")
    parser.add_argument("--out", default="", help="출력 파일 경로 (기본: stdout)")
    args = parser.parse_args()

    from app.main import app
    schema = app.openapi()

    if args.yaml:
        try:
            import yaml
            content = yaml.dump(schema, allow_unicode=True, sort_keys=False)
        except ImportError:
            print("PyYAML 미설치. pip install pyyaml", file=sys.stderr)
            sys.exit(1)
    else:
        content = json.dumps(schema, ensure_ascii=False, indent=2)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        print(f"저장됨: {out}")
    else:
        print(content)


if __name__ == "__main__":
    main()
