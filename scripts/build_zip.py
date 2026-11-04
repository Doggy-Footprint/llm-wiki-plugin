"""release workflow가 의존성 설치 없이 python3로 실행하므로 표준 라이브러리만 쓴다."""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

SKILL_FILES = ("SKILL.md", "learn.py", "concept.md", "claude-ai.md")
TOP = "llm-wiki-add"


def build(plugin_dir: Path, out: Path) -> Path:
    plugin_dir, out = Path(plugin_dir), Path(out)
    skill = plugin_dir / "skills" / "add"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SKILL_FILES:
            data = (skill / name).read_bytes()
            if name == "SKILL.md":
                # claude.ai 계정 안에서 `add`는 너무 일반적인 이름이라 zip에서만 바꾼다.
                data = re.sub(rb"^name: add\r?$", b"name: llm-wiki-add", data, count=1, flags=re.M)
            info = zipfile.ZipInfo(f"{TOP}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, data, zipfile.ZIP_DEFLATED)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="llm-wiki-add.zip 빌드")
    p.add_argument("--out", default=None, help="기본값: <플러그인 폴더>/dist/llm-wiki-add.zip")
    args = p.parse_args(argv)
    plugin_dir = Path(__file__).resolve().parent.parent
    out = Path(args.out) if args.out else plugin_dir / "dist" / "llm-wiki-add.zip"
    print(build(plugin_dir, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
