# /// script
# requires-python = ">=3.11"
# dependencies = ["markitdown[pdf,docx,pptx]==0.1.9"]
# ///
"""표준 라이브러리만 쓰고 markitdown은 fetch 안에서만 import한다. claude.ai 코드 실행 환경처럼 의존성을 설치할 수 없는 곳에서도 env·result가 돌아야 한다."""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path

SOLO: dict[int, str] = {0: "전구조적", 1: "단일구조적", 2: "다중구조적", 3: "관계적", 4: "확장추상적"}
OUTLINE_THRESHOLD: int = 20000
ROLLOVER_HOUR = 5
MANIFEST_FIELDS = ["raw_path", "original_name", "sha256", "archived_at", "extracted_to"]
STUDY_HEADING = "## 공부 (study/)"
CLOUD_PUSH_VALUES = ("default-branch", "session-branch")
RESULT_SECTIONS = ("내가 정리한 것", "보충 (LLM)", "연결", "다음 학습")
LIST_SECTIONS = ("연결", "다음 학습")
LINK_PLACEHOLDER = "- [[관련 개념]] — 어떤 관계인지"

INDEX_TEXT = (
    "# Index\n\n"
    "위키를 다룰 때 가장 먼저 읽는 목차. 페이지마다 한 줄: `- [[제목]] — 한 줄 설명`\n\n"
    "편집 규칙:\n"
    "- 파일명 = 페이지 제목, 링크는 `[[제목]]`. 새 페이지는 `templates/`에서 시작하고 여기에 한 줄 추가한다.\n"
    "- frontmatter는 `key: value`, `key: [a, b]`만 쓴다. 중첩은 쓰지 않는다.\n"
    "- 사용자·자료에서 온 내용과 LLM 보충은 섹션을 나눈다.\n"
    "- `level`(SOLO 0~4)과 `## 이해 기록`·`## 오해와 교정`은 `/wiki-add`(`learn.py`)만 쓴다.\n"
    "- 무엇이든 바꾸면 `wiki/log.md`에 한 줄을 덧붙인다.\n\n"
    f"{STUDY_HEADING}\n"
)
LOG_TEXT = "# Log\n\n기록을 덧붙이기만 한다. 형식: `- YYYY-MM-DD [작업] 내용`\n\n"


class LearnError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def parse_date(value: str, now: datetime.datetime | None = None) -> datetime.date:
    if value in ("today", "yesterday"):
        now = now or _now()
        today = now.date() - datetime.timedelta(days=1 if now.hour < ROLLOVER_HOUR else 0)
        return today - datetime.timedelta(days=1) if value == "yesterday" else today
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise LearnError(f"날짜 형식 오류(YYYY-MM-DD, today, yesterday): {_show(value)}")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise LearnError(f"없는 날짜: {_show(value)}") from None


def _slugify(text: str) -> str:
    return re.sub(r"[^\w가-힣-]+", "-", text).strip("-") or "item"


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _show(value: object) -> str:
    """오류 메시지용: 제어 문자만 이스케이프하고 나머지(역슬래시 포함)는 그대로 둔다."""
    return "".join(
        c if unicodedata.category(c) != "Cc" else {"\t": "\\t", "\n": "\\n", "\r": "\\r"}.get(c, f"\\x{ord(c):02x}")
        for c in str(value)
    )


def _check_title(title: str) -> None:
    bad = (
        not isinstance(title, str)
        or not title.strip()
        or "/" in title
        or "\\" in title
        or title.startswith(".")
        or len(title) > 100
        or any(unicodedata.category(c) == "Cc" for c in title)
    )
    if bad:
        raise LearnError(f"잘못된 제목: '{_show(title)}'")


def _check_level(level: int) -> None:
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 4:
        raise LearnError(f"level은 0~4 정수여야 함: '{_show(level)}'")


