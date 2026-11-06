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

NAMES = ["wiki-add", "wiki-goal", "wiki-learn", "wiki-quiz"]
SCRIPTS = {"wiki-add": "skills/wiki-add/learn.py", "wiki-goal": "skills/wiki-goal/goal.py",
           "wiki-learn": "skills/wiki-add/learn.py",
           "wiki-quiz": "skills/wiki-quiz/quiz.py"}
RAW_PREFIX = "https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/"


def loader(name: str) -> Path:
    return PLUGIN_ROOT / "claude-ai" / name / "SKILL.md"


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


def test_one_loader_zip_per_tool_holding_only_its_skill(tmp_path):
    out = tmp_path / "out"
    res = build_zip.build(PLUGIN_ROOT, out)
    assert built_names(res) == [f"{n}.zip" for n in NAMES]
    for n in NAMES:
        ent = zip_entries(out / f"{n}.zip")
        assert set(ent) == {f"{n}/SKILL.md"}
        assert ent[f"{n}/SKILL.md"][2] == loader(n).read_bytes()
        assert ent[f"{n}/SKILL.md"][1] == 0o644


@pytest.mark.parametrize("name", NAMES)
def test_loader_frontmatter_name_and_english_description(name):
    fm = frontmatter(loader(name).read_text(encoding="utf-8"))
    assert set(fm) == {"name", "description"}
    assert fm["name"] == name
    desc = fm["description"]
    assert desc.isascii() and 0 < len(desc) <= 1024
    assert ": " not in desc, "YAML plain scalar에는 ': '가 들어갈 수 없다 (claude.ai frontmatter가 깨진다)"
    assert f'"/{name}' in desc


@pytest.mark.parametrize("name", NAMES)
def test_loader_points_at_its_own_instructions_and_script(name):
    text = loader(name).read_text(encoding="utf-8")
    assert "Doggy-Footprint/llm-wiki-plugin" in text
    assert f"`skills/{name}/claude-ai.md`" in text
    assert RAW_PREFIX + SCRIPTS[name] in text
    assert f"/tmp/llm-wiki/{Path(SCRIPTS[name]).name}" in text
    for ref in re.findall(r"`(skills/[\w-]+/[\w.-]+)`", text):
        assert (PLUGIN_ROOT / ref).is_file(), ref


def test_loaders_match_chat_instruction_folders():
    chat_skills = {p.parent.name for p in (PLUGIN_ROOT / "skills").glob("*/claude-ai.md")}
    loader_names = {p.parent.name for p in (PLUGIN_ROOT / "claude-ai").glob("*/SKILL.md")}
    assert chat_skills == loader_names == set(NAMES)
    for n in NAMES:
        assert frontmatter((PLUGIN_ROOT / "skills" / n / "SKILL.md").read_text(encoding="utf-8"))["name"] == n


@pytest.mark.parametrize("name", NAMES)
def test_chat_instructions_reference_existing_repo_paths(name):
    text = (PLUGIN_ROOT / "skills" / name / "claude-ai.md").read_text(encoding="utf-8")
    assert "<skill 폴더>" not in text and "zip" not in text
    for ref in re.findall(r"`(skills/[\w-]+/[\w.-]+)`", text):
        assert (PLUGIN_ROOT / ref).is_file(), ref


def test_build_ignores_other_files(tmp_path):
    plug = copy_plugin(tmp_path)
    (plug / "claude-ai" / "notes.txt").write_text("stray\n")
    (plug / "claude-ai" / "wiki-add" / "extra.md").write_text("stray\n")
    (plug / "claude-ai" / "__pycache__").mkdir()
    (plug / "claude-ai" / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
    out = tmp_path / "z"
    assert built_names(build_zip.build(plug, out)) == [f"{n}.zip" for n in NAMES]
    assert set(zip_entries(out / "wiki-add.zip")) == {"wiki-add/SKILL.md"}


def test_build_picks_up_a_new_loader_folder(tmp_path):
    plug = copy_plugin(tmp_path)
    (plug / "claude-ai" / "wiki-new").mkdir()
    (plug / "claude-ai" / "wiki-new" / "SKILL.md").write_text("---\nname: wiki-new\n---\n")
    assert built_names(build_zip.build(plug, tmp_path / "z")) == [f"{n}.zip" for n in sorted(NAMES + ["wiki-new"])]


def test_build_bytes_stable_across_mtime_and_clock(tmp_path, monkeypatch):
    plug = copy_plugin(tmp_path)
    first = [p.read_bytes() for p in build_zip.build(plug, tmp_path / "a")]
    year_2100 = 4102444800
    for n in NAMES:
        os.utime(plug / "claude-ai" / n / "SKILL.md", (year_2100, year_2100))
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
    assert sorted(p.name for p in out.iterdir()) == [f"{n}.zip" for n in NAMES]
    assert capsys.readouterr().out.splitlines() == [str(out / f"{n}.zip") for n in NAMES]


def test_cli_default_output_path(tmp_path):
    plug = copy_plugin(tmp_path)
    r = subprocess.run([sys.executable, str(plug / "scripts" / "build_zip.py")], cwd=plug, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in (plug / "dist").iterdir()) == [f"{n}.zip" for n in NAMES]


@pytest.mark.parametrize("opt", [["--skill", "wiki-quiz"], ["--out", "x.zip"]])
def test_cli_rejects_removed_options(tmp_path, opt):
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), *opt],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0 and not list(tmp_path.iterdir())


def test_release_uploads_every_built_loader_zip():
    text = (PLUGIN_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "python3 scripts/build_zip.py --out-dir dist" in text
    assert re.search(r"gh release create \"\$tag\" dist/\*\.zip ", text)


def test_O16_Y2_plugin_concept_equals_template():
    assert (SKILL_DIR / "concept.md").read_bytes() == TEMPLATE.encode("utf-8")
    assert TEMPLATE.endswith("\n") and not TEMPLATE.endswith("\n\n")


def test_O16_Y3_plugin_json_fields():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "llm-wiki"
    assert data["version"] == "0.4.0"
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
    assert data["version"] == "0.4.0"
    desc = data["description"].lower()
    for name in NAMES:
        assert re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", desc), name
