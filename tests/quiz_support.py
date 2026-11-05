"""Expected values come from the spec only, never from the implementation."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from learn_support import (  # noqa: F401
    D, DS, PLUGIN_ROOT, SOLO, make_root, result_text, run_main, snapshot, write,
)

QUIZ_DIR = PLUGIN_ROOT / "skills" / "quiz"
QUIZ_PY = QUIZ_DIR / "quiz.py"
HEADER_LINE = "date,page,rating,mode,source,result_id"
NOW = datetime.datetime(2026, 11, 5, 9, 30, 15)
NOW_ID = "2026-11-05T093015"

TEMPLATE_SECTIONS = [
    ("요약", "(한두 문장)"),
    ("내가 정리한 것", "(사용자가 말하거나 자료에서 온 내용)"),
    ("보충 (LLM)", "(LLM 지식으로 덧붙인 내용)"),
    ("이해 기록", ""),
    ("오해와 교정", ""),
    ("연결", "- [[관련 개념]] — 어떤 관계인지"),
    ("출처", "- journal/YYYY/YYYY-MM-DD.md"),
]


def page(root: Path, rel: str, title="__stem__", created=None, updated=None, level=None,
         type_="concept", sections=(), crlf=False, extra_fm=()) -> Path:
    """Write a wiki page. title None -> no H1 line; '__stem__' -> H1 = file stem."""
    p = Path(rel)
    if title == "__stem__":
        title = p.stem
    fm = ["---"]
    if type_ is not None:
        fm.append(f"type: {type_}")
    if created is not None:
        fm.append(f"created: {created}")
    if updated is not None:
        fm.append(f"updated: {updated}")
    if level is not None:
        fm.append(f"level: {level}")
    fm.extend(extra_fm)
    fm.append("---")
    lines = fm
    if title is not None:
        lines = lines + [f"# {title}", ""]
    for heading, body in sections:
        lines += [f"## {heading}", *(body.split("\n") if body else []), ""]
    eol = "\r\n" if crlf else "\n"
    return write(root / rel, eol.join(lines) + eol)


def bare_page(root: Path, rel: str, text: str) -> Path:
    return write(root / rel, text)


def row(date, pg, rating, mode="review", source="code", rid="r1") -> str:
    return f"{date},{pg},{rating},{mode},{source},{rid}"


def write_csv(root: Path, rows, header=True, trailing_newline=True) -> Path:
    lines = ([HEADER_LINE] if header else []) + list(rows)
    text = "\n".join(lines) + ("\n" if trailing_newline else "")
    return write(root / "data" / "reviews.csv", text)


def csv_bytes(root: Path):
    p = root / "data" / "reviews.csv"
    return p.read_bytes() if p.exists() else None


def deck_bytes(root: Path):
    p = root / "chat" / "deck.md"
    return p.read_bytes() if p.exists() else None


def oracle_due(created: str, rows) -> datetime.date:
    from fsrs import Card, Rating, Scheduler

    sch = Scheduler(desired_retention=0.9, learning_steps=(), relearning_steps=(), enable_fuzzing=False)
    ratings = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}
    events = [(created, 0, "good")] + [(d, 1, r) for d, r in rows]
    events = sorted(events, key=lambda e: (e[0], e[1]))  # stable: synthetic first on ties, then file order
    card = Card()
    for d, _, r in events:
        y, m, dd = (int(x) for x in d.split("-"))
        when = datetime.datetime(y, m, dd, 12, 0, tzinfo=datetime.timezone.utc)
        card, _log = sch.review_card(card, ratings[r], review_datetime=when)
    return card.due.astimezone(datetime.timezone.utc).date()


def by_path(items):
    return {i["path"]: i for i in items}


def result_file(dirpath: Path, name="r.quiz.md", entries=("- wiki/study/A.md | good",), **over) -> Path:
    """A quiz-result file; pass key=None to drop a key. entries are raw body lines."""
    kv = {
        "type": "quiz-result", "version": "1", "id": "chat-2026-11-04T090000", "date": "2026-11-04",
        "mode": "review", "source": "chat",
    }
    kv.update(over)
    lines = ["---"] + [f"{k}: {v}" for k, v in kv.items() if v is not None] + ["---"] + list(entries)
    return write(dirpath / name, "\n".join(lines) + "\n")


def study_root(tmp_path: Path, name="root", pages=("A", "B"), created="2026-11-01") -> Path:
    root = tmp_path / name
    for p in pages:
        page(root, f"wiki/study/{p}.md", created=created)
    return root


def expect_quiz_error(fn, base: Path, contains=()):
    import quiz

    before = snapshot(base) if base.exists() else None
    with pytest.raises(quiz.QuizError) as ei:
        fn()
    assert ei.value.code == 2
    for c in contains:
        assert c in str(ei.value), (c, str(ei.value))
    if before is not None:
        assert snapshot(base) == before
    return str(ei.value)


def cli(capsys, argv, environ=None, cwd=None):
    import quiz

    rc = run_main(quiz.main, argv, environ, cwd)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def one_json(out: str):
    assert out.endswith("\n") and out.count("\n") == 1, out
    return json.loads(out)


def oracle_events_due(events) -> datetime.date:
    from fsrs import Card, Rating, Scheduler

    sch = Scheduler(desired_retention=0.9, learning_steps=(), relearning_steps=(), enable_fuzzing=False)
    ratings = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}
    card = Card()
    for d, r in events:
        y, m, dd = (int(x) for x in d.split("-"))
        when = datetime.datetime(y, m, dd, 12, 0, tzinfo=datetime.timezone.utc)
        card, _ = sch.review_card(card, ratings[r], review_datetime=when)
    return card.due.astimezone(datetime.timezone.utc).date()
