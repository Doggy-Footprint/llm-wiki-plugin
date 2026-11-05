"""O7: record."""
import datetime
import re

import pytest

import quiz
from quiz_support import (
    D, DS, HEADER_LINE, NOW, NOW_ID, csv_bytes, deck_bytes, expect_quiz_error, page, row, snapshot,
    study_root, write, write_csv,
)

A, B = "wiki/study/A.md", "wiki/study/B.md"


def test_O7_C13_two_entries_csv_absent_creates_header(tmp_path):
    root = study_root(tmp_path)
    assert csv_bytes(root) is None
    res = quiz.record(root, [(A, "good"), (B, "again")], D, NOW)
    rid = f"code-{NOW_ID}"
    assert res == {"added": 2, "result_id": rid, "deck": "chat/deck.md"}
    assert csv_bytes(root) == (
        f"{HEADER_LINE}\n{DS},{A},good,review,code,{rid}\n{DS},{B},again,review,code,{rid}\n"
    ).encode("utf-8")


def test_O7_result_id_uses_now_time_and_date_arg(tmp_path):
    root = study_root(tmp_path)
    res = quiz.record(root, [(A, "easy")], datetime.date(2026, 11, 4), datetime.datetime(2026, 11, 5, 23, 59, 58))
    assert res["result_id"] == "code-2026-11-04T235958"
    assert csv_bytes(root).decode().splitlines()[1] == "2026-11-04,wiki/study/A.md,easy,review,code,code-2026-11-04T235958"


def test_O7_now_defaults_to_clock(tmp_path):
    root = study_root(tmp_path)
    res = quiz.record(root, [(A, "good")], D)
    assert re.fullmatch(r"code-2026-11-05T\d{6}", res["result_id"])
    assert csv_bytes(root).decode().splitlines()[1].endswith("," + res["result_id"])


def test_O7_appends_without_changing_existing_bytes(tmp_path):
    root = study_root(tmp_path)
    old = f"{HEADER_LINE}\n2026-11-02,{A},good,review,chat,chat-x\n".encode()
    write(root / "data" / "reviews.csv", old)
    quiz.record(root, [(B, "hard")], D, NOW)
    new = csv_bytes(root)
    assert new.startswith(old)
    assert new[len(old):] == f"{DS},{B},hard,review,code,code-{NOW_ID}\n".encode()


def test_O7_deck_rewritten_and_reflects_new_review(tmp_path):
    root = study_root(tmp_path, pages=("A",))  # created 11-01 -> due 11-03
    write(root / "chat" / "deck.md", "STALE")
    quiz.record(root, [(A, "good")], D, NOW)
    text = deck_bytes(root).decode()
    assert text.startswith("---\ntype: quiz-deck\nversion: 1\ngenerated: 2026-11-05\n---\n")
    assert "STALE" not in text
    assert "## Due (0)" in text
    assert (root / "chat" / "inbox" / ".gitkeep").exists()


def test_O7_deck_created_when_absent(tmp_path):
    root = study_root(tmp_path)
    quiz.record(root, [(A, "good")], D, NOW)
    assert deck_bytes(root) is not None


def test_O7_single_entry_ok(tmp_path):
    root = study_root(tmp_path)
    assert quiz.record(root, [(B, "hard")], D, NOW)["added"] == 1


@pytest.mark.parametrize("entries,label", [
    ([("wiki/study/Nope.md", "good")], "unknown page"),
    ([(A, "good"), ("wiki/study/Nope.md", "good")], "valid then unknown page"),
    ([("wiki/journal/J.md", "good")], "non-concept page"),
    ([("wiki/index.md", "good")], "index page"),
    ([("../x.md", "good")], "dotdot"),
    ([("/abs/A.md", "good")], "absolute"),
    ([(A, "ok")], "bad rating"),
    ([(A, "good"), (B, "ok")], "valid then bad rating"),
    ([(A, "")], "empty rating"),
    ([(A, "good"), (A, "again")], "duplicate page"),
    ([(A, "good"), (B, "good"), (A, "good")], "duplicate later"),
    ([], "no entries"),
])
def test_O7_C14_rejected_leaves_files_unchanged(tmp_path, entries, label):
    root = study_root(tmp_path)
    page(root, "wiki/journal/J.md", type_="journal")
    write_csv(root, [row("2026-11-02", A, "good", rid="old")])
    write(root / "chat" / "deck.md", "OLD DECK\n")
    c0, d0 = csv_bytes(root), deck_bytes(root)
    expect_quiz_error(lambda: quiz.record(root, entries, D, NOW), root)
    assert csv_bytes(root) == c0 and deck_bytes(root) == d0, label


@pytest.mark.parametrize("entries", [
    [(A, "ok")], [], [(A, "good"), (A, "good")], [("wiki/study/Nope.md", "good")],
])
def test_O7_C14_rejected_with_csv_absent_creates_nothing(tmp_path, entries):
    root = study_root(tmp_path)
    before = snapshot(root)
    expect_quiz_error(lambda: quiz.record(root, entries, D, NOW), root)
    assert snapshot(root) == before
    assert csv_bytes(root) is None and deck_bytes(root) is None
    assert not (root / "data").exists() and not (root / "chat").exists()


