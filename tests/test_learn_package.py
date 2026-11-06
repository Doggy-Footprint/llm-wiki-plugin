import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

import build_zip
from learn_support import PLUGIN_ROOT, SKILL_DIR, TEMPLATE

NAMES = ["wiki-add", "wiki-goal", "wiki-insight", "wiki-learn", "wiki-quiz"]
WIKI_REPO = "`Doggy-Footprint/LLM-wiki` (default branch `master`)"


def copy_plugin(tmp_path) -> Path:
    dst = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist", ".pytest_cache"))
    return dst


def zip_entries(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: (i.date_time, i.external_attr >> 16, z.read(i)) for i in z.infolist() if not i.is_dir()}


def frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return dict(ln.split(": ", 1) for ln in block.strip().split("\n"))


def built_names(paths) -> list[str]:
    return [Path(p).name for p in paths]


def chat_text(name: str) -> str:
    return (PLUGIN_ROOT / "skills" / name / "claude-ai.md").read_text(encoding="utf-8")


def test_plugin_zip_holds_manifest_skills_and_docs_only(tmp_path):
    plug = copy_plugin(tmp_path)
    out = tmp_path / "out"
    assert built_names(build_zip.build(plug, out)) == ["llm-wiki.zip"]
    ent = zip_entries(out / "llm-wiki.zip")
    expected = {".claude-plugin/plugin.json", "README.md", "LICENSE"}
    expected |= {p.relative_to(plug).as_posix() for p in (plug / "skills").rglob("*") if p.is_file()}
    assert set(ent) == expected
    for rel, (_, mode, data) in ent.items():
        assert data == (plug / rel).read_bytes(), rel
        assert mode == 0o644


def test_no_loader_folder_left():
    assert not (PLUGIN_ROOT / "claude-ai").exists()


@pytest.mark.parametrize("path", [f"skills/{n}/SKILL.md" for n in NAMES])
def test_skill_description_has_no_angle_brackets(path):
    desc = frontmatter((PLUGIN_ROOT / path).read_text(encoding="utf-8"))["description"]
    assert "<" not in desc and ">" not in desc, "claude.ai skill 업로드가 'description cannot contain XML tags'로 거부한다"


def test_chat_instruction_folders_match_skills():
    chat_skills = {p.parent.name for p in (PLUGIN_ROOT / "skills").glob("*/claude-ai.md")}
    assert chat_skills == set(NAMES)
    for n in NAMES:
        assert frontmatter((PLUGIN_ROOT / "skills" / n / "SKILL.md").read_text(encoding="utf-8"))["name"] == n