def _write_all(writes: Sequence[tuple[Path, bytes]]) -> None:
    """검증이 끝난 내용을 한꺼번에 쓰고, 중간에 실패하면 이전 상태로 되돌린다."""
    undo: list[tuple[Path, bytes | None]] = []
    made: list[Path] = []
    try:
        for path, data in writes:
            missing = []
            d = path.parent
            while not d.exists():
                missing.append(d)
                d = d.parent
            path.parent.mkdir(parents=True, exist_ok=True)
            made.extend(reversed(missing))
            undo.append((path, path.read_bytes() if path.exists() else None))
            path.write_bytes(data)
    except BaseException:
        for path, old in reversed(undo):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        for d in reversed(made):
            try:
                d.rmdir()
            except OSError:
                pass
        raise


# 위키 저장소의 scripts/_lib.py frontmatter()가 같은 값으로 읽어야 한다.

def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _parse_fm(text: str) -> dict:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict = {}
    last_key = None
    for line in text[4:end].splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") and last_key is not None:
            if not isinstance(meta[last_key], list):
                meta[last_key] = []
            meta[last_key].append(_unquote(s[2:]))
            continue
        if ":" not in line or line[0].isspace():
            continue
        k, v = line.split(":", 1)
        v = v.split(" #", 1)[0].strip()
        if v.startswith("[") and not v.startswith("[[") and v.endswith("]"):
            meta[k.strip()] = [_unquote(x) for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = _unquote(v)
        last_key = k.strip()
    return meta


def _split_lines(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=\n)", text) if p]


def _body(line: str) -> str:
    return line.rstrip("\r\n")


def _eol(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _fm_end(lines: list[str]) -> int | None:
    if not lines or _body(lines[0]) != "---":
        return None
    for i in range(1, len(lines)):
        if _body(lines[i]).rstrip() == "---":
            return i
    return None


def _body_start(lines: list[str]) -> int:
    end = _fm_end(lines)
    return 0 if end is None else end + 1


def _find_key(lines: list[str], end: int, key: str) -> int | None:
    pat = re.compile(rf"^{re.escape(key)}[ \t]*:")
    for i in range(1, end):
        if pat.match(lines[i]):
            return i
    return None


def _line_value(line: str) -> str:
    return _unquote(_body(line).split(":", 1)[1].split(" #", 1)[0])


def _set_scalar(lines: list[str], key: str, value: str, nl: str) -> None:
    end = _fm_end(lines)
    i = _find_key(lines, end, key)
    if i is None:
        lines.insert(end, f"{key}: {value}{nl}")
    elif _line_value(lines[i]) != value:
        lines[i] = f"{key}: {value}{_eol(lines[i])}"


def _add_sources(lines: list[str], new: Sequence[str], nl: str) -> None:
    if not new:
        return
    end = _fm_end(lines)
    i = _find_key(lines, end, "sources")
    if i is None:
        lines.insert(end, f"sources: [{', '.join(new)}]{nl}")
        return
    val = _body(lines[i]).split(":", 1)[1].split(" #", 1)[0].strip()
    if val.startswith("[") and not val.startswith("[[") and val.endswith("]"):
        items = [x.strip() for x in val[1:-1].split(",") if x.strip()]
    elif val:
        items = [val]
    else:
        j, indent, have = i + 1, "", set()
        while j < end and lines[j].strip().startswith("- "):
            indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
            have.add(_unquote(lines[j].strip()[2:]))
            j += 1
        add = [s for s in new if s not in have]
        lines[j:j] = [f"{indent}- {s}{nl}" for s in add]
        return
    have = {_unquote(x) for x in items}
    add = [s for s in new if s not in have]
    if add:
        lines[i] = f"sources: [{', '.join(items + add)}]{_eol(lines[i])}"


_H_RE = re.compile(r"^#{1,2} ")


def _section(lines: list[str], heading: str) -> tuple[int, int] | None:
    for i in range(_body_start(lines), len(lines)):
        if _body(lines[i]).rstrip() == heading:
            e = i + 1
            while e < len(lines) and not _H_RE.match(lines[e]):
                e += 1
            return i, e
    return None


def _last_nonblank(lines: list[str], h: int, e: int) -> int:
    j = e - 1
    while j > h and not lines[j].strip():
        j -= 1
    return j


def _insert(lines: list[str], pos: int, bodies: list[str], nl: str) -> None:
    if not bodies:
        return
    tail = pos == len(lines) and bool(lines) and not lines[-1].endswith("\n")
    if tail:
        lines[-1] += nl
    new = [b + nl for b in bodies]
    if tail:
        new[-1] = bodies[-1]
    lines[pos:pos] = new


def _ensure_section(lines: list[str], heading: str, anchors: Sequence[str], nl: str) -> tuple[int, int]:
    found = _section(lines, heading)
    if found:
        return found
    idx = None
    for a in anchors:
        s = _section(lines, a)
        if s:
            idx = s[0]
            break
    if idx is None:
        pre = [""] if lines and lines[-1].strip() else []
        _insert(lines, len(lines), pre + [heading], nl)
    else:
        pre = [""] if idx > 0 and lines[idx - 1].strip() else []
        _insert(lines, idx, pre + [heading, ""], nl)
    return _section(lines, heading)


def _append_to_section(lines, heading, bodies, anchors, nl, blank_before=False) -> None:
    h, e = _ensure_section(lines, heading, anchors, nl)
    j = _last_nonblank(lines, h, e)
    pre = [""] if blank_before and j > h else []
    _insert(lines, j + 1, pre + list(bodies), nl)


def _section_bodies(lines: list[str], heading: str) -> list[str]:
    s = _section(lines, heading)
    return [] if s is None else [_body(l).rstrip() for l in lines[s[0] + 1 : s[1]]]


def _contains_block(have: list[str], block: list[str]) -> bool:
    n = len(block)
    return any(have[i : i + n] == block for i in range(len(have) - n + 1))


def _manifest_path(root: Path) -> Path:
    return root / "raw" / "MANIFEST.csv"


def _read_manifest(root: Path) -> tuple[list[list[str]], str]:
    p = _manifest_path(root)
    if not p.exists():
        return [], "\n"
    text = p.read_bytes().decode("utf-8")
    term = "\r\n" if "\r\n" in text else "\n"
    return list(csv.reader(io.StringIO(text, newline=""))), term


def _csv_text(rows: list[list[str]], term: str) -> bytes:
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator=term).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _manifest_dicts(rows: list[list[str]]) -> list[dict]:
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:] if r]


