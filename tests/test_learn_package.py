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


# ---------------- O12: wiki-learn / wiki-quiz zips, build_all, plugin.json ----------------

SKILLS = PLUGIN_ROOT / "skills"
LEARN_DIR = SKILLS / "wiki-learn"
QUIZ_DIR = SKILLS / "quiz"
WL_NAMES = ["SKILL.md", "claude-ai.md", "add.md", "add-claude-ai.md", "learn.py", "concept.md"]
WQ_NAMES = ["SKILL.md", "claude-ai.md", "quiz.py"]
WL_EXPECTED = {f"wiki-learn/{n}" for n in WL_NAMES}
WQ_EXPECTED = {f"wiki-quiz/{n}" for n in WQ_NAMES}


def zip_entries(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: (i.date_time, i.external_attr >> 16, z.read(i)) for i in z.infolist() if not i.is_dir()}


def built(tmp_path, skill, name="z.zip"):
    out = tmp_path / name
    res = build_zip.build(PLUGIN_ROOT, out, skill)
    assert Path(res).resolve() == out.resolve()
    return out


def test_O12_C27_wiki_learn_zip_entries_and_bytes(tmp_path):
    ent = zip_entries(built(tmp_path, "wiki-learn"))
    assert set(ent) == WL_EXPECTED
    assert ent["wiki-learn/SKILL.md"][2] == (LEARN_DIR / "SKILL.md").read_bytes()
    assert ent["wiki-learn/claude-ai.md"][2] == (LEARN_DIR / "claude-ai.md").read_bytes()
    assert ent["wiki-learn/add.md"][2] == (SKILL_DIR / "SKILL.md").read_bytes()
    assert ent["wiki-learn/add-claude-ai.md"][2] == (SKILL_DIR / "claude-ai.md").read_bytes()
    assert ent["wiki-learn/learn.py"][2] == (SKILL_DIR / "learn.py").read_bytes()
    assert ent["wiki-learn/concept.md"][2] == (SKILL_DIR / "concept.md").read_bytes()


def test_O12_C27_wiki_quiz_zip_entries_and_name_substitution(tmp_path):
    ent = zip_entries(built(tmp_path, "quiz"))
    assert set(ent) == WQ_EXPECTED
    assert ent["wiki-quiz/claude-ai.md"][2] == (QUIZ_DIR / "claude-ai.md").read_bytes()
    assert ent["wiki-quiz/quiz.py"][2] == (QUIZ_DIR / "quiz.py").read_bytes()
    src = (QUIZ_DIR / "SKILL.md").read_bytes().decode("utf-8")
    lines = src.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.rstrip() == "name: quiz"]
    assert idx, "source quiz SKILL.md frontmatter must contain `name: quiz`"
    lines[idx[0]] = "name: wiki-quiz"
    got = ent["wiki-quiz/SKILL.md"][2].decode("utf-8")
    assert got == "\n".join(lines)
    assert "name: wiki-quiz" in got.split("---")[1] and "name: quiz\n" not in got.split("---")[1]


def test_O12_C27_wiki_add_zip_unchanged_by_default_and_explicit(tmp_path):
    a = zip_entries(built(tmp_path, "add", "a.zip"))
    out = tmp_path / "b.zip"
    build_zip.build(PLUGIN_ROOT, out)
    assert zip_entries(out) == a
    assert set(a) == EXPECTED


@pytest.mark.parametrize("skill", ["add", "wiki-learn", "quiz"])
def test_O12_zip_metadata_fixed_and_0644(tmp_path, skill):
    p1 = built(tmp_path, skill, "one.zip")
    other = tmp_path / "later"
    other.mkdir()
    p2 = built(other, skill, "two.zip")
    e1, e2 = zip_entries(p1), zip_entries(p2)
    assert e1 == e2
    assert len({v[0] for v in e1.values()}) == 1
    assert {v[1] for v in e1.values()} == {0o644}


@pytest.mark.parametrize("skill", ["nope", "", "wiki-quiz", "wiki-add", "learn"])
def test_O12_unknown_skill_value_error(tmp_path, skill):
    with pytest.raises(ValueError):
        build_zip.build(PLUGIN_ROOT, tmp_path / "x.zip", skill)


def test_O12_stray_files_excluded_for_new_skills(tmp_path):
    plug = copy_plugin(tmp_path)
    for d in ("wiki-learn", "quiz"):
        sk = plug / "skills" / d
        (sk / "__pycache__").mkdir(exist_ok=True)
        (sk / "__pycache__" / "x.pyc").write_bytes(b"\x00pyc")
        (sk / "notes.txt").write_text("stray\n")
        (sk / "tests").mkdir(exist_ok=True)
        (sk / "tests" / "t.py").write_text("x = 1\n")
    wl, wq = tmp_path / "wl.zip", tmp_path / "wq.zip"
    build_zip.build(plug, wl, "wiki-learn")
    build_zip.build(plug, wq, "quiz")
    assert set(zip_entries(wl)) == WL_EXPECTED
    assert set(zip_entries(wq)) == WQ_EXPECTED


