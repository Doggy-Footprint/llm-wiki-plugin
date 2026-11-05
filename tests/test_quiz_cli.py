"""O10: CLI commands, root resolution, exit codes, no-fsrs paths; parse_date."""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import quiz
from quiz_support import (
    D, DS, HEADER_LINE, QUIZ_DIR, QUIZ_PY, cli, csv_bytes, deck_bytes, one_json, page, result_file,
    snapshot, write,
)

A, B = "wiki/study/A.md", "wiki/study/B.md"


def mkroot(tmp_path, name="root"):
    root = tmp_path / name
    page(root, A, title="알파", level=2, created="2026-11-01",
         sections=[("요약", "요약 문장"), ("연결", "- [[Xtarget]] — r")])
    page(root, B, created="2026-11-01")
    return root


# ---------------- commands ----------------

def test_O10_C25_due(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "due", "--date", "2026-11-03", "--limit", "1"])
    assert rc == 0 and err == ""
    d = one_json(out)
    assert set(d) == {"items", "warnings", "orphans"}
    assert [i["path"] for i in d["items"]] == [A]
    assert d["items"][0]["title"] == "알파" and "알파" in out  # ensure_ascii=False
    assert d["items"][0]["due"] == "2026-11-03"


def test_O10_C25_due_default_args(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, _ = cli(capsys, ["--root", str(root), "due", "--date", "2026-11-03"])
    assert rc == 0 and len(one_json(out)["items"]) == 2


def test_O10_C25_card(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "card", A])
    assert rc == 0 and err == ""
    assert one_json(out) == {"path": A, "title": "알파", "level": 2, "summary": "요약 문장", "mine": "",
                             "misconceptions": [], "links": ["Xtarget"]}


def test_O10_C25_frontier(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "frontier", "--limit", "3"])
    assert rc == 0 and err == ""
    assert one_json(out) == [{"title": "Xtarget", "from": ["알파"], "max_level": 2}]


def test_O10_C25_record(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "record", "--date", DS, f"{A}=good", f"{B}=again"])
    assert rc == 0 and err == ""
    d = one_json(out)
    assert d["added"] == 2 and d["deck"] == "chat/deck.md"
    assert re.fullmatch(r"code-2026-11-05T\d{6}", d["result_id"])
    lines = csv_bytes(root).decode().splitlines()
    assert lines[0] == HEADER_LINE
    assert lines[1] == f"{DS},{A},good,review,code,{d['result_id']}"
    assert lines[2] == f"{DS},{B},again,review,code,{d['result_id']}"
    assert deck_bytes(root) is not None


def test_O10_C25_result_and_import_roundtrip(tmp_path, capsys):
    root = mkroot(tmp_path)
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    rc, out, err = cli(capsys, ["--root", str(root), "result", "--out", str(out_dir), "--date", DS,
                                f"{A}=hard", f"{B}=easy"])
    assert rc == 0 and err == ""
    d = one_json(out)
    assert set(d) == {"path", "id"}
    files = list(out_dir.glob("*.quiz.md"))
    assert len(files) == 1 and Path(d["path"]).name == files[0].name
    assert re.fullmatch(r"chat-2026-11-05T\d{6}", d["id"])
    assert f"- {A} | hard\n- {B} | easy\n" in files[0].read_text(encoding="utf-8")
    assert csv_bytes(root) is None

    rc, out, err = cli(capsys, ["--root", str(root), "import", str(files[0])])
    assert rc == 0 and err == ""
    assert one_json(out) == {"added": 2, "skipped": False, "result_id": d["id"]}
    assert f"{DS},{A},hard,review,chat,{d['id']}" in csv_bytes(root).decode()


def test_O10_C25_import_relative_file_uses_cwd(tmp_path, capsys):
    root = mkroot(tmp_path)
    inp = tmp_path / "in"
    f = result_file(inp, "r.quiz.md", id="rel-1")
    rc, out, _ = cli(capsys, ["--root", str(root), "import", "r.quiz.md"], {}, inp)
    assert rc == 0 and one_json(out)["result_id"] == "rel-1"


def test_O10_C25_sync_ok_exit_zero(tmp_path, capsys):
    root = mkroot(tmp_path)
    result_file(root / "chat" / "inbox", "a.quiz.md", id="id-a")
    rc, out, err = cli(capsys, ["--root", str(root), "sync", "--date", DS])
    assert rc == 0 and err == ""
    assert one_json(out) == {"quiz": ["id-a"], "learn": [], "failed": [], "deck": "chat/deck.md"}


def test_O10_C25_sync_failure_exit_one_and_json(tmp_path, capsys):
    root = mkroot(tmp_path)
    result_file(root / "chat" / "inbox", "bad.quiz.md", version="2")
    rc, out, err = cli(capsys, ["--root", str(root), "sync", "--date", DS])
    assert rc == 1
    d = one_json(out)
    assert [f["file"] for f in d["failed"]] == ["chat/inbox/bad.quiz.md"] and d["deck"] == "chat/deck.md"
    assert (root / "chat" / "inbox" / "bad.quiz.md").exists()