def _manifest_append(root: Path, row: list[str]) -> tuple[Path, bytes]:
    p = _manifest_path(root)
    if not p.exists():
        return p, _csv_text([MANIFEST_FIELDS, row], "\n")
    data = p.read_bytes()
    term = "\r\n" if b"\r\n" in data else "\n"
    if data and not data.endswith(b"\n"):
        data += term.encode()
    return p, data + _csv_text([row], term)


def _find_git_top(cwd: Path) -> Path | None:
    for d in [cwd, *cwd.parents]:
        if (d / ".git").exists():
            return d
    return None


def _resolve_root(root_arg: str | None, environ: Mapping[str, str], cwd: Path) -> Path:
    cwd = Path(cwd)
    if root_arg:
        root = Path(root_arg)
    elif environ.get("LLM_WIKI_ROOT"):
        root = Path(environ["LLM_WIKI_ROOT"])
    else:
        return Path(os.path.abspath(_find_git_top(cwd) or cwd))
    return Path(os.path.abspath(root if root.is_absolute() else cwd / root))


def env(root_arg: str | None, environ: Mapping[str, str], cwd: pathlib.Path) -> dict:
    root = _resolve_root(root_arg, environ, cwd)
    if "CLAUDECODE" not in environ:
        mode = "chat"
    elif environ.get("CLAUDE_CODE_REMOTE") == "true":
        mode = "cloud"
    else:
        mode = "local"
    cloud_push = "session-branch"
    toml_path = root / "llm-wiki.toml"
    if toml_path.exists():
        try:
            conf = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            raise LearnError(f"{toml_path} 파싱 실패: {e}") from None
        add = conf.get("add", {})
        if isinstance(add, dict) and "cloud_push" in add:
            cloud_push = add["cloud_push"]
            if cloud_push not in CLOUD_PUSH_VALUES:
                raise LearnError(f"{toml_path}의 cloud_push 값 오류(default-branch | session-branch): '{_show(cloud_push)}'")
    return {
        "mode": mode,
        "root": str(root),
        "has_wiki": (root / "wiki" / "index.md").exists(),
        "cloud_push": cloud_push,
    }


