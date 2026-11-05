import datetime
import re
from pathlib import Path

import pytest

import quiz
from quiz_support import (
    D, DS, HEADER_LINE, NOW, NOW_ID, csv_bytes, deck_bytes, expect_quiz_error, page, result_file, row,
    snapshot, study_root, write, write_csv,
)

A, B = "wiki/study/A.md", "wiki/study/B.md"


def made_path(res, out):
    p = Path(res["path"])
    return p if p.exists() else out / p.name


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out"
    o.mkdir()
    return o


def test_O8_F8_exact_text_and_return(out):
    res = quiz.make_result([(A, "good"), (B, "again")], D, out, NOW)
    p = made_path(res, out)
    assert p.name == "2026-11-05-093015.quiz.md"
    assert res["id"] == f"chat-{NOW_ID}"
    assert p.read_bytes() == (
        "---\ntype: quiz-result\nversion: 1\nid: chat-2026-11-05T093015\ndate: 2026-11-05\n"
        "mode: review\nsource: chat\n---\n- wiki/study/A.md | good\n- wiki/study/B.md | again\n"
    ).encode("utf-8")


def test_O8_F8_date_arg_not_now_date(out):
    res = quiz.make_result([(A, "easy")], datetime.date(2026, 11, 4), out, NOW)
    p = made_path(res, out)
    assert p.name == "2026-11-04-093015.quiz.md"
    assert res["id"] == "chat-2026-11-04T093015"
    assert "id: chat-2026-11-04T093015\ndate: 2026-11-04\n" in p.read_text(encoding="utf-8")


def test_O8_F8_now_defaults_to_clock(out):
    res = quiz.make_result([(A, "hard")], D, out)
    p = made_path(res, out)
    assert re.fullmatch(r"2026-11-05-\d{6}\.quiz\.md", p.name)
    assert res["id"] == "chat-2026-11-05T" + p.name[len("2026-11-05-"):-len(".quiz.md")]


def test_O8_C23_name_clash_suffixes(out):
    r1 = quiz.make_result([(A, "good")], D, out, NOW)
    r2 = quiz.make_result([(A, "hard")], D, out, NOW)
    r3 = quiz.make_result([(A, "easy")], D, out, NOW)
    assert [made_path(r, out).name for r in (r1, r2, r3)] == [
        "2026-11-05-093015.quiz.md", "2026-11-05-093015-2.quiz.md", "2026-11-05-093015-3.quiz.md",
    ]
    assert [r["id"] for r in (r1, r2, r3)] == [
        "chat-2026-11-05T093015", "chat-2026-11-05T093015-2", "chat-2026-11-05T093015-3",
    ]
    t2 = made_path(r2, out).read_text(encoding="utf-8")
    assert "id: chat-2026-11-05T093015-2\n" in t2 and t2.endswith("- wiki/study/A.md | hard\n")
    assert made_path(r1, out).read_text(encoding="utf-8").endswith("- wiki/study/A.md | good\n")


def test_O8_F8_nested_page_and_dots_inside_segment_accepted(out):
    res = quiz.make_result([("wiki/a/b/Cd.md", "good"), ("wiki/a..b.md", "easy")], D, out, NOW)
    t = made_path(res, out).read_text(encoding="utf-8")
    assert t.endswith("- wiki/a/b/Cd.md | good\n- wiki/a..b.md | easy\n")


@pytest.mark.parametrize("entries", [
    [("notwiki/A.md", "good")],
    [("wiki/../A.md", "good")],
    [("wiki/a/../b.md", "good")],
    [("wiki/A.txt", "good")],
    [("wiki/A", "good")],
    [("/wiki/A.md", "good")],
    [("../wiki/A.md", "good")],
    [("A.md", "good")],
    [(A, "bad")],
    [(A, "")],
    [(A, "good"), (B, "bad")],
    [(A, "good"), (A, "good")],
    [(A, "good"), (B, "good"), (A, "again")],
    [],
])
def test_O8_C24_rejected_no_file(out, entries):
    before = snapshot(out)
    with pytest.raises(quiz.QuizError) as ei:
        quiz.make_result(entries, D, out, NOW)
    assert ei.value.code == 2
    assert snapshot(out) == before and list(out.iterdir()) == []


@pytest.fixture
def env(tmp_path):
    root = study_root(tmp_path)
    inp = tmp_path / "in"
    inp.mkdir()
    return root, inp


def test_O8_C15_make_result_then_import(tmp_path, out):
    root = study_root(tmp_path)
    res = quiz.make_result([(A, "good"), (B, "again")], datetime.date(2026, 11, 4), out, NOW)
    imp = quiz.import_result(made_path(res, out), root)
    assert imp == {"added": 2, "skipped": False, "result_id": "chat-2026-11-04T093015"}
    assert csv_bytes(root) == (
        f"{HEADER_LINE}\n"
        "2026-11-04,wiki/study/A.md,good,review,chat,chat-2026-11-04T093015\n"
        "2026-11-04,wiki/study/B.md,again,review,chat,chat-2026-11-04T093015\n"
    ).encode("utf-8")
    assert deck_bytes(root) is None


