import subprocess
from pathlib import Path

import pytest

import learn
from learn_support import D, DS, MANIFEST_HEADER, expect_error, fm_parse, make_root, section_lines, snapshot, write


def same(path_str, expected: Path):
    assert Path(path_str).is_absolute()
    return Path(path_str).resolve() == expected.resolve()


def plain_dir(tmp_path, name="plain"):
    d = tmp_path / name
    d.mkdir()
    return d


# ---- mode (E1-E3) ----
@pytest.mark.parametrize(
    "environ,mode",
    [
        ({}, "chat"),
        ({"CLAUDE_CODE_REMOTE": "true"}, "chat"),
        ({"CLAUDECODE": "1"}, "local"),
        ({"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "false"}, "local"),
        ({"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true"}, "cloud"),
    ],
    ids=["E1_chat", "E1_remote_without_claudecode", "E2_local", "E2_remote_false", "E3_cloud"],
)
def test_O13_E1_E3_mode(tmp_path, environ, mode):
    cwd = plain_dir(tmp_path)
    assert learn.env(None, environ, cwd)["mode"] == mode


# ---- root precedence (E4) ----
def test_O13_E4_root_arg_beats_env_and_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    arg, envroot = plain_dir(tmp_path, "arg"), plain_dir(tmp_path, "envroot")
    r = learn.env(str(arg), {"LLM_WIKI_ROOT": str(envroot)}, repo)
    assert same(r["root"], arg)


def test_O13_E4_env_var_beats_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    envroot = plain_dir(tmp_path, "envroot")
    assert same(learn.env(None, {"LLM_WIKI_ROOT": str(envroot)}, repo)["root"], envroot)


def test_O13_E4_git_toplevel_from_subfolder(tmp_path):
    repo = tmp_path / "repo"
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert same(learn.env(None, {}, sub)["root"], repo)


def test_O13_E4_cwd_when_not_git(tmp_path):
    cwd = plain_dir(tmp_path)
    assert same(learn.env(None, {}, cwd)["root"], cwd)


def test_O13_has_wiki(tmp_path):
    empty = plain_dir(tmp_path, "empty")
    assert learn.env(str(empty), {}, tmp_path)["has_wiki"] is False
    write(empty / "wiki" / "log.md", "# Log\n")
    assert learn.env(str(empty), {}, tmp_path)["has_wiki"] is False
    root = make_root(tmp_path)
    assert learn.env(str(root), {}, tmp_path)["has_wiki"] is True


# ---- cloud_push (E5-E8) ----
def cp(tmp_path, toml=None):
    root = plain_dir(tmp_path, "r")
    if toml is not None:
        write(root / "llm-wiki.toml", toml)
    return root


def test_O13_E5_toml_absent(tmp_path):
    root = cp(tmp_path)
    assert learn.env(str(root), {}, tmp_path)["cloud_push"] == "session-branch"


@pytest.mark.parametrize("toml", ["", "[other]\nx = 1\n", "[add]\n"], ids=["empty_file", "no_add_table", "no_key"])
def test_O13_E5_key_absent(tmp_path, toml):
    root = cp(tmp_path, toml)
    assert learn.env(str(root), {}, tmp_path)["cloud_push"] == "session-branch"


@pytest.mark.parametrize("value", ["default-branch", "session-branch"])
def test_O13_E6_valid_values(tmp_path, value):
    root = cp(tmp_path, f'[add]\ncloud_push = "{value}"\n')
    assert learn.env(str(root), {}, tmp_path)["cloud_push"] == value


def test_O13_E7_invalid_value(tmp_path):
    root = cp(tmp_path, '[add]\ncloud_push = "weird-branch"\n')
    msg = expect_error(2, lambda: learn.env(str(root), {}, tmp_path), tmp_path)
    assert "weird-branch" in msg or "llm-wiki.toml" in msg


def test_O13_E8_broken_toml(tmp_path):
    root = cp(tmp_path, "[add\ncloud_push = = =\n")
    msg = expect_error(2, lambda: learn.env(str(root), {}, tmp_path), tmp_path)
    assert "llm-wiki.toml" in msg


# ---- init (E9-E11) ----
def test_O13_E9_init_empty_dir(tmp_path):
    root = plain_dir(tmp_path, "fresh")
    assert learn.env(str(root), {}, tmp_path)["has_wiki"] is False
    res = learn.init(root)
    assert sorted(res["created"]) == ["raw/MANIFEST.csv", "wiki/index.md", "wiki/log.md"]
    files = sorted(k for k, v in snapshot(root).items() if v is not None)
    assert files == ["raw/MANIFEST.csv", "wiki/index.md", "wiki/log.md"]
    index = (root / "wiki/index.md").read_text(encoding="utf-8")
    assert index.splitlines()[0] == "# Index"
    assert "## 공부 (study/)" in index.splitlines()
    assert (root / "wiki/log.md").read_text(encoding="utf-8").splitlines()[0] == "# Log"
    assert (root / "raw/MANIFEST.csv").read_text(encoding="utf-8").splitlines() == [",".join(MANIFEST_HEADER)]
    assert learn.env(str(root), {}, tmp_path)["has_wiki"] is True


def test_O13_E10_init_existing_wiki_untouched(tmp_path):
    root = make_root(
        tmp_path,
        index="# Mine\n\n## 공부 (study/)\n- [[A]] — a\n",
        log="# Log\n- x\n",
        rows=[("raw/a.md", "a.md", "0" * 64, "2026-11-01T00:00:00", "")],
    )
    before = snapshot(tmp_path)
    res = learn.init(root)
    assert res["created"] == []
    assert snapshot(tmp_path) == before


def test_O13_E10_init_creates_only_missing(tmp_path):
    root = plain_dir(tmp_path, "part")
    write(root / "wiki/index.md", "# Custom index\n")
    res = learn.init(root)
    assert sorted(res["created"]) == ["raw/MANIFEST.csv", "wiki/log.md"]
    assert (root / "wiki/index.md").read_bytes() == b"# Custom index\n"


def test_O13_E11_record_after_init(tmp_path):
    root = plain_dir(tmp_path, "fresh")
    learn.init(root)
    res = learn.record("초기 페이지", 2, "근거", root, D, summary="요약")
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert res["created"] is True and fm_parse(page)["level"] == "2"
    assert section_lines(page, "이해 기록")
    index = (root / "wiki/index.md").read_text(encoding="utf-8").splitlines()
    assert "- [[초기 페이지]] — 요약" in index
    assert index.index("## 공부 (study/)") < index.index("- [[초기 페이지]] — 요약")
    assert (root / "wiki/log.md").read_text(encoding="utf-8").splitlines()[-1] == f"- {DS} [learn] 초기 페이지: 새 페이지, L2"