def init(root: Path) -> dict:
    root = Path(root)
    files = [
        (root / "wiki" / "index.md", INDEX_TEXT.encode("utf-8")),
        (root / "wiki" / "log.md", LOG_TEXT.encode("utf-8")),
        (root / "raw" / "MANIFEST.csv", _csv_text([MANIFEST_FIELDS], "\n")),
    ]
    todo = [(p, d) for p, d in files if not p.exists()]
    _write_all(todo)
    return {"created": [p.relative_to(root).as_posix() for p, _ in todo]}


def _outline(text: str) -> list[dict] | None:
    if len(text) <= OUTLINE_THRESHOLD:
        return None
    return [
        {"line": n, "heading": line.strip()}
        for n, line in enumerate(text.split("\n"), 1)
        if line.startswith("#")
    ]


def _convert(source: str) -> str:
    try:
        from markitdown import MarkItDown

        text = MarkItDown().convert(source).text_content
    except Exception as e:
        raise LearnError(f"변환 실패: {_show(source)} ({type(e).__name__}: {e})", 3) from None
    if not text or not text.strip():
        raise LearnError(f"변환 결과가 비어 있음: {_show(source)}", 3)
    return text


def fetch(source: str, date: datetime.date, slug: str, root: Path) -> dict:
    root = Path(root)
    source = str(source)
    slug = _slugify(slug)
    is_url = source.lower().startswith(("http://", "https://"))
    data = None
    if is_url:
        original, digest = source, None
    else:
        path = Path(source)
        if not path.is_file():
            raise LearnError(f"없는 파일이거나 http(s) URL이 아님: {_show(source)}")
        data = path.read_bytes()
        original, digest = path.name, hashlib.sha256(data).hexdigest()

    for row in _manifest_dicts(_read_manifest(root)[0]):
        hit = row.get("original_name") == source if is_url else row.get("sha256") == digest
        if hit:
            raw_rel = row["raw_path"]
            md_rel = None
            cand = raw_rel if raw_rel.endswith(".md") else os.path.splitext(raw_rel)[0] + ".md"
            if (root / cand).is_file():
                md_rel = cand
            text = (root / md_rel).read_text(encoding="utf-8", errors="replace") if md_rel else ""
            return {
                "raw": raw_rel,
                "md": md_rel,
                "chars": len(text),
                "outline": _outline(text) if md_rel else None,
                "duplicate_of": raw_rel,
            }

    ext = "" if is_url else path.suffix.lower()
    if is_url:
        text = _convert(source)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    elif not data:
        raise LearnError(f"빈 파일: {_show(source)}", 3)
    elif ext == ".md":
        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            raise LearnError(f"변환 결과가 비어 있음: {_show(source)}", 3)
    else:
        text = _convert(str(path))

    folder = root / "raw" / f"{date:%Y}" / f"{date:%m}"
    base = f"{date.isoformat()}-{slug}"
    n = 1
    while True:
        stem = base if n == 1 else f"{base}-{n}"
        raw_p = folder / (stem + ext) if not is_url else folder / (stem + ".md")
        md_p = folder / (stem + ".md")
        if not raw_p.exists() and not md_p.exists():
            break
        n += 1

    writes: list[tuple[Path, bytes]] = []
    if is_url or ext == ".md":
        raw_p = md_p
        writes.append((md_p, text.encode("utf-8") if is_url else data))
    else:
        writes.append((raw_p, data))
        writes.append((md_p, text.encode("utf-8")))
    raw_rel = raw_p.relative_to(root).as_posix()
    archived = _now().astimezone().isoformat(timespec="seconds")
    writes.append(_manifest_append(root, [raw_rel, original, digest, archived, ""]))
    _write_all(writes)
    return {
        "raw": raw_rel,
        "md": md_p.relative_to(root).as_posix(),
        "chars": len(text),
        "outline": _outline(text),
        "duplicate_of": None,
    }