def test_O12_build_all(tmp_path):
    out_dir = tmp_path / "dist"
    out_dir.mkdir()
    res = build_zip.build_all(PLUGIN_ROOT, out_dir)
    assert sorted(Path(p).name for p in res) == ["wiki-add.zip", "wiki-learn.zip", "wiki-quiz.zip"]
    assert len(res) == 3
    for p in res:
        assert Path(p).parent.resolve() == out_dir.resolve() and Path(p).is_file()
    assert sorted(f.name for f in out_dir.iterdir()) == ["wiki-add.zip", "wiki-learn.zip", "wiki-quiz.zip"]
    assert set(zip_entries(out_dir / "wiki-add.zip")) == EXPECTED
    assert set(zip_entries(out_dir / "wiki-learn.zip")) == WL_EXPECTED
    assert set(zip_entries(out_dir / "wiki-quiz.zip")) == WQ_EXPECTED
    assert zip_entries(out_dir / "wiki-learn.zip") == zip_entries(built(tmp_path, "wiki-learn", "single.zip"))
    assert zip_entries(out_dir / "wiki-quiz.zip") == zip_entries(built(tmp_path, "quiz", "single2.zip"))


@pytest.mark.parametrize("skill,expected", [("wiki-learn", WL_EXPECTED), ("quiz", WQ_EXPECTED), ("add", EXPECTED)])
def test_O12_cli_skill_option(tmp_path, skill, expected):
    out = tmp_path / "cli.zip"
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), "--skill", skill,
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert set(zip_entries(out)) == expected


def test_O12_cli_all_out_dir(tmp_path):
    out_dir = tmp_path / "all"
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), "--all",
                        "--out-dir", str(out_dir)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sorted(f.name for f in out_dir.iterdir()) == ["wiki-add.zip", "wiki-learn.zip", "wiki-quiz.zip"]


def test_O12_cli_unknown_skill_fails(tmp_path):
    r = subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "build_zip.py"), "--skill", "nope",
                        "--out", str(tmp_path / "x.zip")], capture_output=True, text=True)
    assert r.returncode != 0 and not (tmp_path / "x.zip").exists()


def test_O12_plugin_json_version_and_description():
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "0.2.0"
    desc = data["description"].lower()
    assert "wiki-learn" in desc and "quiz" in desc and "add" in desc


import os
import re
import time


def test_O12_description_names_each_skill_as_a_word():
    desc = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"].lower()
    for name in ("add", "wiki-learn", "quiz"):
        assert re.search(rf"\b{re.escape(name)}\b", desc), name
    # `add` and `quiz` must not be satisfied only by being part of `wiki-learn`
    stripped = desc.replace("wiki-learn", " ")
    assert re.search(r"\badd\b", stripped), "description must name add on its own"
    assert re.search(r"\bquiz\b", stripped), "description must name quiz on its own"
    assert re.search(r"\bwiki-learn\b", desc)


def build_three(plug, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for skill, name in (("add", "a.zip"), ("wiki-learn", "l.zip"), ("quiz", "q.zip")):
        p = out_dir / name
        build_zip.build(plug, p, skill)
        paths[skill] = p.read_bytes()
    return paths


def test_O12_zip_bytes_unchanged_when_source_mtimes_change(tmp_path):
    plug = copy_plugin(tmp_path)
    first = build_three(plug, tmp_path / "b1")
    far = 4102444800  # year 2100
    for p in (plug / "skills").rglob("*"):
        os.utime(p, (far, far))
    second = build_three(plug, tmp_path / "b2")
    assert first == second


def test_O12_zip_bytes_unchanged_when_clock_is_shifted(tmp_path, monkeypatch):
    plug = copy_plugin(tmp_path)
    base = build_three(plug, tmp_path / "plain")
    real_time, real_lt, real_gt = time.time, time.localtime, time.gmtime

    def shifted():
        return real_time() + 400 * 86400

    monkeypatch.setattr(time, "time", shifted)
    monkeypatch.setattr(time, "localtime", lambda secs=None: real_lt(shifted() if secs is None else secs))
    monkeypatch.setattr(time, "gmtime", lambda secs=None: real_gt(shifted() if secs is None else secs))
    assert build_three(plug, tmp_path / "shifted") == base
