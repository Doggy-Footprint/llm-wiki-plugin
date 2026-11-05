"""release workflow가 의존성 설치 없이 python3로 실행하므로 표준 라이브러리만 쓴다."""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

# 이름: (zip 최상위 폴더, SKILL.md의 name 치환 대상, [(zip 안 파일 이름, skills/ 아래 원본 경로)])
# claude.ai 계정 안에서 `add`·`quiz`는 너무 일반적인 이름이라 zip에서만 바꾼다.
SKILLS: dict[str, tuple[str, str | None, list[tuple[str, str]]]] = {
    "add": ("wiki-add", "add", [(n, f"add/{n}") for n in ("SKILL.md", "learn.py", "concept.md", "claude-ai.md")]),
    "wiki-learn": ("wiki-learn", None, [
        ("SKILL.md", "wiki-learn/SKILL.md"),
        ("claude-ai.md", "wiki-learn/claude-ai.md"),
        ("add.md", "add/SKILL.md"),
        ("add-claude-ai.md", "add/claude-ai.md"),
        ("learn.py", "add/learn.py"),
        ("concept.md", "add/concept.md"),
    ]),
    "quiz": ("wiki-quiz", "quiz", [(n, f"quiz/{n}") for n in ("SKILL.md", "claude-ai.md", "quiz.py")]),
}
ZIP_NAMES = {"add": "wiki-add.zip", "wiki-learn": "wiki-learn.zip", "quiz": "wiki-quiz.zip"}


def build(plugin_dir: Path, out: Path, skill: str = "add") -> Path:
    if skill not in SKILLS:
        raise ValueError(f"알 수 없는 skill: {skill!r} (add, wiki-learn, quiz 중 하나)")
    plugin_dir, out = Path(plugin_dir), Path(out)
    top, rename, files = SKILLS[skill]
    skills_dir = plugin_dir / "skills"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in files:
            data = (skills_dir / src).read_bytes()
            if name == "SKILL.md" and rename:
                data = re.sub(rb"^name: " + rename.encode() + rb"\r?$", b"name: " + top.encode(), data,
                              count=1, flags=re.M)
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, data, zipfile.ZIP_DEFLATED)
    return out


def build_all(plugin_dir: Path, out_dir: Path) -> list[Path]:
    return [build(plugin_dir, Path(out_dir) / ZIP_NAMES[s], s) for s in SKILLS]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="claude.ai용 skill zip 빌드")
    p.add_argument("--out", default=None, help="기본값: <플러그인 폴더>/dist/<zip 이름>")
    p.add_argument("--skill", choices=list(SKILLS), default="add")
    p.add_argument("--all", action="store_true", help="세 zip을 모두 만든다 (기본 출력 폴더: <플러그인 폴더>/dist)")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)
    plugin_dir = Path(__file__).resolve().parent.parent
    if args.all:
        out_dir = Path(args.out_dir) if args.out_dir else plugin_dir / "dist"
        for path in build_all(plugin_dir, out_dir):
            print(path)
        return 0
    out = Path(args.out) if args.out else plugin_dir / "dist" / ZIP_NAMES[args.skill]
    print(build(plugin_dir, out, args.skill))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