def related(query: str, root: Path, limit: int = 10) -> list[dict]:
    terms = [t for t in query.lower().split() if t]
    if not terms:
        raise LearnError("빈 query")
    if limit < 1:
        raise LearnError(f"limit은 1 이상이어야 함: {_show(limit)}")
    root = Path(root)
    wiki = root / "wiki"
    skip = {wiki / "index.md", wiki / "log.md"}
    found = []
    for p in sorted(wiki.rglob("*.md")) if wiki.is_dir() else []:
        if p in skip:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        meta = _parse_fm(text)
        lines = text.replace("\r\n", "\n").split("\n")
        body_lines = lines[(_fm_end(lines) or -1) + 1 :]
        title = next((l[2:].strip() for l in body_lines if l.startswith("# ")), p.stem)
        body = "\n".join(body_lines).lower()
        labels = []
        for key in ("tags", "aliases"):
            v = meta.get(key, [])
            labels += [x.lower() for x in (v if isinstance(v, list) else [v])]
        score = 0
        for t in terms:
            if t in title.lower():
                score += 10
            if any(t in x for x in labels):
                score += 5
            score += min(body.count(t), 5)
        if score:
            lv = meta.get("level")
            found.append({
                "path": p.relative_to(root).as_posix(),
                "title": title,
                "level": int(lv) if lv in ("0", "1", "2", "3", "4") else None,
                "score": score,
            })
    found.sort(key=lambda r: (-r["score"], r["title"], r["path"]))
    return found[:limit]


def _template_text(root: Path) -> str:
    p = root / "templates" / "concept.md"
    if not p.is_file():
        p = Path(__file__).parent / "concept.md"
    return p.read_bytes().decode("utf-8")


def _find_pages(root: Path, title: str) -> list[Path]:
    wiki = root / "wiki"
    skip = {wiki / "index.md", wiki / "log.md"}
    name = f"{title}.md"
    return [p for p in wiki.rglob("*.md") if p.name == name and p not in skip] if wiki.is_dir() else []


def _check_source(source: str, root: Path) -> str:
    p = Path(source)
    p = p if p.is_absolute() else root / p
    resolved = p.resolve()
    if not resolved.is_relative_to((root / "raw").resolve()) or not resolved.is_file():
        raise LearnError(f"raw 안의 실제 파일이 아님: {_show(source)}")
    return resolved.relative_to(root.resolve()).as_posix()


def _append_text_line(data: bytes | None, line: str, header: str) -> bytes:
    text = header if data is None else data.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith("\n"):
        text += nl
    return (text + line + nl).encode("utf-8")


def _index_with(root: Path, title: str, summary: str) -> tuple[Path, bytes] | None:
    p = root / "wiki" / "index.md"
    line = f"- [[{title}]] — {summary}"
    if not p.exists():
        return p, (INDEX_TEXT + line + "\n").encode("utf-8")
    text = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _split_lines(text)
    if any(_body(l).startswith(f"- [[{title}]]") for l in lines):
        return None
    s = _section(lines, STUDY_HEADING)
    if s is None:
        pre = [""] if lines and lines[-1].strip() else []
        _insert(lines, len(lines), pre + [STUDY_HEADING, line], nl)
    else:
        _insert(lines, _last_nonblank(lines, *s) + 1, [line], nl)
    return p, "".join(lines).encode("utf-8")


def _manifest_with_sources(root: Path, sources: Sequence[str], page_rel: str) -> tuple[Path, bytes] | None:
    if not sources:
        return None
    rows, term = _read_manifest(root)
    if not rows or "raw_path" not in rows[0] or "extracted_to" not in rows[0]:
        return None
    rp, et = rows[0].index("raw_path"), rows[0].index("extracted_to")
    changed = False
    for r in rows[1:]:
        if len(r) <= max(rp, et):
            continue
        row_base = os.path.splitext(r[rp])[0]
        for s in sources:
            base = s[:-3] if s.endswith(".md") else s
            if r[rp] == s or row_base == base:
                cur = [x for x in r[et].split(";") if x]
                if page_rel not in cur:
                    r[et] = ";".join(cur + [page_rel])
                    changed = True
    return (_manifest_path(root), _csv_text(rows, term)) if changed else None