@pytest.mark.parametrize("name", NAMES)
def test_skill_routes_claude_ai_chat_to_its_chat_instructions(name):
    text = (PLUGIN_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    assert "claude.ai chat" in text and "follow only `claude-ai.md`" in text


@pytest.mark.parametrize("name", NAMES)
def test_chat_instructions_reference_existing_plugin_paths(name):
    text = chat_text(name)
    for word in ("<skill dir>", "zip", "loader", "raw.githubusercontent.com", "llm-wiki-plugin"):
        assert word not in text, word
    assert "this skill's own files are next to this file, in `<this folder>`" in text
    for ref in re.findall(r"`(skills/[\w-]+/[\w.-]+)`", text):
        assert (PLUGIN_ROOT / ref).is_file(), ref
    for ref in re.findall(r'"<this folder>/([\w.-]+)"', text):
        assert (PLUGIN_ROOT / "skills" / name / ref).is_file(), ref


@pytest.mark.parametrize("name", NAMES)
def test_chat_instructions_copy_every_script_they_run(name):
    text = chat_text(name)
    used = set(re.findall(r"<script dir>/(\w+\.py)", text))
    copied = set(re.findall(r'"<this folder>/(\w+\.py)"', text))
    assert used <= copied
    if used:
        assert "`<script dir>` is `/tmp/llm-wiki`" in text
        assert "cp " in text and " /tmp/llm-wiki/`" in text


def test_chat_wiki_learn_finds_the_wiki_add_folder_it_reads():
    text = chat_text("wiki-learn")
    assert "`skills/wiki-add/claude-ai.md`" in text and "`skills/wiki-add/SKILL.md`" in text
    assert "find / -path '*/wiki-add/learn.py'" in text and "missing and stop" in text


@pytest.mark.parametrize("name", [n for n in NAMES if n != "wiki-add"])
def test_chat_instructions_name_the_default_wiki_repository(name):
    text = chat_text(name)
    assert "Use the repository named in the user's prompt; if none, the GitHub repository " + WIKI_REPO in text


def test_build_ignores_other_files(tmp_path):
    plug = copy_plugin(tmp_path)
    (plug / "notes.txt").write_text("stray\n")
    (plug / "skills" / "wiki-add" / "__pycache__").mkdir()
    (plug / "skills" / "wiki-add" / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
    (plug / "skills" / "wiki-add" / "y.pyc").write_bytes(b"\x00pyc")
    (plug / "skills" / ".DS_Store").write_bytes(b"\x00")
    out = tmp_path / "z"
    build_zip.build(plug, out)
    names = set(zip_entries(out / "llm-wiki.zip"))
    assert not {n for n in names if n.startswith(("tests/", "scripts/", ".github/")) or n == "notes.txt"}
    assert not {n for n in names if "__pycache__" in n or n.endswith((".pyc", ".DS_Store"))}


def test_build_picks_up_a_new_skill_folder(tmp_path):
    plug = copy_plugin(tmp_path)
    (plug / "skills" / "wiki-new").mkdir()
    (plug / "skills" / "wiki-new" / "SKILL.md").write_text("---\nname: wiki-new\n---\n")
    build_zip.build(plug, tmp_path / "z")
    assert "skills/wiki-new/SKILL.md" in zip_entries(tmp_path / "z" / "llm-wiki.zip")


def test_build_bytes_stable_across_mtime_and_clock(tmp_path, monkeypatch):
    plug = copy_plugin(tmp_path)
    first = [p.read_bytes() for p in build_zip.build(plug, tmp_path / "a")]
    year_2100 = 4102444800
    for rel in build_zip.plugin_files(plug):
        os.utime(plug / rel, (year_2100, year_2100))
    real_time, real_lt, real_gt = time.time, time.localtime, time.gmtime

    def shifted():
        return real_time() + 400 * 86400

    monkeypatch.setattr(time, "time", shifted)
    monkeypatch.setattr(time, "localtime", lambda secs=None: real_lt(shifted() if secs is None else secs))
    monkeypatch.setattr(time, "gmtime", lambda secs=None: real_gt(shifted() if secs is None else secs))
    assert [p.read_bytes() for p in build_zip.build(plug, tmp_path / "b")] == first


def test_cli_runs_in_process(tmp_path, monkeypatch, capsys):
    out = tmp_path / "cli"
    monkeypatch.setattr(sys, "argv", ["build_zip.py", "--out-dir", str(out)])
    try:
        runpy.run_path(str(PLUGIN_ROOT / "scripts" / "build_zip.py"), run_name="__main__")
    except SystemExit as e:
        assert e.code in (None, 0)
    assert sorted(p.name for p in out.iterdir()) == ["llm-wiki.zip"]
    assert capsys.readouterr().out.splitlines() == [str(out / "llm-wiki.zip")]


def test_cli_default_output_path(tmp_path):
    plug = copy_plugin(tmp_path)
    r = subprocess.run([sys.executable, str(plug / "scripts" / "build_zip.py")], cwd=plug, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in (plug / "dist").iterdir()) == ["llm-wiki.zip"]


@pytest.mark.parametrize("opt", [["--skill", "wiki-quiz"], ["--out", "x.zip"]])
def test_cli_rejects_removed_options(tmp_path, opt):
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), *opt],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0 and not list(tmp_path.iterdir())


def test_release_uploads_the_built_plugin_zip():
    text = (PLUGIN_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "python3 scripts/build_zip.py --out-dir dist" in text
    assert re.search(r"gh release create \"\$tag\" dist/\*\.zip ", text)


def test_O16_Y2_plugin_concept_equals_template():
    assert (SKILL_DIR / "concept.md").read_bytes() == TEMPLATE.encode("utf-8")
    assert TEMPLATE.endswith("\n") and not TEMPLATE.endswith("\n\n")


def test_O16_Y3_plugin_json_fields():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "llm-wiki"
    assert data["version"] == "0.9.0"
    assert data["license"] == "MIT"
    assert "Doggy-Footprint" in json.dumps(data["author"])
    assert data["repository"] == "https://github.com/Doggy-Footprint/llm-wiki-plugin"
    assert data.get("description")


def test_O16_Y5_import_and_env_without_markitdown(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    code = (
        "import sys, pathlib\n"
        "sys.modules['markitdown'] = None\n"
        f"sys.path.insert(0, {str(SKILL_DIR)!r})\n"
        "import learn\n"
        f"sys.exit(learn.main(['env'], environ={{}}, cwd=pathlib.Path({str(cwd)!r})))\n"
    )
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["mode"] == "chat"


def test_O16_Y6_pep723_block_in_header():
    head = (SKILL_DIR / "learn.py").read_bytes().decode("utf-8").splitlines()[:15]
    start = head.index("# /// script")
    end = head.index("# ///", start + 1)
    block = head[start:end]
    assert any("markitdown[pdf,docx,pptx]==0.1.9" in ln for ln in block)


def test_O12_plugin_json_version_and_description():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "0.9.0"
    desc = data["description"].lower()
    for name in NAMES:
        assert re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", desc), name
