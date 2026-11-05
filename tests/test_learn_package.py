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

LOADER = PLUGIN_ROOT / "claude-ai" / "SKILL.md"
TOOLS = PLUGIN_ROOT / "claude-ai" / "skills.md"
RAW_PREFIX = "https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/"


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


def tool_rows() -> list[list[str]]:
    rows = []
    for ln in TOOLS.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and len(cells) == 4 and cells[0] not in ("도구", "---"):
            rows.append(cells)
    return rows


def test_loader_zip_holds_only_loader_skill(tmp_path):
    out = tmp_path / "out" / "llm-wiki.zip"
    res = build_zip.build(PLUGIN_ROOT, out)
    assert Path(res).resolve() == out.resolve()
    ent = zip_entries(out)
    assert set(ent) == {"llm-wiki/SKILL.md"}
    assert ent["llm-wiki/SKILL.md"][2] == LOADER.read_bytes()
    assert ent["llm-wiki/SKILL.md"][1] == 0o644


def test_loader_frontmatter_name_and_english_description():
    fm = frontmatter(LOADER.read_text(encoding="utf-8"))
    assert fm["name"] == "llm-wiki"
    desc = fm["description"]
    assert desc.isascii() and 0 < len(desc) <= 1024
    for name in ("add", "wiki-learn", "quiz"):
        assert re.search(rf"\({re.escape(name)}\)", desc), name


def test_loader_points_at_public_repo_and_tool_list():
    text = LOADER.read_text(encoding="utf-8")
    assert "Doggy-Footprint/llm-wiki-plugin" in text and RAW_PREFIX in text
    assert "`claude-ai/skills.md`" in text


def test_tool_list_paths_exist_and_cover_every_chat_skill():
    rows = tool_rows()
    assert [r[0] for r in rows] == ["add", "wiki-learn", "quiz"]
    for name, _, instr, script in rows:
        assert (PLUGIN_ROOT / instr).is_file(), instr
        assert (PLUGIN_ROOT / script).is_file(), script
        assert instr == f"skills/{name}/claude-ai.md"
    chat_skills = {p.parent.name for p in (PLUGIN_ROOT / "skills").glob("*/claude-ai.md")}
    assert chat_skills == {r[0] for r in rows}


@pytest.mark.parametrize("name", ["add", "wiki-learn", "quiz"])
def test_chat_instructions_reference_existing_repo_paths(name):
    text = (PLUGIN_ROOT / "skills" / name / "claude-ai.md").read_text(encoding="utf-8")
    assert "<skill 폴더>" not in text and "zip" not in text
    for ref in re.findall(r"`(skills/[\w-]+/[\w.-]+)`", text):
        assert (PLUGIN_ROOT / ref).is_file(), ref


def test_build_ignores_other_files(tmp_path):
    plug = copy_plugin(tmp_path)
    (plug / "claude-ai" / "notes.txt").write_text("stray\n")
    (plug / "claude-ai" / "__pycache__").mkdir()
    (plug / "claude-ai" / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
    out = tmp_path / "z.zip"
    build_zip.build(plug, out)
    assert set(zip_entries(out)) == {"llm-wiki/SKILL.md"}


def test_build_bytes_stable_across_mtime_and_clock(tmp_path, monkeypatch):
    plug = copy_plugin(tmp_path)
    first = build_zip.build(plug, tmp_path / "a.zip").read_bytes()
    year_2100 = 4102444800
    os.utime(plug / "claude-ai" / "SKILL.md", (year_2100, year_2100))
    real_time, real_lt, real_gt = time.time, time.localtime, time.gmtime

    def shifted():
        return real_time() + 400 * 86400

    monkeypatch.setattr(time, "time", shifted)
    monkeypatch.setattr(time, "localtime", lambda secs=None: real_lt(shifted() if secs is None else secs))
    monkeypatch.setattr(time, "gmtime", lambda secs=None: real_gt(shifted() if secs is None else secs))
    assert build_zip.build(plug, tmp_path / "b.zip").read_bytes() == first


def test_cli_runs_in_process(tmp_path, monkeypatch):
    out = tmp_path / "cli.zip"
    monkeypatch.setattr(sys, "argv", ["build_zip.py", "--out", str(out)])
    try:
        runpy.run_path(str(PLUGIN_ROOT / "scripts" / "build_zip.py"), run_name="__main__")
    except SystemExit as e:
        assert e.code in (None, 0)
    assert set(zip_entries(out)) == {"llm-wiki/SKILL.md"}


def test_cli_default_output_path(tmp_path):
    plug = copy_plugin(tmp_path)
    r = subprocess.run([sys.executable, str(plug / "scripts" / "build_zip.py")], cwd=plug, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert set(zip_entries(plug / "dist" / "llm-wiki.zip")) == {"llm-wiki/SKILL.md"}


def test_cli_rejects_removed_skill_option(tmp_path):
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), "--skill", "quiz",
                        "--out", str(tmp_path / "x.zip")], capture_output=True, text=True)
    assert r.returncode != 0 and not (tmp_path / "x.zip").exists()


def test_release_uploads_the_built_loader_zip():
    text = (PLUGIN_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "python3 scripts/build_zip.py --out dist/llm-wiki.zip" in text
    assert re.search(r"gh release create \"\$tag\" dist/llm-wiki\.zip ", text)


def test_O16_Y2_plugin_concept_equals_template():
    assert (SKILL_DIR / "concept.md").read_bytes() == TEMPLATE.encode("utf-8")
    assert TEMPLATE.endswith("\n") and not TEMPLATE.endswith("\n\n")


def test_O16_Y3_plugin_json_fields():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "llm-wiki"
    assert data["version"] == "0.2.0"
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
    assert data["version"] == "0.2.0"
    desc = data["description"].lower()
    assert "wiki-learn" in desc and "quiz" in desc and "add" in desc


def test_O12_description_names_each_skill_as_a_word():
    desc = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"].lower()
    for name in ("add", "wiki-learn", "quiz"):
        assert re.search(rf"\b{re.escape(name)}\b", desc), name
    # `add` and `quiz` must not be satisfied only by being part of `wiki-learn`
    stripped = desc.replace("wiki-learn", " ")
    assert re.search(r"\badd\b", stripped), "description must name add on its own"
    assert re.search(r"\bquiz\b", stripped), "description must name quiz on its own"
    assert re.search(r"\bwiki-learn\b", desc)