def _plan_record(title, level, evidence, root, date, summary, misconception, sources) -> dict:
    root = Path(root)
    _check_title(title)
    _check_level(level)
    evidence = _one_line(evidence)
    misconception = _one_line(misconception) if misconception else None
    summary = _one_line(summary) if summary else None
    srcs = list(dict.fromkeys(_check_source(s, root) for s in sources))
    pages = _find_pages(root, title)
    if len(pages) > 1:
        raise LearnError(f"같은 제목의 페이지가 둘 이상: {_show(title)} ({', '.join(p.relative_to(root).as_posix() for p in pages)})")
    if pages:
        page, old = pages[0], None
        try:
            old = page.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise LearnError(f"UTF-8이 아닌 페이지: {page}") from None
        text, is_new = old, False
    else:
        if not summary:
            raise LearnError(f"새 페이지에는 summary가 필요함: {_show(title)}")
        page, old, is_new = root / "wiki" / "study" / f"{title}.md", None, True
        text = _template_text(root).replace("{{title}}", title).replace("{{date}}", date.isoformat())
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _split_lines(text)
    prev = None
    if not is_new:
        lv = _parse_fm(text).get("level")
        prev = int(lv) if lv in ("0", "1", "2", "3", "4") else None

    if is_new:
        s = _section(lines, "## 요약")
        if s:
            for i in range(s[0] + 1, s[1]):
                if _body(lines[i]).strip() == "(한두 문장)":
                    lines[i] = summary + _eol(lines[i])
                    break
    if _fm_end(lines) is None:
        lines[0:0] = ["---" + nl, "---" + nl]
    _set_scalar(lines, "level", str(level), nl)
    _set_scalar(lines, "updated", date.isoformat(), nl)
    _add_sources(lines, srcs, nl)

    entry = f"- {date.isoformat()} L{level} {SOLO[level]}: {evidence}"
    _ensure_section(lines, "## 이해 기록", ["## 오해와 교정", "## 연결"], nl)
    if entry not in _section_bodies(lines, "## 이해 기록"):
        _append_to_section(lines, "## 이해 기록", [entry], [], nl)
    _ensure_section(lines, "## 오해와 교정", ["## 연결"], nl)
    if misconception:
        mline = f"- {date.isoformat()} {misconception}"
        if mline not in _section_bodies(lines, "## 오해와 교정"):
            _append_to_section(lines, "## 오해와 교정", [mline], [], nl)

    page_rel = page.relative_to(root).as_posix()
    return {
        "root": root, "title": title, "level": level, "date": date, "page": page, "page_rel": page_rel,
        "is_new": is_new, "old": old, "lines": lines, "nl": nl, "prev": prev,
        "index": _index_with(root, title, summary) if is_new else None,
        "manifest": _manifest_with_sources(root, srcs, page_rel),
    }


def _commit_record(plan: dict) -> dict:
    root, page = plan["root"], plan["page"]
    new_text = "".join(plan["lines"])
    changed = plan["is_new"] or new_text != plan["old"] or plan["manifest"] is not None
    if changed:
        d = plan["date"].isoformat()
        if plan["is_new"]:
            msg = f"- {d} [learn] {plan['title']}: 새 페이지, L{plan['level']}"
        else:
            prev = "-" if plan["prev"] is None else plan["prev"]
            msg = f"- {d} [learn] {plan['title']}: L{prev}→L{plan['level']}"
        log = root / "wiki" / "log.md"
        writes = [(page, new_text.encode("utf-8"))]
        if plan["index"]:
            writes.append(plan["index"])
        writes.append((log, _append_text_line(log.read_bytes() if log.exists() else None, msg, LOG_TEXT)))
        if plan["manifest"]:
            writes.append(plan["manifest"])
        _write_all(writes)
    return {
        "page": plan["page_rel"],
        "created": plan["is_new"],
        "previous_level": plan["prev"],
        "level": plan["level"],
        "changed": changed,
    }