def test_O10_C25_deck(tmp_path, capsys):
    root = mkroot(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "deck", "--date", DS])
    assert rc == 0 and err == ""
    d = one_json(out)
    assert d["path"] == "chat/deck.md" and d["due"] == 2 and d["frontier"] == 1 and d["known"] == 2
    assert d["chars"] == len(deck_bytes(root).decode("utf-8"))


def test_O10_default_date_is_today_with_rollover(tmp_path, capsys):
    """--date omitted: both due and deck accept it (value comes from the clock, not asserted)."""
    root = mkroot(tmp_path)
    rc, out, _ = cli(capsys, ["--root", str(root), "due"])
    assert rc == 0 and "items" in one_json(out)
    rc, out, _ = cli(capsys, ["--root", str(root), "deck"])
    assert rc == 0 and re.search(r"^generated: \d{4}-\d{2}-\d{2}$", deck_bytes(root).decode(), re.M)


# ---------------- root resolution ----------------

def test_O10_root_flag_beats_env(tmp_path, capsys):
    root = mkroot(tmp_path, "real")
    decoy = tmp_path / "decoy"
    (decoy / "wiki").mkdir(parents=True)
    rc, out, _ = cli(capsys, ["--root", str(root), "due", "--date", "2026-11-03"], {"LLM_WIKI_ROOT": str(decoy)}, tmp_path)
    assert rc == 0 and len(one_json(out)["items"]) == 2


def test_O10_root_from_env(tmp_path, capsys):
    root = mkroot(tmp_path, "real")
    rc, out, _ = cli(capsys, ["due", "--date", "2026-11-03"], {"LLM_WIKI_ROOT": str(root)}, tmp_path)
    assert rc == 0 and len(one_json(out)["items"]) == 2


def test_O10_root_from_git_top(tmp_path, capsys):
    root = mkroot(tmp_path, "gitroot")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    sub = root / "wiki" / "study"
    rc, out, _ = cli(capsys, ["due", "--date", "2026-11-03"], {}, sub)
    assert rc == 0 and len(one_json(out)["items"]) == 2
    rc, out, _ = cli(capsys, ["deck", "--date", DS], {}, sub)
    assert rc == 0 and (root / "chat" / "deck.md").exists()
    assert not (sub / "chat").exists()


def test_O10_root_falls_back_to_cwd(tmp_path, capsys):
    root = mkroot(tmp_path, "plain")
    rc, out, _ = cli(capsys, ["due", "--date", "2026-11-03"], {}, root)
    assert rc == 0 and len(one_json(out)["items"]) == 2


def test_O10_Q8_fresh_root_with_only_wiki(tmp_path, capsys):
    root = tmp_path / "fresh"
    (root / "wiki").mkdir(parents=True)
    for argv in (["due", "--date", DS], ["frontier"], ["sync", "--date", DS], ["deck", "--date", DS]):
        rc, out, err = cli(capsys, ["--root", str(root), *argv])
        assert rc == 0 and err == "", argv
        one_json(out)
    assert csv_bytes(root) is None and not (root / "data").exists()
    assert (root / "chat" / "deck.md").exists()


# ---------------- errors ----------------

ERRORS = [
    ["due", "--limit", "0"],
    ["due", "--limit", "11"],
    ["due", "--limit", "abc"],
    ["due", "--date", "2026-02-30"],
    ["due", "--date", "not-a-date"],
    ["card", "../x.md"],
    ["card", "wiki/study/Nope.md"],
    ["card", "/abs.md"],
    ["frontier", "--limit", "0"],
    ["frontier", "--limit", "11"],
    ["record", "--date", DS, f"{A}=ok"],
    ["record", "--date", DS, "wiki/study/Nope.md=good"],
    ["record", "--date", DS, "noequals"],
    ["record", "--date", DS],
    ["record", "--date", DS, f"{A}=good", f"{A}=again"],
    ["record", "--date", "2026-02-30", f"{A}=good"],
    ["import", "/nonexistent/file.quiz.md"],
    ["sync", "--date", "2026-13-01"],
    ["deck", "--date", "nope"],
    ["bogus"],
]


@pytest.mark.parametrize("argv", ERRORS, ids=[" ".join(a) for a in ERRORS])
def test_O10_C25_errors_exit_two(tmp_path, capsys, argv):
    root = mkroot(tmp_path)
    before = snapshot(root)
    rc, out, err = cli(capsys, ["--root", str(root), *argv])
    assert rc == 2
    assert out == "" and err.strip() != ""
    assert snapshot(root) == before


