"""release workflow가 의존성 설치 없이 python3로 실행하므로 표준 라이브러리만 쓴다."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

# 도구별 지시는 claude.ai가 실행 때 공개 저장소에서 읽으므로 zip에는 로더 SKILL.md만 넣는다.
TOP = "llm-wiki"
ZIP_NAME = f"{TOP}.zip"


def build(plugin_dir: Path, out: Path) -> Path:
    data = (Path(plugin_dir) / "claude-ai" / "SKILL.md").read_bytes()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(f"{TOP}/SKILL.md", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        z.writestr(info, data, zipfile.ZIP_DEFLATED)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="claude.ai용 로더 skill zip 빌드")
    p.add_argument("--out", default=None, help=f"기본값: <플러그인 폴더>/dist/{ZIP_NAME}")
    args = p.parse_args(argv)
    plugin_dir = Path(__file__).resolve().parent.parent
    out = Path(args.out) if args.out else plugin_dir / "dist" / ZIP_NAME
    print(build(plugin_dir, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