def record(title: str, level: int, evidence: str, root: Path, date: datetime.date,
           summary: str | None = None, misconception: str | None = None,
           sources: Sequence[str] = ()) -> dict:
    return _commit_record(_plan_record(title, level, evidence, root, date, summary, misconception, sources))


def make_result(title: str, level: int, date: datetime.date, summary: str, evidence: str,
                out_dir: Path, misconception: str | None = None, mine: str = "",
                supplement: str = "", links: Sequence[str] = (), next_items: Sequence[str] = ()) -> dict:
    out_dir = Path(out_dir)
    _check_title(title)
    _check_level(level)
    if not out_dir.is_dir():
        raise LearnError(f"출력 폴더가 없음: {out_dir}")
    head = [
        "---", "type: learn-result", "version: 1", f"title: {_one_line(title)}", f"date: {date.isoformat()}",
        f"level: {level}", f"summary: {_one_line(summary)}", f"evidence: {_one_line(evidence)}",
    ]
    if misconception:
        head.append(f"misconception: {_one_line(misconception)}")
    head.append("---")
    parts = list(head)
    for heading, content in (
        ("## 내가 정리한 것", mine.strip().split("\n") if mine.strip() else []),
        ("## 보충 (LLM)", supplement.strip().split("\n") if supplement.strip() else []),
        ("## 연결", [f"- {l}" for l in links]),
        ("## 다음 학습", [f"- {n}" for n in next_items]),
    ):
        parts += ["", heading, *content]
    base = f"{date.isoformat()}-{_slugify(title)}"
    n = 1
    while True:
        path = out_dir / (f"{base}.learn.md" if n == 1 else f"{base}-{n}.learn.md")
        if not path.exists():
            break
        n += 1
    path.write_bytes(("\n".join(parts) + "\n").encode("utf-8"))
    return {"path": path.as_posix()}


def _result_sections(text: str) -> dict[str, list[str]]:
    lines = text.replace("\r\n", "\n").split("\n")
    out: dict[str, list[str]] = {}
    cur = None
    for l in lines[(_fm_end(lines) or -1) + 1 :]:
        if l.startswith("## "):
            name = l[3:].strip()
            cur = name if name in RESULT_SECTIONS else None
            if cur:
                out[cur] = []
        elif cur:
            out[cur].append(l.rstrip())
    return {k: _trim(v) for k, v in out.items() if _trim(v)}


def _trim(lines: list[str]) -> list[str]:
    a, b = 0, len(lines)
    while a < b and not lines[a].strip():
        a += 1
    while b > a and not lines[b - 1].strip():
        b -= 1
    return lines[a:b]


def _is_placeholder(line: str, heading: str) -> bool:
    s = _body(line).strip()
    if heading == "## 연결":
        return s == LINK_PLACEHOLDER
    return s.startswith("(") and s.endswith(")")


