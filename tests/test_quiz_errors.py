"""O13: error guessing G1-G5. Spec fixes few outcomes here, so each test states its interpretation:
no exception other than QuizError(2) escapes, and files never lose existing bytes."""
import datetime

import pytest

import quiz
from quiz_support import (
    D, DS, HEADER_LINE, cli, csv_bytes, deck_bytes, oracle_due, page, result_file, row, snapshot,
    study_root, write, write_csv,
)

A, B = "wiki/study/A.md", "wiki/study/B.md"
FAR = datetime.date(2027, 3, 1)
NOW = datetime.datetime(2026, 11, 5, 9, 30, 15)


def one_page(tmp_path):
    root = tmp_path / "r"
    page(root, A, created="2026-11-01")
    return root


def listed(res, path=A):
    return {i["path"]: i for i in res["items"]}[path]


def test_O13_G1_bom_in_csv_header_due_does_not_crash(tmp_path):
    """Interpretation: a BOM is either tolerated or reported as a warning; the page stays scheduled and
    the data row on line 2 is read either way, and due never rewrites the file."""
    root = one_page(tmp_path)
    raw = b"\xef\xbb\xbf" + (HEADER_LINE + "\n" + row("2026-11-03", A, "good") + "\n").encode()
    write(root / "data" / "reviews.csv", raw)
    res = quiz.due(root, FAR, 10)
    it = listed(res)
    assert it["due"] in {
        oracle_due("2026-11-01", [("2026-11-03", "good")]).isoformat(),
        oracle_due("2026-11-01", []).isoformat(),
    }
    assert isinstance(res["warnings"], list)
    assert csv_bytes(root) == raw


def test_O13_G1_bom_csv_record_preserves_existing_bytes(tmp_path):
    """Interpretation: record appends after the existing bytes or refuses with QuizError; never rewrites them."""
    root = one_page(tmp_path)
    raw = b"\xef\xbb\xbf" + (HEADER_LINE + "\n").encode()
    write(root / "data" / "reviews.csv", raw)
    try:
        quiz.record(root, [(A, "good")], D, NOW)
    except quiz.QuizError as e:
        assert e.code == 2
        assert csv_bytes(root) == raw
        return
    new = csv_bytes(root)
    assert new.startswith(raw)
    assert new.decode("utf-8-sig").splitlines()[-1] == f"{DS},{A},good,review,code,code-2026-11-05T093015"


def test_O13_G2_trailing_empty_line_in_csv(tmp_path):
    """Interpretation: a blank line is ignorable or a warned broken row; valid rows still schedule."""
    root = one_page(tmp_path)
    write(root / "data" / "reviews.csv", HEADER_LINE + "\n" + row("2026-11-03", A, "good") + "\n\n")
    res = quiz.due(root, FAR, 10)
    it = listed(res)
    assert it["due"] == oracle_due("2026-11-01", [("2026-11-03", "good")]).isoformat()
    assert it["reviews"] == 1
    assert res["orphans"] == 0


