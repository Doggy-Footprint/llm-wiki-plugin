# /// script
# requires-python = ">=3.11"
# dependencies = ["fsrs==6.3.2"]
# ///
"""표준 라이브러리만 최상위에서 import한다. fsrs는 일정 계산 함수 안에서만 import해서, 의존성을 설치할 수 없는 claude.ai 코드 실행 환경에서도 make_result와 `result`가 돌아야 한다. claude.ai에서는 이 파일 하나만 내려받아 실행하므로 learn.py·scripts/_lib.py를 최상위에서 import하지 않는다."""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

RATINGS: tuple[str, ...] = ("again", "hard", "good", "easy")
REVIEWS_HEADER: list[str] = ["date", "page", "rating", "mode", "source", "result_id"]
DUE_DEFAULT = 5
DUE_MAX = 10
FRONTIER_MAX = 10
ROLLOVER_HOUR = 5
SOLO: dict[int, str] = {0: "전구조적", 1: "단일구조적", 2: "다중구조적", 3: "관계적", 4: "확장추상적"}
SUMMARY_CAP, MINE_CAP, MISC_CAP, MISC_COUNT, LINK_CAP = 300, 800, 200, 3, 10
CSV_NAME = "data/reviews.csv"
DECK_PATH = "chat/deck.md"
SOURCES = ("code", "chat")
LINK_PLACEHOLDER_TARGET = "관련 개념"
_H_RE = re.compile(r"^#{1,2} ")
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class QuizError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _iso(value: str) -> datetime.date | None:
    if not _ISO_RE.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def parse_date(value: str, now: datetime.datetime | None = None) -> datetime.date:
    if value in ("today", "yesterday"):
        now = now or _now()
        today = now.date() - datetime.timedelta(days=1 if now.hour < ROLLOVER_HOUR else 0)
        return today - datetime.timedelta(days=1) if value == "yesterday" else today
    if not _ISO_RE.fullmatch(value):
        raise QuizError(f"날짜 형식 오류(YYYY-MM-DD, today, yesterday): {value!r}")
    d = _iso(value)
    if d is None:
        raise QuizError(f"없는 날짜: {value!r}")
    return d


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _split_fm(text: str) -> tuple[dict, str]:
    """scripts/_lib.py frontmatter()와 같은 값을 읽어야 한다. CRLF는 LF로 바꿔 읽는다."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
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
    rest = text[end + 1:]
    return meta, rest.split("\n", 1)[1] if "\n" in rest else ""


class _Page:
    __slots__ = ("path", "title", "level", "created", "updated", "lines")

    def __init__(self, path, title, level, created, updated, lines):
        self.path, self.title, self.level = path, title, level
        self.created, self.updated, self.lines = created, updated, lines

    def start_date(self) -> datetime.date | None:
        for v in (self.created, self.updated):
            d = _iso(v) if isinstance(v, str) else None
            if d:
                return d
        return None


def _load_page(root: Path, file: Path) -> tuple[_Page | None, str | None]:
    rel = file.relative_to(root).as_posix()
    try:
        text = file.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None, f"{rel}: UTF-8이 아니어서 건너뜀"
    meta, body = _split_fm(text)
    if meta.get("type") != "concept":
        return None, None
    lines = body.split("\n")
    title = file.stem
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip() or file.stem
            break
    lv = meta.get("level")
    level = int(lv) if isinstance(lv, str) and re.fullmatch(r"[0-4]", lv) else None
    str_or_none = lambda v: v if isinstance(v, str) and v else None
    return _Page(rel, title, level, str_or_none(meta.get("created")), str_or_none(meta.get("updated")), lines), None


def _scan(root: Path) -> tuple[list[_Page], list[str], set[str]]:
    wiki = root / "wiki"
    pages: list[_Page] = []
    warnings: list[str] = []
    stems: set[str] = set()
    if not wiki.is_dir():
        return pages, warnings, stems
    skip = {wiki / "index.md", wiki / "log.md"}
    for f in sorted(wiki.rglob("*.md"), key=lambda p: p.as_posix()):
        if not f.is_file():
            continue
        stems.add(f.stem)
        if f in skip:
            continue
        page, warn = _load_page(root, f)
        if warn:
            warnings.append(warn)
        if page:
            pages.append(page)
    return pages, warnings, stems


def concept_pages(root: Path) -> list[dict]:
    return [{"path": p.path, "title": p.title, "level": p.level, "created": p.created}
            for p in _scan(Path(root))[0]]


def _valid_rel(page: object) -> bool:
    if not isinstance(page, str) or not page.startswith("wiki/") or not page.endswith(".md"):
        return False
    if any(ord(c) < 32 or c in "\\|" for c in page):
        return False
    segs = page.split("/")
    return all(s not in ("", ".", "..") for s in segs) and segs[-1] != ".md"


def _check_page(root: Path, page: str) -> _Page:
    if not _valid_rel(page):
        raise QuizError(f"wiki/ 안의 .md 경로가 아님: {page!r}")
    wiki = (root / "wiki").resolve()
    file = (root / page).resolve()
    if not file.is_relative_to(wiki) or not file.is_file() or page in ("wiki/index.md", "wiki/log.md"):
        raise QuizError(f"개념 페이지가 아님: {page!r}")
    loaded, _ = _load_page(root, root / page)
    if loaded is None:
        raise QuizError(f"개념 페이지가 아님(type: concept 아님 또는 읽을 수 없음): {page!r}")
    return loaded


def _section(lines: list[str], heading: str) -> list[str]:
    for i, line in enumerate(lines):
        if line.rstrip() == heading:
            out = []
            for l in lines[i + 1:]:
                if _H_RE.match(l):
                    break
                out.append(l)
            return out
    return []


def _cap(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _placeholder(line: str) -> bool:
    s = line.strip()
    return s.startswith("(") and s.endswith(")")


def _link_targets(lines: list[str], cap: int | None = None) -> list[str]:
    out: list[str] = []
    for line in _section(lines, "## 연결"):
        for m in _LINK_RE.findall(line):
            t = m.split("|", 1)[0].split("#", 1)[0].strip()
            if t and t != LINK_PLACEHOLDER_TARGET and t not in out:
                out.append(t)
    return out if cap is None else out[:cap]


def _card_of(page: _Page) -> dict:
    lines = page.lines
    summary = " ".join(s for s in (l.strip() for l in _section(lines, "## 요약"))
                       if s and not _placeholder(s))
    mine = "\n".join(s for s in (l.strip() for l in _section(lines, "## 내가 정리한 것"))
                     if s and not _placeholder(s))
    misc = [l.strip()[2:].strip() for l in _section(lines, "## 오해와 교정") if l.strip().startswith("- ")]
    return {
        "path": page.path,
        "title": page.title,
        "level": page.level,
        "summary": _cap(summary, SUMMARY_CAP),
        "mine": _cap(mine, MINE_CAP),
        "misconceptions": [_cap(m, MISC_CAP) for m in misc[-MISC_COUNT:]],
        "links": _link_targets(lines, LINK_CAP),
    }


def card(root: Path, page: str) -> dict:
    return _card_of(_check_page(Path(root), page))


def _frontier(pages: list[_Page], stems: set[str], limit: int) -> list[dict]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= FRONTIER_MAX:
        raise QuizError(f"limit은 1~{FRONTIER_MAX}: {limit!r}")
    found: dict[str, list[_Page]] = {}
    for p in pages:
        for t in _link_targets(p.lines):
            if t not in stems:
                found.setdefault(t, []).append(p)
    items = []
    for t, srcs in found.items():
        levels = [p.level for p in srcs if p.level is not None]
        items.append({"title": t, "from": sorted({p.title for p in srcs}),
                      "max_level": max(levels) if levels else None})
    items.sort(key=lambda i: (-len(i["from"]), -(i["max_level"] if i["max_level"] is not None else -1), i["title"]))
    return items[:limit]


def frontier(root: Path, limit: int = FRONTIER_MAX) -> list[dict]:
    pages, _, stems = _scan(Path(root))
    return _frontier(pages, stems, limit)


def _read_csv(root: Path) -> tuple[list[dict], list[str], set[str]]:
    p = root / CSV_NAME
    if not p.is_file():
        return [], [], set()
    text = p.read_bytes().decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows: list[dict] = []
    warnings: list[str] = []
    ids: set[str] = set()
    first = True
    for row in reader:
        line = reader.line_num
        if first:
            first = False
            if row != REVIEWS_HEADER:
                warnings.append(f"{CSV_NAME}:{line}: unexpected header")
            continue
        if not row:
            continue
        if len(row) >= 6 and row[5].strip():
            ids.add(row[5].strip())
        reason = None
        if len(row) < 6 or not row[1].strip():
            reason = "missing columns"
        elif (d := _iso(row[0].strip())) is None:
            reason = f"invalid date {row[0]!r}"
        elif row[2].strip() not in RATINGS:
            reason = f"invalid rating {row[2].strip()!r}"
        if reason:
            warnings.append(f"{CSV_NAME}:{line}: {reason}")
            continue
        rows.append({"date": d, "page": row[1].strip(), "rating": row[2].strip(), "order": len(rows)})
    return rows, warnings, ids


def _append_rows(root: Path, rows: Sequence[Sequence[str]]) -> None:
    p = root / CSV_NAME
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    if p.is_file() and p.stat().st_size > 0:
        old = p.read_bytes()
        head = b"" if old.endswith(b"\n") else b"\n"
    else:
        old, head = b"", b""
        w.writerow(REVIEWS_HEADER)
    w.writerows(rows)
    _atomic_write(p, old + head + buf.getvalue().encode("utf-8"))


def _schedule(pages: list[_Page], rows: list[dict]) -> dict[str, dict]:
    import fsrs

    scheduler = fsrs.Scheduler(desired_retention=0.9, learning_steps=(), relearning_steps=(), enable_fuzzing=False)
    rating_of = {"again": fsrs.Rating.Again, "hard": fsrs.Rating.Hard, "good": fsrs.Rating.Good, "easy": fsrs.Rating.Easy}
    by_page: dict[str, list[dict]] = {}
    for r in rows:
        by_page.setdefault(r["page"], []).append(r)
    out: dict[str, dict] = {}
    for p in pages:
        start = p.start_date()
        if start is None:
            continue
        real = by_page.get(p.path, [])
        events = [(start, 0, 0, "good")] + [(r["date"], 1, r["order"], r["rating"]) for r in real]
        events.sort(key=lambda e: e[:3])
        c = fsrs.Card()
        for d, _, _, rating in events:
            at = datetime.datetime(d.year, d.month, d.day, 12, tzinfo=datetime.timezone.utc)
            c, _log = scheduler.review_card(c, rating_of[rating], review_datetime=at)
        ordered = sorted(real, key=lambda r: (r["date"], r["order"]))
        out[p.path] = {
            "due": c.due.astimezone(datetime.timezone.utc).date(),
            "reviews": len(real),
            "last_rating": ordered[-1]["rating"] if ordered else None,
            "last_date": ordered[-1]["date"].isoformat() if ordered else None,
        }
    return out


def _due(root: Path, pages: list[_Page], page_warnings: list[str], date: datetime.date, limit: int) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= DUE_MAX:
        raise QuizError(f"limit은 1~{DUE_MAX}: {limit!r}")
    rows, csv_warnings, _ = _read_csv(root)
    known = {p.path for p in pages}
    orphans = sum(1 for r in rows if r["page"] not in known)
    warnings = list(page_warnings)
    for p in pages:
        if p.start_date() is None:
            warnings.append(f"{p.path}: created/updated 날짜가 없어 복습 대상에서 제외")
    warnings += csv_warnings
    titles = {p.path: p for p in pages}
    items = []
    for path, s in _schedule(pages, rows).items():
        if s["due"] <= date:
            p = titles[path]
            items.append({"path": path, "title": p.title, "level": p.level, "due": s["due"].isoformat(),
                          "overdue_days": (date - s["due"]).days, "reviews": s["reviews"],
                          "last_rating": s["last_rating"], "last_date": s["last_date"]})
    items.sort(key=lambda i: (-i["overdue_days"], i["path"]))
    return {"items": items[:limit], "warnings": warnings, "orphans": orphans}


def due(root: Path, date: datetime.date, limit: int = DUE_DEFAULT) -> dict:
    root = Path(root)
    pages, page_warnings, _ = _scan(root)
    return _due(root, pages, page_warnings, date, limit)


def _check_entries(entries: Sequence[tuple[str, str]], page_check) -> list[tuple[str, str]]:
    entries = [tuple(e) for e in entries]
    if not entries:
        raise QuizError("기록할 항목이 없음")
    seen = set()
    for page, rating in entries:
        if rating not in RATINGS:
            raise QuizError(f"rating은 {'/'.join(RATINGS)} 중 하나: {rating!r}")
        if page in seen:
            raise QuizError(f"중복된 페이지: {page!r}")
        seen.add(page)
        page_check(page)
    return entries


def record(root: Path, entries: Sequence[tuple[str, str]], date: datetime.date,
           now: datetime.datetime | None = None) -> dict:
    root = Path(root)
    entries = _check_entries(entries, lambda p: _check_page(root, p))
    now = now or _now()
    result_id = f"code-{date.isoformat()}T{now:%H%M%S}"
    _append_rows(root, [[date.isoformat(), p, r, "review", "code", result_id] for p, r in entries])
    out = deck(root, date)
    return {"added": len(entries), "result_id": result_id, "deck": out["path"]}


def make_result(entries: Sequence[tuple[str, str]], date: datetime.date, out_dir: Path,
                now: datetime.datetime | None = None) -> dict:
    def check(page: str) -> None:
        if not _valid_rel(page):
            raise QuizError(f"wiki/ 안의 .md 경로가 아님: {page!r}")

    entries = _check_entries(entries, check)
    now = now or _now()
    stamp = f"{date.isoformat()}-{now:%H%M%S}"
    out_dir = Path(out_dir)
    n, suffix = 1, ""
    while (out_dir / f"{stamp}{suffix}.quiz.md").exists():
        n += 1
        suffix = f"-{n}"
    rid = f"chat-{date.isoformat()}T{now:%H%M%S}{suffix}"
    text = ("---\ntype: quiz-result\nversion: 1\n"
            f"id: {rid}\ndate: {date.isoformat()}\nmode: review\nsource: chat\n---\n"
            + "".join(f"- {p} | {r}\n" for p, r in entries))
    path = out_dir / f"{stamp}{suffix}.quiz.md"
    _atomic_write(path, text.encode("utf-8"))
    return {"path": str(path), "id": rid}


_ENTRY_RE = re.compile(r"^-\s+(.*)\|(.*)$")


def import_result(path: Path, root: Path) -> dict:
    path, root = Path(path), Path(root)

    def bad(msg: str) -> QuizError:
        return QuizError(f"{path}: {msg}")

    if not path.is_file():
        raise bad("파일이 없음")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise bad("UTF-8이 아님") from None
    meta, body = _split_fm(text)
    if meta.get("type") != "quiz-result":
        raise bad("quiz-result 형식이 아님(type)")
    if meta.get("version") != "1":
        raise bad(f"지원하지 않는 version: {meta.get('version')!r}")
    rid = meta.get("id")
    if not isinstance(rid, str) or not rid.strip():
        raise bad("id가 없음")
    d = _iso(meta["date"]) if isinstance(meta.get("date"), str) else None
    if d is None:
        raise bad(f"date 형식 오류: {meta.get('date')!r}")
    if meta.get("mode") != "review":
        raise bad(f"mode는 review여야 함: {meta.get('mode')!r}")
    source = meta.get("source")
    if source not in SOURCES:
        raise bad(f"source는 {'/'.join(SOURCES)} 중 하나: {source!r}")
    entries: list[tuple[str, str]] = []
    for line in body.split("\n"):
        if not line.startswith("-"):
            continue
        m = _ENTRY_RE.match(line.rstrip())
        if not m:
            raise bad(f"항목 형식 오류: {line!r}")
        entries.append((m.group(1).strip(), m.group(2).strip().lower()))
    try:
        _check_entries(entries, lambda p: _check_page(root, p))
    except QuizError as e:
        raise bad(str(e)) from None
    rid = rid.strip()
    if rid in _read_csv(root)[2]:
        return {"added": 0, "skipped": True, "result_id": rid}
    _append_rows(root, [[d.isoformat(), p, r, "review", source, rid] for p, r in entries])
    return {"added": len(entries), "skipped": False, "result_id": rid}


def _level_text(level: int | None) -> str:
    return "L-" if level is None else f"L{level}"


def deck(root: Path, date: datetime.date) -> dict:
    root = Path(root)
    pages, page_warnings, stems = _scan(root)
    d = _due(root, pages, page_warnings, date, DUE_MAX)
    fr = _frontier(pages, stems, FRONTIER_MAX)
    by_path = {p.path: p for p in pages}

    due_lines = [f"## Due ({len(d['items'])})"]
    for it in d["items"]:
        c = _card_of(by_path[it["path"]])
        lv = it["level"]
        due_lines += [
            "",
            f"### {it['title']}",
            f"- path: {it['path']}",
            "- level: -" if lv is None else f"- level: L{lv} ({SOLO[lv]})",
            f"- due: {it['due']} (overdue {it['overdue_days']}d)",
            f"- last: {it['last_date']} {it['last_rating']}" if it["last_rating"] else "- last: -",
            f"- summary: {c['summary'] or '-'}",
            f"- mine: {c['mine'].replace(chr(10), ' / ') or '-'}",
        ]
        if c["misconceptions"]:
            due_lines.append("- misconceptions:")
            due_lines += [f"  - {m}" for m in c["misconceptions"]]
        else:
            due_lines.append("- misconceptions: -")
        due_lines.append(f"- links: {', '.join(c['links']) or '-'}")
    fr_lines = [f"## Frontier ({len(fr)})"]
    fr_lines += [f"- [[{f['title']}]] — from {', '.join(f'[[{t}]]' for t in f['from'])}" for f in fr]
    known = sorted(pages, key=lambda p: (p.title, p.path))
    known_lines = [f"## Known ({len(known)})"] + [f"- {p.title} ({_level_text(p.level)})" for p in known]
    sections = [["---", "type: quiz-deck", "version: 1", f"generated: {date.isoformat()}", "---", "# Quiz deck"],
                due_lines, fr_lines, known_lines]
    if d["warnings"]:
        sections.append(["## Warnings"] + [f"- {w}" for w in d["warnings"]])
    lines: list[str] = []
    for i, sec in enumerate(sections):
        if i:
            lines.append("")
        lines += sec
    text = "\n".join(lines) + "\n"
    _atomic_write(root / DECK_PATH, text.encode("utf-8"))
    keep = root / "chat" / "inbox" / ".gitkeep"
    if not keep.exists():
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_bytes(b"")
    return {"path": DECK_PATH, "chars": len(text), "due": len(d["items"]), "frontier": len(fr),
            "known": len(known)}


def _load_learn():
    import importlib.util

    p = Path(__file__).resolve().parent.parent / "wiki-add" / "learn.py"
    spec = importlib.util.spec_from_file_location("_quiz_learn", p)
    if spec is None or spec.loader is None:
        raise ImportError(f"learn.py를 불러올 수 없음: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sync(root: Path, date: datetime.date) -> dict:
    root = Path(root)
    inbox = root / "chat" / "inbox"
    quiz_ids: list[str] = []
    learned: list[str] = []
    failed: list[dict] = []
    learn_mod = None
    learn_error: str | None = None
    files = sorted((f for f in inbox.iterdir() if f.is_file()), key=lambda f: f.name) if inbox.is_dir() else []
    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            if f.name.endswith(".quiz.md"):
                quiz_ids.append(import_result(f, root)["result_id"])
            elif f.name.endswith(".learn.md"):
                if learn_mod is None and learn_error is None:
                    try:
                        learn_mod = _load_learn()
                    except Exception as e:  # learn.py runs arbitrary module code on import; any failure is per-file
                        learn_error = f"learn.py를 불러올 수 없음: {e}"
                if learn_mod is None:
                    raise QuizError(learn_error)
                try:
                    learned.append(learn_mod.import_result(f, root)["page"])
                except learn_mod.LearnError as e:
                    raise QuizError(str(e)) from None
            else:
                continue
        except (QuizError, OSError) as e:
            failed.append({"file": rel, "error": str(e)})
            continue
        f.unlink()
    out = deck(root, date)
    return {"quiz": quiz_ids, "learn": learned, "failed": failed, "deck": out["path"]}


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


def _date_arg(value: str) -> datetime.date:
    try:
        return parse_date(value)
    except QuizError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    p = argparse.ArgumentParser(prog="quiz.py", description="quiz skill helper")
    p.add_argument("--root", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("due", parents=[common])
    s.add_argument("--date", type=_date_arg, default=None)
    s.add_argument("--limit", type=int, default=DUE_DEFAULT)
    s = sub.add_parser("card", parents=[common])
    s.add_argument("page")
    s = sub.add_parser("frontier", parents=[common])
    s.add_argument("--limit", type=int, default=FRONTIER_MAX)
    s = sub.add_parser("record", parents=[common])
    s.add_argument("--date", type=_date_arg, default=None)
    s.add_argument("entries", nargs="+")
    s = sub.add_parser("result", parents=[common])
    s.add_argument("--out", required=True)
    s.add_argument("--date", type=_date_arg, default=None)
    s.add_argument("entries", nargs="+")
    s = sub.add_parser("import", parents=[common])
    s.add_argument("file")
    s = sub.add_parser("sync", parents=[common])
    s.add_argument("--date", type=_date_arg, default=None)
    s = sub.add_parser("deck", parents=[common])
    s.add_argument("--date", type=_date_arg, default=None)
    return p


def _entries(raw: Sequence[str]) -> list[tuple[str, str]]:
    out = []
    for item in raw:
        page, sep, rating = item.rpartition("=")
        if not sep:
            raise QuizError(f"PAGE=RATING 형식이 아님: {item!r}")
        out.append((page, rating))
    return out


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None,
         cwd: Path | None = None) -> int:
    environ = os.environ if environ is None else environ
    cwd = Path.cwd() if cwd is None else Path(cwd)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 2)

    code = 0
    try:
        root = _resolve_root(args.root, environ, cwd)
        today = lambda: args.date or parse_date("today")
        if args.cmd == "due":
            out = due(root, today(), args.limit)
        elif args.cmd == "card":
            out = card(root, args.page)
        elif args.cmd == "frontier":
            out = frontier(root, args.limit)
        elif args.cmd == "record":
            out = record(root, _entries(args.entries), today())
        elif args.cmd == "result":
            o = Path(args.out)
            out = make_result(_entries(args.entries), today(), o if o.is_absolute() else cwd / o)
        elif args.cmd == "import":
            f = Path(args.file)
            out = import_result(f if f.is_absolute() else cwd / f, root)
        elif args.cmd == "sync":
            out = sync(root, today())
            code = 1 if out["failed"] else 0
        else:
            out = deck(root, today())
    except QuizError as e:
        print(f"오류: {e}", file=sys.stderr)
        return e.code
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
