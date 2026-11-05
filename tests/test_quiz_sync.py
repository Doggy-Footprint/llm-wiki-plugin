import importlib.util
import json
import shutil
import sys

import pytest

import quiz
from quiz_support import (
    D, DS, HEADER_LINE, QUIZ_PY, csv_bytes, deck_bytes, make_root, page, result_file, result_text, row,
    snapshot, write, write_csv, cli, one_json,
)

A, B = "wiki/study/A.md", "wiki/study/B.md"


def base_root(tmp_path, name="root"):
    root = make_root(tmp_path, name)
    page(root, A, created="2026-11-01")
    page(root, B, created="2026-11-01")
    return root


def inbox(root):
    return root / "chat" / "inbox"


def c19_fixture(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    result_file(ib, "2026-11-04-090000.quiz.md", id="chat-2026-11-04T090000",
                entries=["- wiki/study/A.md | good", "- wiki/study/B.md | again"])
    write(ib / "2026-11-04-imported.learn.md", result_text())
    result_file(ib, "bad.quiz.md", version="2")
    write(ib / ".gitkeep", b"")
    write(ib / "notes.txt", "메모\n")
    return root


def test_O9_C19_mixed_inbox(tmp_path):
    root = c19_fixture(tmp_path)
    ib = inbox(root)
    bad_bytes = (ib / "bad.quiz.md").read_bytes()
    res = quiz.sync(root, D)
    assert res["quiz"] == ["chat-2026-11-04T090000"]
    assert len(res["learn"]) == 1
    page_rel = res["learn"][0]
    assert page_rel.startswith("wiki/") and page_rel.endswith("Imported.md")
    assert "# Imported" in (root / page_rel).read_text(encoding="utf-8")
    assert len(res["failed"]) == 1
    f = res["failed"][0]
    assert f["file"] == "chat/inbox/bad.quiz.md" and "bad.quiz.md" in f["error"]
    assert res["deck"] == "chat/deck.md"

    assert sorted(p.name for p in ib.iterdir()) == [".gitkeep", "bad.quiz.md", "notes.txt"]
    assert (ib / "bad.quiz.md").read_bytes() == bad_bytes
    assert (ib / "notes.txt").read_text(encoding="utf-8") == "메모\n"
    assert (ib / ".gitkeep").read_bytes() == b""

    assert csv_bytes(root) == (
        f"{HEADER_LINE}\n"
        "2026-11-04,wiki/study/A.md,good,review,chat,chat-2026-11-04T090000\n"
        "2026-11-04,wiki/study/B.md,again,review,chat,chat-2026-11-04T090000\n"
    ).encode()
    deck = deck_bytes(root).decode()
    assert "generated: 2026-11-05" in deck
    assert "- Imported (L2)" in deck  # deck is built after the learn import


def test_O9_C19_exit_code_one_with_json_printed(tmp_path, capsys):
    root = c19_fixture(tmp_path)
    rc, out, err = cli(capsys, ["--root", str(root), "sync", "--date", DS])
    assert rc == 1
    d = one_json(out)
    assert d["quiz"] == ["chat-2026-11-04T090000"] and len(d["failed"]) == 1 and d["deck"] == "chat/deck.md"


def test_O9_sync_processes_in_name_order(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    result_file(ib, "b.quiz.md", id="id-b", entries=["- wiki/study/B.md | hard"])
    result_file(ib, "a.quiz.md", id="id-a", entries=["- wiki/study/A.md | easy"])
    res = quiz.sync(root, D)
    assert res["quiz"] == ["id-a", "id-b"] and res["failed"] == []
    rows = csv_bytes(root).decode().splitlines()[1:]
    assert [r.split(",")[5] for r in rows] == ["id-a", "id-b"]
    assert [p.name for p in ib.iterdir()] == [".gitkeep"]


def test_O9_duplicate_file_is_deleted_not_failed_csv_unchanged(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    write_csv(root, [row("2026-11-04", A, "good", source="chat", rid="id-x")])
    before = csv_bytes(root)
    result_file(ib, "dup.quiz.md", id="id-x", entries=["- wiki/study/B.md | again"])
    res = quiz.sync(root, D)
    assert res["failed"] == []
    assert res["quiz"] == ["id-x"]
    assert not (ib / "dup.quiz.md").exists()
    assert csv_bytes(root) == before


def test_O9_failed_quiz_does_not_block_others_and_csv_untouched_by_it(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    result_file(ib, "a.quiz.md", id="id-a", entries=["- wiki/study/Nope.md | good"])
    result_file(ib, "b.quiz.md", id="id-b", entries=["- wiki/study/B.md | good"])
    res = quiz.sync(root, D)
    assert res["quiz"] == ["id-b"]
    assert [f["file"] for f in res["failed"]] == ["chat/inbox/a.quiz.md"]
    assert (ib / "a.quiz.md").exists() and not (ib / "b.quiz.md").exists()
    assert "id-a" not in csv_bytes(root).decode()


def test_O9_bad_learn_file_kept_and_failed(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    write(ib / "x.learn.md", result_text(type="quiz-result"))
    write(ib / "y.learn.md", result_text(title="Fine"))
    res = quiz.sync(root, D)
    assert len(res["learn"]) == 1 and res["learn"][0].endswith("Fine.md")
    assert [f["file"] for f in res["failed"]] == ["chat/inbox/x.learn.md"]
    assert (ib / "x.learn.md").exists() and not (ib / "y.learn.md").exists()


def test_O9_C20_no_inbox_no_csv(tmp_path):
    root = tmp_path / "fresh"
    page(root, A, created="2026-11-01")
    res = quiz.sync(root, D)
    assert res == {"quiz": [], "learn": [], "failed": [], "deck": "chat/deck.md"}
    assert csv_bytes(root) is None and not (root / "data").exists()
    assert deck_bytes(root) is not None
    assert (root / "chat" / "inbox" / ".gitkeep").exists()


def test_O9_C20_empty_inbox_and_empty_wiki(tmp_path):
    root = tmp_path / "fresh"
    (root / "wiki").mkdir(parents=True)
    inbox(root).mkdir(parents=True)
    res = quiz.sync(root, D)
    assert res["quiz"] == [] and res["learn"] == [] and res["failed"] == []
    assert csv_bytes(root) is None
    assert deck_bytes(root) is not None


def test_O9_csv_created_only_when_rows_appended(tmp_path):
    root = base_root(tmp_path)
    result_file(inbox(root), "ok.quiz.md", id="id-1")
    assert csv_bytes(root) is None
    quiz.sync(root, D)
    assert csv_bytes(root).decode().startswith(HEADER_LINE + "\n")


def load_isolated(path, name="quiz_isolated"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def isolated_sync(tmp_path, learn_py_text=None):
    iso = tmp_path / "iso"
    qdir = iso / "skills" / "wiki-quiz"
    qdir.mkdir(parents=True)
    shutil.copy(QUIZ_PY, qdir / "quiz.py")
    if learn_py_text is not None:
        write(iso / "skills" / "wiki-add" / "learn.py", learn_py_text)
    mod = load_isolated(qdir / "quiz.py")
    root = base_root(tmp_path, "iroot")
    ib = inbox(root)
    result_file(ib, "a.quiz.md", id="id-a", entries=["- wiki/study/A.md | good"])
    write(ib / "x.learn.md", result_text())
    try:
        res = mod.sync(root, D)
    finally:
        sys.modules.pop("quiz_isolated", None)
    return root, res


@pytest.mark.parametrize("learn_py", [None, "raise RuntimeError('boom')\n", "def broken(:\n"],
                         ids=["missing", "import-raises", "syntax-error"])
def test_O9_learn_module_unavailable(tmp_path, learn_py):
    root, res = isolated_sync(tmp_path, learn_py)
    ib = inbox(root)
    assert res["quiz"] == ["id-a"]
    assert res["learn"] == []
    assert len(res["failed"]) == 1
    f = res["failed"][0]
    assert f["file"] == "chat/inbox/x.learn.md" and isinstance(f["error"], str) and f["error"]
    assert (ib / "x.learn.md").exists() and not (ib / "a.quiz.md").exists()
    assert deck_bytes(root) is not None
    assert "id-a" in csv_bytes(root).decode()
    assert not any(root.glob("wiki/**/Imported.md"))


def test_O9_A4_files_without_exact_suffix_are_ignored(tmp_path):
    root = base_root(tmp_path)
    ib = inbox(root)
    names = ["readme.md", "x.quiz.md.bak", "quiz.md", "y.learn.md.bak"]
    for n in names:
        result_file(ib, n, id=f"id-{n}")
    before = {n: (ib / n).read_bytes() for n in names}
    res = quiz.sync(root, D)
    assert res["quiz"] == [] and res["learn"] == [] and res["failed"] == []
    for n in names:
        assert (ib / n).read_bytes() == before[n]
    assert csv_bytes(root) is None