def test_O8_import_appends_to_existing_csv_bytes(env):
    root, inp = env
    write_csv(root, [row("2026-11-02", A, "good", rid="old")])
    old = csv_bytes(root)
    f = result_file(inp, source="code", date="2026-11-03", id="code-x", entries=["- wiki/study/B.md | hard"])
    quiz.import_result(f, root)
    new = csv_bytes(root)
    assert new.startswith(old)
    assert new[len(old):] == b"2026-11-03,wiki/study/B.md,hard,review,code,code-x\n"


def test_O8_C16_second_import_is_skipped(env):
    root, inp = env
    f = result_file(inp, entries=["- wiki/study/A.md | good", "- wiki/study/B.md | easy"])
    first = quiz.import_result(f, root)
    assert first["added"] == 2 and first["skipped"] is False
    snap = snapshot(root)
    again = quiz.import_result(f, root)
    assert again == {"added": 0, "skipped": True, "result_id": "chat-2026-11-04T090000"}
    assert snapshot(root) == snap


def test_O8_C16_id_present_from_record_is_skipped_even_with_other_entries(env):
    root, inp = env
    quiz.record(root, [(A, "good")], D, NOW)
    rid = f"code-{NOW_ID}"
    before = csv_bytes(root)
    f = result_file(inp, id=rid, source="code", entries=["- wiki/study/B.md | again"])
    res = quiz.import_result(f, root)
    assert res["skipped"] is True and res["added"] == 0 and res["result_id"] == rid
    assert csv_bytes(root) == before


def test_O8_C16_different_id_same_content_is_imported(env):
    root, inp = env
    quiz.import_result(result_file(inp, "a.quiz.md", id="id-1"), root)
    res = quiz.import_result(result_file(inp, "b.quiz.md", id="id-2"), root)
    assert res["added"] == 1 and res["skipped"] is False
    assert csv_bytes(root).decode().count("\n") == 3


BAD = [
    ("wrong type", dict(type="learn-result"), None),
    ("missing type", dict(type=None), None),
    ("version 2", dict(version="2"), None),
    ("missing version", dict(version=None), None),
    ("missing id", dict(id=None), None),
    ("empty id", dict(id=""), None),
    ("missing date", dict(date=None), None),
    ("invalid date", dict(date="2026-02-30"), None),
    ("malformed date", dict(date="11/04/2026"), None),
    ("missing mode", dict(mode=None), None),
    ("wrong mode", dict(mode="explore"), None),
    ("missing source", dict(source=None), None),
    ("wrong source", dict(source="web"), None),
    ("no entries", {}, []),
    ("only prose", {}, ["그냥 문장"]),
    ("unknown page", {}, ["- wiki/study/Nope.md | good"]),
    ("valid then unknown page", {}, ["- wiki/study/A.md | good", "- wiki/study/Nope.md | good"]),
    ("non-concept page", {}, ["- wiki/journal/J.md | good"]),
    ("bad rating meh", {}, ["- wiki/study/A.md | meh"]),
    ("valid then bad rating", {}, ["- wiki/study/A.md | good", "- wiki/study/B.md | meh"]),
    ("empty rating", {}, ["- wiki/study/A.md |"]),
    ("duplicate page", {}, ["- wiki/study/A.md | good", "- wiki/study/A.md | again"]),
    ("dotdot page", {}, ["- ../outside.md | good"]),
    ("dotdot inside wiki", {}, ["- wiki/../../outside.md | good"]),
    ("absolute page", {}, ["- /abs/A.md | good"]),
    ("outside wiki page", {}, ["- notwiki/N.md | good"]),
    ("index page", {}, ["- wiki/index.md | good"]),
]


@pytest.mark.parametrize("label,over,entries", BAD, ids=[b[0] for b in BAD])
def test_O8_C17_violations_rejected(tmp_path, label, over, entries):
    root = study_root(tmp_path)
    page(root, "wiki/journal/J.md", type_="journal")
    page(root, "notwiki/N.md", created="2026-11-01")
    page(tmp_path, "outside.md", created="2026-11-01")
    write_csv(root, [row("2026-11-02", A, "good", rid="old")])
    inp = tmp_path / "in"
    inp.mkdir()
    kw = dict(over)
    if entries is not None:
        kw["entries"] = entries
    f = result_file(inp, "bad.quiz.md", **kw)
    expect_quiz_error(lambda: quiz.import_result(f, root), root, contains=("bad.quiz.md",))