def test_O10_C25_result_errors_exit_two_without_file(tmp_path, capsys):
    root = mkroot(tmp_path)
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    for entries in (["wiki/../A.md=good"], ["notwiki/A.md=good"], ["wiki/A.txt=good"], [f"{A}=bad"],
                    [f"{A}=good", f"{A}=good"], []):
        rc, out, err = cli(capsys, ["--root", str(root), "result", "--out", str(out_dir), "--date", DS, *entries])
        assert rc == 2 and out == "" and err.strip() != "", entries
    assert list(out_dir.iterdir()) == []


def test_O10_import_bad_file_exit_two(tmp_path, capsys):
    root = mkroot(tmp_path)
    f = result_file(tmp_path / "in", "bad.quiz.md", version="2")
    rc, out, err = cli(capsys, ["--root", str(root), "import", str(f)])
    assert rc == 2 and out == "" and "bad.quiz.md" in err
    assert csv_bytes(root) is None


# ---------------- subprocess: script entry, fsrs blocked ----------------

def test_O10_script_entry_point(tmp_path):
    root = mkroot(tmp_path)
    r = subprocess.run([sys.executable, str(QUIZ_PY), "--root", str(root), "due", "--date", "2026-11-03"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert {i["path"] for i in json.loads(r.stdout)["items"]} == {A, B}
    r = subprocess.run([sys.executable, str(QUIZ_PY), "--root", str(root), "card", "../x.md"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 2 and r.stdout == "" and r.stderr.strip()


def blocked(tmp_path, body):
    code = (
        "import sys, pathlib, json\n"
        "sys.modules['fsrs'] = None\n"
        f"sys.path.insert(0, {str(QUIZ_DIR)!r})\n"
        "import quiz\n" + body
    )
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=tmp_path)


def test_O10_C26_result_cli_without_fsrs(tmp_path):
    root = mkroot(tmp_path)
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    r = blocked(tmp_path, (
        f"rc = quiz.main(['--root', {str(root)!r}, 'result', '--out', {str(out_dir)!r}, '--date', '2026-11-05', "
        f"'{A}=good', '{B}=hard'], {{}}, pathlib.Path({str(tmp_path)!r}))\n"
        "sys.exit(rc)\n"))
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    files = list(out_dir.glob("*.quiz.md"))
    assert len(files) == 1 and d["id"].startswith("chat-2026-11-05T")
    assert files[0].read_text(encoding="utf-8").endswith(f"- {A} | good\n- {B} | hard\n")


def test_O10_C26_make_result_api_without_fsrs(tmp_path):
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    r = blocked(tmp_path, (
        "import datetime\n"
        f"res = quiz.make_result([('{A}', 'easy')], datetime.date(2026, 11, 5), pathlib.Path({str(out_dir)!r}), "
        "datetime.datetime(2026, 11, 5, 9, 30, 15))\n"
        "print(res['id'])\n"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "chat-2026-11-05T093015"
    assert (out_dir / "2026-11-05-093015.quiz.md").exists()


def test_O10_C26_control_scheduling_needs_fsrs(tmp_path):
    """Validates the block itself: the scheduling path must not succeed when fsrs is unimportable."""
    root = mkroot(tmp_path)
    r = blocked(tmp_path, (
        f"rc = quiz.main(['--root', {str(root)!r}, 'due', '--date', '2026-11-03'], {{}}, pathlib.Path({str(tmp_path)!r}))\n"
        "sys.exit(rc)\n"))
    assert r.returncode != 0


# ---------------- parse_date ----------------

def dt(h, m=0, day=5):
    return datetime.datetime(2026, 11, day, h, m)


@pytest.mark.parametrize("value,now,want", [
    ("2026-11-05", None, datetime.date(2026, 11, 5)),
    ("2026-02-28", None, datetime.date(2026, 2, 28)),
    ("today", dt(4, 59), datetime.date(2026, 11, 4)),
    ("today", dt(5, 0), datetime.date(2026, 11, 5)),
    ("today", dt(23, 59), datetime.date(2026, 11, 5)),
    ("yesterday", dt(4, 59), datetime.date(2026, 11, 3)),
    ("yesterday", dt(5, 0), datetime.date(2026, 11, 4)),
    ("today", datetime.datetime(2026, 1, 1, 3, 0), datetime.date(2025, 12, 31)),
])
def test_O10_parse_date_ok(value, now, want):
    assert quiz.parse_date(value, now) == want


@pytest.mark.parametrize("value", ["2026/11/05", "2026-1-5", "tomorrow", "", "2026-02-30", "2026-13-01", "11-05"])
def test_O10_parse_date_errors(value):
    with pytest.raises(quiz.QuizError) as ei:
        quiz.parse_date(value, dt(12))
    assert ei.value.code == 2


def test_O10_parse_date_default_now_runs():
    assert isinstance(quiz.parse_date("today"), datetime.date)
