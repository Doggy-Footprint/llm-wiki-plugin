# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""표준 라이브러리만 쓴다. claude.ai 코드 실행 환경은 이 파일 하나만 내려받아 result를 돌린다."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path

ROLLOVER_HOUR = 5
AREAS: dict[str, str] = {"life": "## 생활 깨달음 (life/insights/)", "career": "## 커리어 깨달음 (career/insights/)"}
OLD_HEADING = "## 지난 생각"
RESULT_CONFIDENCE = ("hunch", "likely")
CHAT_SOURCE = "claude.ai 채팅"
DECK_PATH = "chat/insights.md"
SECTIONS = ("지금 생각", "생각의 변화", "근거", "보충 (LLM)", "연결", "출처")
RESULT_SECTIONS = ("보충 (LLM)", "연결")
LOG_TEXT = "# Log\n\nAppend only. Format: `- YYYY-MM-DD [작업] 내용`\n\n"
INDEX_TEXT = "# Index\n"


class InsightError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def parse_date(value: str, now: datetime.datetime | None = None) -> datetime.date:
    if value in ("today", "yesterday"):
        now = now or _now()
        today = now.date() - datetime.timedelta(days=1 if now.hour < ROLLOVER_HOUR else 0)
        return today if value == "today" else today - datetime.timedelta(days=1)
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise InsightError(f"날짜 형식이 아님(YYYY-MM-DD): '{_show(value)}'") from None


def _show(value: object) -> str:
    return "".join(
        c if unicodedata.category(c) != "Cc" else {"\t": "\\t", "\n": "\\n", "\r": "\\r"}.get(c, f"\\x{ord(c):02x}")
        for c in str(value)
    )


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _slugify(text: str) -> str:
    return re.sub(r"[^\w가-힣-]+", "-", text).strip("-") or "item"