def test_O8_C17_non_utf8_rejected(tmp_path):
    root = study_root(tmp_path)
    inp = tmp_path / "in"
    inp.mkdir()
    good = result_file(inp, "good.quiz.md").read_bytes()
    f = write(inp / "bad.quiz.md", good + b"\xff\xfe- wiki/study/B.md | good\n")
    expect_quiz_error(lambda: quiz.import_result(f, root), root, contains=("bad.quiz.md",))
    assert csv_bytes(root) is None


def test_O8_C17_no_frontmatter_rejected(tmp_path):
    root = study_root(tmp_path)
    inp = tmp_path / "in"
    inp.mkdir()
    f = write(inp / "bad.quiz.md", "- wiki/study/A.md | good\n")
    expect_quiz_error(lambda: quiz.import_result(f, root), root, contains=("bad.quiz.md",))
    assert csv_bytes(root) is None


def test_O8_C17_rejects_leave_csv_absent(env):
    root, inp = env
    f = result_file(inp, "bad.quiz.md", version="2")
    expect_quiz_error(lambda: quiz.import_result(f, root), root)
    assert csv_bytes(root) is None and not (root / "data").exists()


@pytest.mark.parametrize("line,rating", [
    ("-  wiki/study/A.md|GOOD", "good"),
    ("- wiki/study/A.md|good", "good"),
    ("- wiki/study/A.md |good", "good"),
    ("- wiki/study/A.md| good", "good"),
    ("- wiki/study/A.md  |  Hard  ", "hard"),
    ("- wiki/study/A.md | EASY", "easy"),
    ("- wiki/study/A.md | Again", "again"),
    ("- wiki/study/A.md | aGaIn ", "again"),
])
def test_O8_C18_spacing_and_case_variants(env, line, rating):
    root, inp = env
    f = result_file(inp, entries=[line])
    res = quiz.import_result(f, root)
    assert res["added"] == 1
    assert csv_bytes(root) == (
        f"{HEADER_LINE}\n2026-11-04,{A},{rating},review,chat,chat-2026-11-04T090000\n"
    ).encode()


def test_O8_C18_crlf_file(env):
    root, inp = env
    text = (
        "---\r\ntype: quiz-result\r\nversion: 1\r\nid: chat-crlf\r\ndate: 2026-11-04\r\nmode: review\r\n"
        "source: chat\r\n---\r\n-  wiki/study/A.md|GOOD\r\n- wiki/study/B.md | again\r\n"
    )
    f = write(inp / "crlf.quiz.md", text)
    res = quiz.import_result(f, root)
    assert res == {"added": 2, "skipped": False, "result_id": "chat-crlf"}
    assert csv_bytes(root) == (
        f"{HEADER_LINE}\n2026-11-04,{A},good,review,chat,chat-crlf\n2026-11-04,{B},again,review,chat,chat-crlf\n"
    ).encode()


def test_O8_source_code_and_chat_both_accepted(env):
    root, inp = env
    quiz.import_result(result_file(inp, "c.quiz.md", id="i1", source="code"), root)
    quiz.import_result(result_file(inp, "d.quiz.md", id="i2", source="chat",
                                   entries=["- wiki/study/B.md | good"]), root)
    lines = csv_bytes(root).decode().splitlines()
    assert lines[1].endswith(",review,code,i1") and lines[2].endswith(",review,chat,i2")


def test_O8_v3_missing_import_file_is_quiz_error(tmp_path):
    root = study_root(tmp_path)
    missing = tmp_path / "in" / "nope.quiz.md"
    expect_quiz_error(lambda: quiz.import_result(missing, root), root)
    assert csv_bytes(root) is None


@pytest.mark.parametrize("line", ["- wiki/study/A.md", "- wiki/study/A.md good", "-", "- "])
def test_O8_dash_line_without_pipe_is_not_an_entry(tmp_path, line):
    """Interpretation: a `- ` body line with no `|` is not an entry, so a file whose only such line
    is it has no entries and is rejected (spec: >=1 entry line `- <page> | <rating>`)."""
    root = study_root(tmp_path)
    f = result_file(tmp_path / "in", "np.quiz.md", entries=[line])
    expect_quiz_error(lambda: quiz.import_result(f, root), root, contains=("np.quiz.md",))
    assert csv_bytes(root) is None


def test_O8_v3_quoted_frontmatter_values_in_result_file(tmp_path):
    root = study_root(tmp_path)
    f = result_file(tmp_path / "in", "q.quiz.md", type='"quiz-result"', version="'1'", id='"id-q"',
                    date='"2026-11-04"', mode="'review'", source='"chat"')
    res = quiz.import_result(f, root)
    assert res == {"added": 1, "skipped": False, "result_id": "id-q"}
    assert csv_bytes(root).decode().splitlines()[1] == f"2026-11-04,{A},good,review,chat,id-q"