def import_result(path: Path, root: Path) -> dict:
    path, root = Path(path), Path(root)
    if not path.is_file():
        raise LearnError(f"import 파일이 없음: {path}")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise LearnError(f"UTF-8이 아닌 파일: {path}") from None
    meta = _parse_fm(text)
    if meta.get("type") != "learn-result":
        raise LearnError(f"learn-result 형식이 아님(type): {path}")
    if meta.get("version") != "1":
        raise LearnError(f"지원하지 않는 version: '{_show(meta.get('version'))}' ({path})")
    for key in ("title", "date", "level", "summary", "evidence"):
        v = meta.get(key)
        if not isinstance(v, str) or not v.strip():
            raise LearnError(f"{path}에 필요한 키가 없음: {key}")
    date = parse_date(meta["date"])
    if not re.fullmatch(r"[0-4]", meta["level"]):
        raise LearnError(f"level 형식 오류: '{_show(meta['level'])}' ({path})")
    level = int(meta["level"])
    sections = _result_sections(text)

    plan = _plan_record(meta["title"], level, meta["evidence"], root, date, meta["summary"],
                        meta.get("misconception") or None, ())
    lines, nl, is_new = plan["lines"], plan["nl"], plan["is_new"]
    anchors = {
        "내가 정리한 것": ["## 보충 (LLM)", "## 이해 기록", "## 오해와 교정", "## 연결", "## 다음 학습", "## 출처"],
        "보충 (LLM)": ["## 이해 기록", "## 오해와 교정", "## 연결", "## 다음 학습", "## 출처"],
        "연결": ["## 다음 학습", "## 출처"],
        "다음 학습": ["## 출처"],
    }
    added = []
    for name in RESULT_SECTIONS:
        block = sections.get(name)
        if not block:
            continue
        heading = f"## {name}"
        have = _section_bodies(lines, heading)
        if name in LIST_SECTIONS:
            have_set = {h.strip() for h in have}
            block = [l for l in block if l.strip() not in have_set]
            if not block:
                continue
        elif _contains_block(have, block):
            continue
        s = _ensure_section(lines, heading, anchors[name], nl)
        ph = next((i for i in range(s[0] + 1, s[1]) if _is_placeholder(lines[i], heading)), None) if is_new else None
        if ph is not None:
            new = [x + nl for x in block]
            if not _eol(lines[ph]):
                new[-1] = block[-1]
            lines[ph : ph + 1] = new
        else:
            _append_to_section(lines, heading, block, [], nl, blank_before=name not in LIST_SECTIONS)
        added.append(name)
    out = _commit_record(plan)
    out["sections_added"] = added
    return out


def _date_arg(value: str) -> datetime.date:
    try:
        return parse_date(value)
    except LearnError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    p = argparse.ArgumentParser(prog="learn.py", description="/wiki-add skill helper")
    p.add_argument("--root", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("env", parents=[common])
    sub.add_parser("init", parents=[common])
    s = sub.add_parser("fetch", parents=[common])
    s.add_argument("source")
    s.add_argument("--date", type=_date_arg, required=True)
    s.add_argument("--slug", required=True)
    s = sub.add_parser("related", parents=[common])
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("record", parents=[common])
    s.add_argument("title")
    s.add_argument("--level", type=int, required=True)
    s.add_argument("--evidence", required=True)
    s.add_argument("--summary")
    s.add_argument("--misconception")
    s.add_argument("--source", action="append", dest="sources", default=[])
    s.add_argument("--date", type=_date_arg, default=None)
    s = sub.add_parser("result", parents=[common])
    s.add_argument("title")
    s.add_argument("--level", type=int, required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--evidence", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--misconception")
    s.add_argument("--mine", default="")
    s.add_argument("--supplement", default="")
    s.add_argument("--link", action="append", dest="links", default=[])
    s.add_argument("--next", action="append", dest="next_items", default=[])
    s.add_argument("--date", type=_date_arg, default=None)
    s = sub.add_parser("import", parents=[common])
    s.add_argument("file")
    return p


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None,
         cwd: Path | None = None) -> int:
    environ = os.environ if environ is None else environ
    cwd = Path.cwd() if cwd is None else Path(cwd)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 2)

    def at(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else cwd / q

    try:
        root = _resolve_root(args.root, environ, cwd)
        today = lambda: args.date or parse_date("today")
        if args.cmd == "env":
            out = env(args.root, environ, cwd)
        elif args.cmd == "init":
            out = init(root)
        elif args.cmd == "fetch":
            src = args.source
            if not src.lower().startswith(("http://", "https://")) and at(src).exists():
                src = str(at(src))
            out = fetch(src, args.date, args.slug, root)
        elif args.cmd == "related":
            out = related(" ".join(args.query), root, args.limit)
        elif args.cmd == "record":
            out = record(args.title, args.level, args.evidence, root, today(), args.summary,
                         args.misconception, args.sources)
        elif args.cmd == "result":
            out = make_result(args.title, args.level, today(), args.summary, args.evidence, at(args.out),
                              args.misconception, args.mine, args.supplement, args.links,
                              args.next_items)
        else:
            out = import_result(at(args.file), root)
    except LearnError as e:
        print(f"오류: {e}", file=sys.stderr)
        return e.code
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