def _check_title(title: str) -> None:
    bad = (
        not isinstance(title, str)
        or not title.strip()
        or title != title.strip()
        or "/" in title
        or "\\" in title
        or title.startswith(".")
        or len(title) > 100
        or any(c in title for c in "[]|#")
        or any(unicodedata.category(c) == "Cc" for c in title)
    )
    if bad:
        raise InsightError(f"잘못된 제목: '{_show(title)}'")


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
    for line in text[4:end].splitlines():
        if ":" not in line or line[0].isspace() or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        v = v.split(" #", 1)[0].strip()
        if v.startswith("[") and not v.startswith("[[") and v.endswith("]"):
            meta[k.strip()] = [_unquote(x) for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = _unquote(v)
    return meta


def _fm_end(lines: list[str]) -> int | None:
    if not lines or lines[0] != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return i
    return None


def _set_fm(lines: list[str], key: str, value: str) -> None:
    end = _fm_end(lines)
    if end is None:
        lines[0:0] = ["---", "---"]
        end = 1
    pat = re.compile(rf"^{re.escape(key)}[ \t]*:")
    for i in range(1, end):
        if pat.match(lines[i]):
            lines[i] = f"{key}: {value}"
            return
    lines.insert(end, f"{key}: {value}")


_H_RE = re.compile(r"^#{1,2} ")


def _section(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = (_fm_end(lines) or -1) + 1
    for i in range(start, len(lines)):
        if lines[i].rstrip() == heading:
            e = i + 1
            while e < len(lines) and not _H_RE.match(lines[e]):
                e += 1
            return i, e
    return None


def _trim(lines: list[str]) -> list[str]:
    a, b = 0, len(lines)
    while a < b and not lines[a].strip():
        a += 1
    while b > a and not lines[b - 1].strip():
        b -= 1
    return lines[a:b]


def _bodies(lines: list[str], heading: str) -> list[str]:
    s = _section(lines, f"## {heading}")
    return [] if s is None else _trim([l.rstrip() for l in lines[s[0] + 1 : s[1]]])


def _ensure(lines: list[str], heading: str) -> tuple[int, int]:
    h = f"## {heading}"
    found = _section(lines, h)
    if found:
        return found
    later = SECTIONS[SECTIONS.index(heading) + 1 :] if heading in SECTIONS else ()
    pos = next((s[0] for s in (_section(lines, f"## {x}") for x in later) if s), len(lines))
    while pos > 0 and not lines[pos - 1].strip():
        pos -= 1
    lines[pos:pos] = ["", h, ""] if pos < len(lines) else ["", h]
    return _section(lines, h)


def _set_body(lines: list[str], heading: str, body: Sequence[str]) -> None:
    h, e = _ensure(lines, heading)
    tail = [""] if e < len(lines) else []
    lines[h + 1 : e] = ([""] + list(body) if body else []) + tail


def _append(lines: list[str], heading: str, items: Sequence[str]) -> None:
    if not items:
        return
    h, e = _ensure(lines, heading)
    j = e - 1
    while j > h and not lines[j].strip():
        j -= 1
    if j == h:
        lines[h + 1 : e] = [""] + list(items) + ([""] if e < len(lines) else [])
    else:
        lines[j + 1 : j + 1] = list(items)


def _write_all(writes: Sequence[tuple[Path, bytes]]) -> None:
    undo: list[tuple[Path, bytes | None]] = []
    try:
        for path, data in writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            undo.append((path, path.read_bytes() if path.exists() else None))
            path.write_bytes(data)
    except BaseException:
        for path, old in reversed(undo):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise InsightError(f"UTF-8이 아닌 파일: {path}") from None


def _lines(text: str) -> list[str]:
    return text[:-1].split("\n") if text.endswith("\n") else text.split("\n")


def _join(lines: list[str]) -> bytes:
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def _template_text(root: Path) -> str:
    p = root / "templates" / "insight.md"
    if not p.is_file():
        p = Path(__file__).parent / "insight.md"
    return _read_text(p)


def _result_text(meta: Mapping[str, str], supplement: Sequence[str], links: Sequence[str]) -> str:
    head = ["---", "type: insight-result", "version: 1"]
    head += [f"{k}: {meta[k]}" for k in ("title", "date", "area", "confidence", "now", "said") if meta.get(k)]
    parts = head + ["---"]
    for name, body in (("보충 (LLM)", supplement), ("연결", links)):
        parts += ["", f"## {name}", *body]
    return "\n".join(parts) + "\n"


def parse_result(text: str, where: str = "result") -> dict:
    text = text.replace("\r\n", "\n")
    meta = _parse_fm(text)
    if meta.get("type") != "insight-result":
        raise InsightError(f"insight-result 형식이 아님(type): {where}")
    if meta.get("version") != "1":
        raise InsightError(f"지원하지 않는 version: '{_show(meta.get('version'))}' ({where})")
    for key in ("title", "date", "said"):
        v = meta.get(key)
        if not isinstance(v, str) or not v.strip():
            raise InsightError(f"{where}에 필요한 키가 없음: {key}")
    for key in ("area", "confidence", "now"):
        if key in meta and not isinstance(meta[key], str):
            raise InsightError(f"{key}는 한 줄 문자열이어야 함 ({where})")
    _check_title(meta["title"])
    date = parse_date(meta["date"])
    area = meta.get("area") or None
    if area is not None and area not in AREAS:
        raise InsightError(f"area는 {', '.join(AREAS)} 중 하나: '{_show(area)}' ({where})")
    conf = meta.get("confidence") or None
    if conf is not None and conf not in RESULT_CONFIDENCE:
        raise InsightError(f"confidence는 {', '.join(RESULT_CONFIDENCE)} 중 하나: '{_show(conf)}' ({where})")
    sections: dict[str, list[str]] = {}
    lines = _lines(text)
    cur = None
    for l in lines[(_fm_end(lines) or -1) + 1 :]:
        if l.startswith("## "):
            cur = l[3:].strip() if l[3:].strip() in RESULT_SECTIONS else None
            if cur:
                sections.setdefault(cur, [])
        elif cur:
            sections[cur].append(l.rstrip())
    links = _trim(sections.get("연결", []))
    for l in links:
        if not re.match(r"^- \[\[[^\]]+\]\]", l):
            raise InsightError(f"연결 줄은 '- [[제목]] — 관계' 형식: '{_show(l)}' ({where})")
    return {
        "title": meta["title"], "date": date, "area": area, "confidence": conf,
        "now": _one_line(meta.get("now") or "") or None, "said": _one_line(meta["said"]),
        "supplement": _trim(sections.get("보충 (LLM)", [])), "links": links,
    }


def make_result(title: str, date: datetime.date, said: str, out_dir: Path, area: str | None = None,
                now: str | None = None, confidence: str | None = None, supplement: str = "",
                links: Sequence[str] = ()) -> dict:
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise InsightError(f"출력 폴더가 없음: {out_dir}")
    meta = {"title": title, "date": date.isoformat(), "area": area or "", "confidence": confidence or "",
            "now": _one_line(now or ""), "said": _one_line(said)}
    text = _result_text(meta, _trim(supplement.strip("\n").split("\n")) if supplement.strip() else [],
                        [l if l.startswith("- ") else f"- {l}" for l in links])
    parse_result(text)
    base = f"{date.isoformat()}-{_slugify(title)}"
    n = 1
    while (path := out_dir / (f"{base}.insight.md" if n == 1 else f"{base}-{n}.insight.md")).exists():
        n += 1
    path.write_bytes(text.encode("utf-8"))
    return {"path": path.as_posix()}


def _wiki_pages(root: Path) -> list[Path]:
    wiki = root / "wiki"
    skip = {wiki / "index.md", wiki / "log.md"}
    return sorted(p for p in wiki.rglob("*.md") if p not in skip) if wiki.is_dir() else []


def _find_page(root: Path, title: str) -> Path | None:
    found = [p for p in _wiki_pages(root) if p.name == f"{title}.md"]
    if len(found) > 1:
        raise InsightError(f"같은 제목의 페이지가 둘 이상: {', '.join(p.relative_to(root).as_posix() for p in found)}")
    return found[0] if found else None


def _index_with(root: Path, title: str, area: str, summary: str, is_new: bool) -> tuple[Path, bytes] | None:
    p = root / "wiki" / "index.md"
    line = f"- [[{title}]] — {summary}"
    lines = _lines(_read_text(p)) if p.exists() else _lines(INDEX_TEXT)
    at = next((i for i, l in enumerate(lines) if l.startswith(f"- [[{title}]]")), None)
    if at is not None:
        if is_new or lines[at] == line:
            return None
        lines[at] = line
        return p, _join(lines)
    if not is_new:
        return None
    marker = f"({area}/insights/)"
    head = next((i for i, l in enumerate(lines) if l.startswith("## ") and marker in l), None)
    if head is None:
        pos = next((i for i, l in enumerate(lines) if l.rstrip() == OLD_HEADING), len(lines))
        while pos > 0 and not lines[pos - 1].strip():
            pos -= 1
        k = pos
        while k < len(lines) and not lines[k].strip():
            k += 1
        lines[pos:k] = ["", AREAS[area], line] + ([""] if k < len(lines) else [])
    else:
        e = head + 1
        while e < len(lines) and not lines[e].startswith("## "):
            e += 1
        j = e - 1
        while j > head and not lines[j].strip():
            j -= 1
        lines[j + 1 : j + 1] = [line]
    return p, _join(lines)


def _log_with(root: Path, msg: str) -> tuple[Path, bytes]:
    p = root / "wiki" / "log.md"
    text = _read_text(p) if p.exists() else LOG_TEXT
    if text and not text.endswith("\n"):
        text += "\n"
    return p, (text + msg + "\n").encode("utf-8")


def _new_page(root: Path, r: dict) -> list[str]:
    text = _template_text(root).replace("{{title}}", r["title"]).replace("{{date}}", r["date"].isoformat())
    lines = _lines(text)
    h1 = next((i for i in range((_fm_end(lines) or -1) + 1, len(lines)) if lines[i].startswith("# ")), None)
    if h1 is not None:
        e = h1 + 1
        while e < len(lines) and not lines[e].startswith("## "):
            e += 1
        lines[h1 + 1 : e] = [""] if e < len(lines) else []
    for name in SECTIONS:
        if _section(lines, f"## {name}"):
            _set_body(lines, name, [])
    return lines


def _plan(r: dict, root: Path) -> dict:
    title, d = r["title"], r["date"].isoformat()
    page = _find_page(root, title)
    entry = f"- {d}: {r['said']} ({CHAT_SOURCE})"
    source = f"- {CHAT_SOURCE} {d}"
    changes: list[str] = []
    if page is None:
        if not r["area"]:
            raise InsightError(f"새 insight에는 area가 필요함: {title}")
        if not r["now"]:
            raise InsightError(f"새 insight에는 now(지금 생각)가 필요함: {title}")
        area, is_new, old = r["area"], True, None
        page = root / "wiki" / area / "insights" / f"{title}.md"
        conf = r["confidence"] or "hunch"
        lines = _new_page(root, r)
        _set_fm(lines, "type", "insight")
        _set_fm(lines, "status", "active")
        _set_fm(lines, "confidence", conf)
        _set_fm(lines, "created", d)
        _set_body(lines, "지금 생각", [r["now"]])
        _set_body(lines, "생각의 변화", [entry])
        _set_body(lines, "보충 (LLM)", r["supplement"])
        _set_body(lines, "연결", r["links"])
        _set_body(lines, "출처", [source])
        changes.append(f"새 페이지 ({area}, {conf})")
    else:
        old = _read_text(page)
        meta = _parse_fm(old)
        rel = page.relative_to(root).as_posix()
        if meta.get("type") != "insight":
            raise InsightError(f"insight가 아닌 같은 제목의 페이지가 있음: {rel}")
        if meta.get("status") == "obsolete":
            raise InsightError(f"폐기된(obsolete) insight는 갱신하지 않음: {rel}")
        parts = page.relative_to(root / "wiki").parts
        area, is_new = (parts[0] if parts[0] in AREAS else r["area"] or "life"), False
        lines = _lines(old)
        if r["now"] and _one_line(" ".join(_bodies(lines, "지금 생각"))) != r["now"]:
            _set_body(lines, "지금 생각", [r["now"]])
            changes.append("지금 생각 바뀜")
        if r["confidence"] and meta.get("confidence") != r["confidence"]:
            changes.append(f"confidence {meta.get('confidence') or '-'}→{r['confidence']}")
            _set_fm(lines, "confidence", r["confidence"])
        if entry not in _bodies(lines, "생각의 변화"):
            _append(lines, "생각의 변화", [entry])
            changes.append("생각 추가")
        have = _bodies(lines, "보충 (LLM)")
        sup = r["supplement"]
        if sup and not any(have[i : i + len(sup)] == sup for i in range(len(have) - len(sup) + 1)):
            _append(lines, "보충 (LLM)", ([""] if have else []) + sup)
            changes.append("보충")
        have_links = {l.strip() for l in _bodies(lines, "연결")}
        new_links = [l for l in r["links"] if l.strip() not in have_links]
        if new_links:
            _append(lines, "연결", new_links)
            changes.append("연결")
        if changes and source not in _bodies(lines, "출처"):
            _append(lines, "출처", [source])
    if changes:
        _set_fm(lines, "updated", d)
    now_text = _one_line(" ".join(_bodies(lines, "지금 생각")))
    return {"page": page, "lines": lines, "old": old, "is_new": is_new, "changes": changes,
            "index": _index_with(root, title, area, now_text, is_new) if changes else None}


def import_result(path: Path, root: Path) -> dict:
    path, root = Path(path), Path(root)
    if not path.is_file():
        raise InsightError(f"import 파일이 없음: {path}")
    r = parse_result(_read_text(path), str(path))
    plan = _plan(r, root)
    rel = plan["page"].relative_to(root).as_posix()
    if plan["changes"]:
        writes = [(plan["page"], _join(plan["lines"]))]
        if plan["index"]:
            writes.append(plan["index"])
        writes.append(_log_with(root, f"- {r['date'].isoformat()} [insight] {r['title']}: {', '.join(plan['changes'])}"))
        _write_all(writes)
    return {"page": rel, "created": plan["is_new"], "changes": plan["changes"], "changed": bool(plan["changes"])}


def _summary(lines: list[str]) -> str:
    return _one_line(" ".join(_bodies(lines, "지금 생각"))) or "-"


def deck(root: Path, date: datetime.date) -> dict:
    root = Path(root)
    groups: dict[str, list[str]] = {a: [] for a in AREAS}
    for p in _wiki_pages(root):
        try:
            text = _read_text(p)
        except InsightError:
            continue
        meta = _parse_fm(text)
        if meta.get("type") != "insight" or meta.get("status") == "obsolete":
            continue
        area = p.relative_to(root / "wiki").parts[0]
        groups.setdefault(area if area in AREAS else "other", []).append(
            f"- [[{p.stem}]] — {meta.get('confidence') or '-'}, {meta.get('updated') or '-'}: {_summary(_lines(text))}")
    out = ["---", "type: insight-deck", "version: 1", f"generated: {date.isoformat()}", "---", "# Insights"]
    for area, items in groups.items():
        out += ["", f"## {area} ({len(items)})", *items]
    _write_all([(root / DECK_PATH, ("\n".join(out) + "\n").encode("utf-8"))])
    return {"path": DECK_PATH, "count": sum(len(v) for v in groups.values())}


def sync(root: Path, date: datetime.date) -> dict:
    root = Path(root)
    inbox = root / "chat" / "inbox"
    done: list[str] = []
    failed: list[dict] = []
    files = sorted(f for f in inbox.iterdir() if f.is_file() and f.name.endswith(".insight.md")) if inbox.is_dir() else []
    for f in files:
        try:
            done.append(import_result(f, root)["page"])
            f.unlink()
        except (InsightError, OSError) as e:
            failed.append({"file": f.relative_to(root).as_posix(), "error": str(e)})
    out = deck(root, date)
    return {"insight": done, "failed": failed, "deck": out["path"]}


def _find_git_top(cwd: Path) -> Path | None:
    for d in [cwd, *cwd.parents]:
        if (d / ".git").exists():
            return d
    return None


def _resolve_root(root_arg: str | None, environ: Mapping[str, str], cwd: Path) -> Path:
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
    except InsightError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    p = argparse.ArgumentParser(prog="insight.py", description="wiki-insight helper")
    p.add_argument("--root", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("result", parents=[common])
    s.add_argument("title")
    s.add_argument("--said", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--area", choices=list(AREAS), default=None)
    s.add_argument("--now", default=None)
    s.add_argument("--confidence", choices=list(RESULT_CONFIDENCE), default=None)
    s.add_argument("--supplement", default="")
    s.add_argument("--link", action="append", default=[])
    s.add_argument("--date", type=_date_arg, default=None)
    s = sub.add_parser("import", parents=[common])
    s.add_argument("file")
    for name in ("sync", "deck"):
        s = sub.add_parser(name, parents=[common])
        s.add_argument("--date", type=_date_arg, default=None)
    return p


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
        date = getattr(args, "date", None) or parse_date("today")
        if args.cmd == "result":
            o = Path(args.out)
            out = make_result(args.title, date, args.said, o if o.is_absolute() else cwd / o, args.area,
                              args.now, args.confidence, args.supplement, args.link)
        elif args.cmd == "import":
            f = Path(args.file)
            out = import_result(f if f.is_absolute() else cwd / f, root)
        elif args.cmd == "sync":
            out = sync(root, date)
            code = 1 if out["failed"] else 0
        else:
            out = deck(root, date)
    except InsightError as e:
        print(f"오류: {e}", file=sys.stderr)
        return e.code
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
