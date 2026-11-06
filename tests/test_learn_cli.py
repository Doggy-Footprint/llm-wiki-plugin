import datetime
import json
import re
from pathlib import Path

import pytest

import learn
from learn_support import (
    D, DS, MARKER, ev_line, http_server, make_root, result_text, run_main, section_lines,  # noqa: F401
    snapshot, write,
)


def cli(capsys, tmp_path, root, argv, env=None):
    environ = {"LLM_WIKI_ROOT": str(root)}
    environ.update(env or {})
    rc = run_main(learn.main, argv, environ, tmp_path)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def one_json(out):
    return json.loads(out)


def test_O10_M1_env(tmp_path, capsys):
    root = make_root(tmp_path)
    rc, out, err = cli(capsys, tmp_path, root, ["env"], {"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true"})
    assert rc == 0
    d = one_json(out)
    assert d["mode"] == "cloud" and d["has_wiki"] is True and d["cloud_push"] == "session-branch"
    assert Path(d["root"]).resolve() == root.resolve()
    rc, out, _ = cli(capsys, tmp_path, root, ["env"])
    assert one_json(out)["mode"] == "chat"


def test_O10_M1_root_flag_before_subcommand(tmp_path, capsys):
    root = make_root(tmp_path)
    rc = run_main(learn.main, ["--root", str(root), "env"], {"CLAUDECODE": "1"}, tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert Path(one_json(out)["root"]).resolve() == root.resolve()


def test_O10_M2_init(tmp_path, capsys):
    root = tmp_path / "fresh"
    root.mkdir()
    rc, out, _ = cli(capsys, tmp_path, root, ["init"])
    assert rc == 0
    assert sorted(one_json(out)["created"]) == ["raw/MANIFEST.csv", "wiki/index.md", "wiki/log.md"]


def test_O10_M3_fetch_non_ascii(tmp_path, capsys):
    root = make_root(tmp_path)
    src = write(tmp_path / "src" / "n.md", "# 제목\n한글 본문\n")
    rc, out, _ = cli(capsys, tmp_path, root, ["fetch", str(src), "--date", DS, "--slug", "한글 노트"])
    assert rc == 0
    d = one_json(out)
    assert d["raw"] == "raw/2026/11/2026-11-05-한글-노트.md"
    assert "한글-노트" in out and "\\u" not in out
    assert set(d) >= {"raw", "md", "chars", "outline", "duplicate_of"}


def test_O10_M3_fetch_url(tmp_path, capsys, http_server):
    root = make_root(tmp_path)
    rc, out, _ = cli(capsys, tmp_path, root, ["fetch", http_server.url, "--date", DS, "--slug", "w"])
    assert rc == 0
    d = one_json(out)
    assert d["raw"] == d["md"] and http_server.marker not in out


def test_O10_M4_related(tmp_path, capsys):
    root = make_root(tmp_path)
    write(root / "wiki/study/정렬 알고리즘.md", "x\n")
    rc, out, _ = cli(capsys, tmp_path, root, ["related", "정렬", "알고리즘", "--limit", "5"])
    assert rc == 0
    d = one_json(out)
    assert isinstance(d, list) and len(d) == 1
    assert d[0]["path"] == "wiki/study/정렬 알고리즘.md" and d[0]["score"] == 20 and d[0]["level"] is None
    assert "정렬 알고리즘" in out and "\\u" not in out


def test_O10_M5_record(tmp_path, capsys):
    root = make_root(tmp_path)
    raw = write(root / "raw/2026/11/2026-11-05-a.md", "# a\n")
    rc, out, _ = cli(
        capsys, tmp_path, root,
        ["record", "한글 제목", "--level", "2", "--evidence", "설명 근거", "--summary", "요약문",
         "--misconception", "오해문", "--source", "raw/2026/11/2026-11-05-a.md", "--date", DS],
    )
    assert rc == 0
    d = one_json(out)
    assert d == {"page": "wiki/study/한글 제목.md", "created": True, "previous_level": None, "level": 2, "changed": True}
    assert "한글 제목" in out and "\\u" not in out
    page = (root / d["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "이해 기록") == [ev_line(2, "설명 근거")]
    assert section_lines(page, "오해와 교정") == [f"- {DS} 오해문"]
    assert raw.exists()


def test_O10_M6_M7_result_then_import(tmp_path, capsys):
    root = make_root(tmp_path)
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    rc, out, _ = cli(
        capsys, tmp_path, root,
        ["result", "신경망 기초", "--level", "1", "--summary", "요약", "--evidence", "근거", "--out", str(out_dir),
         "--mine", "내 정리", "--supplement", "보충", "--link", "[[링크]] — 관계", "--date", DS],
    )
    assert rc == 0
    d = one_json(out)
    assert Path(d["path"]).name == "2026-11-05-신경망-기초.learn.md"
    f = out_dir / "2026-11-05-신경망-기초.learn.md"
    assert f.exists()
    rc, out, _ = cli(capsys, tmp_path, root, ["import", str(f)])
    assert rc == 0
    d = one_json(out)
    assert d["page"] == "wiki/study/신경망 기초.md" and d["created"] is True
    assert {s.lstrip("# ").strip() for s in d["sections_added"]} == {"내가 정리한 것", "보충 (LLM)", "연결"}
    assert "신경망 기초" in out and "\\u" not in out


def test_O10_M8_learn_error_2(tmp_path, capsys):
    root = make_root(tmp_path)
    for argv, needle in [
        (["record", "T", "--level", "9", "--evidence", "e", "--summary", "s", "--date", DS], "9"),
        (["record", "a/b", "--level", "2", "--evidence", "e", "--summary", "s", "--date", DS], "a/b"),
        (["related", "kw", "--limit", "0"], "0"),
        (["fetch", str(tmp_path / "missing.md"), "--date", DS, "--slug", "s"], "missing.md"),
        (["import", str(tmp_path / "no.learn.md")], "no.learn.md"),
    ]:
        before = snapshot(tmp_path)
        rc, out, err = cli(capsys, tmp_path, root, argv)
        assert rc == 2, argv
        assert err.strip() and needle in err, (argv, err)
        assert snapshot(tmp_path) == before
        assert not out.strip() or not out.lstrip().startswith(("{", "["))


def test_O10_M8_toml_error_via_env(tmp_path, capsys):
    root = make_root(tmp_path)
    write(root / "llm-wiki.toml", '[add]\ncloud_push = "bogus-value"\n')
    rc, out, err = cli(capsys, tmp_path, root, ["env"])
    assert rc == 2 and err.strip()
    assert "bogus-value" in err or "llm-wiki.toml" in err


def test_O10_M9_learn_error_3(tmp_path, capsys, http_server):
    root = make_root(tmp_path)
    empty = write(tmp_path / "src" / "empty.md", b"")
    for src in (empty, http_server.url404):
        before = snapshot(tmp_path)
        rc, out, err = cli(capsys, tmp_path, root, ["fetch", str(src), "--date", DS, "--slug", "s"])
        assert rc == 3
        assert str(src) in err
        assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "argv",
    [
        ["bogus-subcommand"],
        ["fetch"],
        ["record", "T", "--level", "a", "--evidence", "e", "--summary", "s", "--date", DS],
        ["record", "T", "--evidence", "e", "--summary", "s", "--date", DS],
        ["related", "kw", "--limit", "x"],
        ["import"],
    ],
    ids=["unknown_cmd", "fetch_no_source", "level_a", "level_missing", "limit_x", "import_no_file"],
)
def test_O10_M10_argparse_error_is_2(tmp_path, capsys, argv):
    root = make_root(tmp_path)
    before = snapshot(tmp_path)
    rc, out, err = cli(capsys, tmp_path, root, argv)
    assert rc == 2
    assert err.strip()
    assert snapshot(tmp_path) == before


def test_O10_O5_cli_level_a_message(tmp_path, capsys):
    root = make_root(tmp_path)
    rc, _, err = cli(capsys, tmp_path, root, ["record", "T", "--level", "a", "--evidence", "e", "--summary", "s"])
    assert rc == 2 and err.strip()


def test_O10_date_today_and_yesterday(tmp_path, capsys):
    root = make_root(tmp_path)
    today = datetime.date.today()
    for word, lo, hi in (("today", 1, 0), ("yesterday", 2, 1)):
        rc, _, _ = cli(capsys, tmp_path, root,
                       ["record", f"T-{word}", "--level", "1", "--evidence", "e", "--summary", "s", "--date", word])
        assert rc == 0
        last = (root / "wiki/log.md").read_text(encoding="utf-8").splitlines()[-1]
        m = re.match(r"- (\d{4}-\d{2}-\d{2}) \[learn\] ", last)
        assert m, last
        got = datetime.date.fromisoformat(m.group(1))
        assert 0 <= (today - got).days <= (1 if word == "today" else 2)
        assert (today - got).days >= (0 if word == "today" else 1)


def test_result_next_flag_writes_next_section(tmp_path, capsys):
    root = make_root(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rc, out, _ = cli(capsys, tmp_path, root, [
        "result", "개념", "--level", "1", "--summary", "요약", "--evidence", "근거", "--out", str(out_dir),
        "--next", "[[A]] — 덜 이해함: a", "--next", "[[B]] — 이어서: b", "--date", DS,
    ])
    assert rc == 0
    text = Path(one_json(out)["path"]).read_text(encoding="utf-8")
    assert section_lines(text, "다음 학습") == ["- [[A]] — 덜 이해함: a", "- [[B]] — 이어서: b"]
