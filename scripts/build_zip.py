"""release workflow가 의존성 설치 없이 python3로 실행하므로 표준 라이브러리만 쓴다."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def loaders(plugin_dir: Path) -> list[Path]:
    return sorted(Path(plugin_dir).glob("claude-ai/*/SKILL.md"))


def build(plugin_dir: Path, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    for skill in loaders(plugin_dir):
        name = skill.parent.name
        out = out_dir / f"{name}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            info = zipfile.ZipInfo(f"{name}/SKILL.md", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, skill.read_bytes(), zipfile.ZIP_DEFLATED)
        built.append(out)
    return built


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="claude.ai용 로더 skill zip 빌드 (claude-ai/<이름>/SKILL.md마다 <이름>.zip 하나)",
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