@pytest.mark.parametrize("rating", ["again", "hard", "good", "easy"])
def test_O7_each_rating_written(tmp_path, rating):
    root = study_root(tmp_path)
    quiz.record(root, [(A, rating)], D, NOW)
    assert f",{A},{rating},review,code," in csv_bytes(root).decode()


import os


def data_listing(root):
    d = root / "data"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def test_O7_F2_record_leaves_only_reviews_csv_in_data(tmp_path):
    root = study_root(tmp_path)
    quiz.record(root, [(A, "good")], D, NOW)
    assert data_listing(root) == ["reviews.csv"]
    quiz.record(root, [(B, "good")], D, datetime.datetime(2026, 11, 5, 10, 0, 0))
    assert data_listing(root) == ["reviews.csv"]


def test_O7_F2_import_leaves_only_reviews_csv_in_data(tmp_path):
    from quiz_support import result_file

    root = study_root(tmp_path)
    quiz.import_result(result_file(tmp_path / "in", "a.quiz.md", id="i1"), root)
    assert data_listing(root) == ["reviews.csv"]
    quiz.import_result(result_file(tmp_path / "in", "b.quiz.md", id="i2", entries=["- wiki/study/B.md | hard"]), root)
    assert data_listing(root) == ["reviews.csv"]


def test_O7_F2_os_replace_failure_keeps_original_csv_and_no_temp(tmp_path, monkeypatch):
    root = study_root(tmp_path)
    write_csv(root, [row("2026-11-02", A, "good", rid="old")])
    old = csv_bytes(root)

    def boom(*a, **k):
        raise OSError("replace blocked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(Exception):
        quiz.record(root, [(B, "easy")], D, NOW)
    assert csv_bytes(root) == old
    assert data_listing(root) == ["reviews.csv"]


def test_O7_F2_os_replace_failure_csv_absent_leaves_no_csv_or_temp(tmp_path, monkeypatch):
    root = study_root(tmp_path)

    def boom(*a, **k):
        raise OSError("replace blocked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(Exception):
        quiz.record(root, [(A, "easy")], D, NOW)
    assert csv_bytes(root) is None
    assert data_listing(root) == []


def test_O7_F2_os_replace_failure_import_keeps_original(tmp_path, monkeypatch):
    from quiz_support import result_file

    root = study_root(tmp_path)
    write_csv(root, [row("2026-11-02", A, "good", rid="old")])
    old = csv_bytes(root)
    f = result_file(tmp_path / "in", "a.quiz.md", id="i1", entries=["- wiki/study/B.md | hard"])

    def boom(*a, **k):
        raise OSError("replace blocked")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(Exception):
        quiz.import_result(f, root)
    assert csv_bytes(root) == old
    assert data_listing(root) == ["reviews.csv"]


BAD_NAMES = ["a|b", "a\\b", "a\nb", "a\tb", "a\x01b", "a\rb"]


@pytest.mark.parametrize("stem", BAD_NAMES, ids=[repr(s) for s in BAD_NAMES])
def test_O7_record_rejects_control_backslash_pipe_in_page(tmp_path, stem):
    root = study_root(tmp_path)
    rel = f"wiki/study/{stem}.md"
    try:
        page(root, rel, created="2026-11-01")  # the page really exists
    except OSError:
        pytest.skip("filesystem cannot hold this name")
    expect_quiz_error(lambda: quiz.record(root, [(rel, "good")], D, NOW), root)
    assert csv_bytes(root) is None and deck_bytes(root) is None


@pytest.mark.parametrize("stem", BAD_NAMES, ids=[repr(s) for s in BAD_NAMES])
def test_O7_make_result_rejects_control_backslash_pipe_in_page(tmp_path, stem):
    out = tmp_path / "o"
    out.mkdir()
    with pytest.raises(quiz.QuizError) as ei:
        quiz.make_result([(f"wiki/study/{stem}.md", "good")], D, out, NOW)
    assert ei.value.code == 2 and list(out.iterdir()) == []


@pytest.mark.parametrize("stem", ["a|b", "a\\b", "a\tb", "a\x01b"])
def test_O7_result_file_line_rejects_control_backslash_pipe_in_page(tmp_path, stem):
    from quiz_support import result_file

    root = study_root(tmp_path)
    rel = f"wiki/study/{stem}.md"
    try:
        page(root, rel, created="2026-11-01")
    except OSError:
        pytest.skip("filesystem cannot hold this name")
    f = result_file(tmp_path / "in", "bad.quiz.md", entries=[f"- {rel} | good"])
    expect_quiz_error(lambda: quiz.import_result(f, root), root)
    assert csv_bytes(root) is None


def test_O7_cli_record_rejects_newline_in_page(tmp_path, capsys):
    from quiz_support import cli

    root = study_root(tmp_path)
    page(root, "wiki/study/a\nb.md", created="2026-11-01")
    rc, out, err = cli(capsys, ["--root", str(root), "record", "--date", DS, "wiki/study/a\nb.md=good"])
    assert rc == 2 and out == "" and err.strip()
    assert csv_bytes(root) is None
