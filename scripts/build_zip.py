"""release workflow가 의존성 설치 없이 python3로 실행하므로 표준 라이브러리만 쓴다."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

NAME = "llm-wiki"
INCLUDE = [".claude-plugin/plugin.json", "skills", "README.md", "LICENSE"]
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc"}
SKIP_NAMES = {".DS_Store"}


def plugin_files(plugin_dir: Path) -> list[str]:
    plugin_dir = Path(plugin_dir)
    files = []
    for entry in INCLUDE:
        path = plugin_dir / entry
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for p in candidates:
            rel = p.relative_to(plugin_dir)
            if SKIP_DIRS & set(rel.parts[:-1]) or p.suffix in SKIP_SUFFIXES or p.name in SKIP_NAMES:
                continue
            files.append(rel.as_posix())
    return sorted(files)


def build(plugin_dir: Path, out_dir: Path) -> list[Path]:
    plugin_dir = Path(plugin_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in plugin_files(plugin_dir):
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, (plugin_dir / rel).read_bytes(), zipfile.ZIP_DEFLATED)
    return [out]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="claude.ai Customize > Plugins > Upload plugin용 플러그인 zip 빌드 (dist/llm-wiki.zip)",
                                allow_abbrev=False)
    p.add_argument("--out-dir", default=None, help="기본값: <플러그인 폴더>/dist")
    args = p.parse_args(argv)
    plugin_dir = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out_dir) if args.out_dir else plugin_dir / "dist"
    for path in build(plugin_dir, out_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