def test_O13_G2_several_blank_lines_and_whitespace_line(tmp_path):
    root = one_page(tmp_path)
    write(root / "data" / "reviews.csv",
          HEADER_LINE + "\n\n" + row("2026-11-03", A, "good") + "\n   \n\n")
    it = listed(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", [("2026-11-03", "good")]).isoformat()


def test_O13_G2_record_after_trailing_blank_line_keeps_prefix(tmp_path):
    root = one_page(tmp_path)
    old = (HEADER_LINE + "\n" + row("2026-11-03", A, "good") + "\n\n").encode()
    write(root / "data" / "reviews.csv", old)
    quiz.record(root, [(A, "hard")], D, NOW)
    new = csv_bytes(root)
    assert new.startswith(old)
    assert new.decode().splitlines()[-1] == f"{DS},{A},hard,review,code,code-2026-11-05T093015"


def test_O13_G2_record_when_last_row_has_no_newline(tmp_path):
    """Interpretation (F2 append-only): the new row starts on its own line and old bytes are a prefix."""
    root = one_page(tmp_path)
    old = (HEADER_LINE + "\n" + row("2026-11-03", A, "good")).encode()
    write(root / "data" / "reviews.csv", old)
    quiz.record(root, [(A, "hard")], D, NOW)
    new = csv_bytes(root)
    assert new.startswith(old)
    lines = new.decode().splitlines()
    assert lines[1] == row("2026-11-03", A, "good")
    assert lines[2] == f"{DS},{A},hard,review,code,code-2026-11-05T093015"
    assert new.endswith(b"\n")


def test_O13_G3_result_entry_with_extra_pipe_rejected(tmp_path):
    """Interpretation: neither split point gives a concept page plus a valid rating
    (rating 'good | x' or page 'wiki/study/A.md | good'), so the file is rejected as a whole."""
    root = study_root(tmp_path)
    inp = tmp_path / "in"
    for i, line in enumerate(["- wiki/study/A.md | good | x", "- wiki/study/A.md | good |", "- wiki/study/A.md || good"]):
        f = result_file(inp, f"p{i}.quiz.md", entries=[line])
        before = snapshot(root)
        with pytest.raises(quiz.QuizError) as ei:
            quiz.import_result(f, root)
        assert ei.value.code == 2 and f"p{i}.quiz.md" in str(ei.value)
        assert snapshot(root) == before
    assert csv_bytes(root) is None


def test_O13_G3_extra_pipe_in_sync_keeps_file_and_reports(tmp_path):
    root = study_root(tmp_path)
    result_file(root / "chat" / "inbox", "x.quiz.md", entries=["- wiki/study/A.md | good | x"])
    res = quiz.sync(root, D)
    assert len(res["failed"]) == 1 and res["quiz"] == []
    assert (root / "chat" / "inbox" / "x.quiz.md").exists()


def test_O13_G4_equals_in_page_name_splits_on_last_equals(tmp_path, capsys):
    root = tmp_path / "r"
    page(root, "wiki/study/a=b.md", created="2026-11-01")
    rc, out, err = cli(capsys, ["--root", str(root), "record", "--date", DS, "wiki/study/a=b.md=good"])
    assert rc == 0 and err == ""
    assert csv_bytes(root).decode().splitlines()[1].startswith(f"{DS},wiki/study/a=b.md,good,review,code,")


def test_O13_G4_equals_page_with_bad_rating_exit_two(tmp_path, capsys):
    root = tmp_path / "r"
    page(root, "wiki/study/a=b.md", created="2026-11-01")
    rc, out, err = cli(capsys, ["--root", str(root), "record", "--date", DS, "wiki/study/a=b.md=ok"])
    assert rc == 2 and out == "" and err.strip()
    assert csv_bytes(root) is None


def test_O13_G4_equals_result_cli(tmp_path, capsys):
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    rc, out, _ = cli(capsys, ["result", "--out", str(out_dir), "--date", DS, "wiki/study/a=b.md=easy"],
                     {}, tmp_path)
    assert rc == 0
    f = next(out_dir.glob("*.quiz.md"))
    assert f.read_text(encoding="utf-8").endswith("- wiki/study/a=b.md | easy\n")


@pytest.mark.parametrize("value", ["2026-02-30", "2026-04-31", "2025-02-29", "2026-00-10", "2026-11-00"])
def test_O13_G5_impossible_dates_rejected(value):
    with pytest.raises(quiz.QuizError) as ei:
        quiz.parse_date(value)
    assert ei.value.code == 2


def test_O13_G5_leap_day_accepted():
    assert quiz.parse_date("2028-02-29") == datetime.date(2028, 2, 29)


@pytest.mark.parametrize("argv", [
    ["due", "--date", "2026-02-30"],
    ["deck", "--date", "2026-02-30"],
    ["sync", "--date", "2026-02-30"],
    ["record", "--date", "2026-02-30", f"{A}=good"],
])
def test_O13_G5_cli_date_errors_write_nothing(tmp_path, capsys, argv):
    root = study_root(tmp_path)
    before = snapshot(root)
    rc, out, err = cli(capsys, ["--root", str(root), *argv])
    assert rc == 2 and out == "" and err.strip()
    assert snapshot(root) == before


def test_O13_result_file_date_2026_02_30_rejected_on_import(tmp_path):
    root = study_root(tmp_path)
    f = result_file(tmp_path / "in", "d.quiz.md", date="2026-02-30")
    with pytest.raises(quiz.QuizError) as ei:
        quiz.import_result(f, root)
    assert ei.value.code == 2
    assert csv_bytes(root) is None
