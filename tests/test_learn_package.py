import json
import runpy
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import build_zip
from learn_support import PLUGIN_ROOT, SKILL_DIR, TEMPLATE

FILES = ["SKILL.md", "learn.py", "concept.md", "claude-ai.md"]
EXPECTED = {f"wiki-add/{f}" for f in FILES}


def copy_plugin(tmp_path) -> Path:
    dst = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist", ".pytest_cache"))
    return dst


def file_names(z: zipfile.ZipFile):
    return {n for n in z.namelist() if not n.endswith("/")}


def test_O16_Z1_zip_file_list(tmp_path):
    out = tmp_path / "out" / "wiki-add.zip"
    out.parent.mkdir()
    res = build_zip.build(PLUGIN_ROOT, out)
    assert Path(res).resolve() == out.resolve()
    with zipfile.ZipFile(out) as z:
        assert file_names(z) == EXPECTED
        for n in z.namelist():
            assert n.startswith("wiki-add/")
        for f in FILES[1:]:
            assert z.read(f"wiki-add/{f}") == (SKILL_DIR / f).read_bytes()


def test_O16_Z2_skill_name_substituted(tmp_path):
    out = tmp_path / "z.zip"
    build_zip.build(PLUGIN_ROOT, out)
    src = (SKILL_DIR / "SKILL.md").read_bytes().decode("utf-8")
    with zipfile.ZipFile(out) as z:
        got = z.read("wiki-add/SKILL.md").decode("utf-8")
    lines = src.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.rstrip() == "name: add"]
    assert idx, "source SKILL.md frontmatter must contain `name: add`"
    lines[idx[0]] = "name: wiki-add"
    assert got == "\n".join(lines)
    assert "name: wiki-add" in got.split("---")[1]


def test_O16_Z3_stray_files_excluded(tmp_path):
    plug = copy_plugin(tmp_path)
    skill = plug / "skills" / "add"
    (skill / "__pycache__").mkdir()
    (skill / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
    (skill / "tests").mkdir()
    (skill / "tests" / "t_stray.py").write_text("x = 1\n")
    (skill / "notes.txt").write_text("stray\n")
    (plug / "tests" / "extra_test.py").write_text("y = 2\n")
    out = tmp_path / "z.zip"
    build_zip.build(plug, out)
    with zipfile.ZipFile(out) as z:
        assert file_names(z) == EXPECTED
        assert not any("pyc" in n or "tests" in n or "notes" in n for n in z.namelist())


def test_O16_cli_runs_in_process(tmp_path, monkeypatch):
    out = tmp_path / "cli.zip"
    monkeypatch.setattr(sys, "argv", ["build_zip.py", "--out", str(out)])
    try:
        runpy.run_path(str(PLUGIN_ROOT / "scripts" / "build_zip.py"), run_name="__main__")
    except SystemExit as e:
        assert e.code in (None, 0)
    with zipfile.ZipFile(out) as z:
        assert file_names(z) == EXPECTED


def test_O16_cli_default_output_path(tmp_path):
    plug = copy_plugin(tmp_path)
    r = subprocess.run(
        [sys.executable, str(plug / "scripts" / "build_zip.py")], cwd=plug, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(plug / "dist" / "wiki-add.zip") as z:
        assert file_names(z) == EXPECTED


def test_O16_Y2_plugin_concept_equals_template():
    assert (SKILL_DIR / "concept.md").read_bytes() == TEMPLATE.encode("utf-8")
    assert TEMPLATE.endswith("\n") and not TEMPLATE.endswith("\n\n")


def test_O16_Y3_plugin_json_fields():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "llm-wiki"
    assert data["version"] == "0.1.2"
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
