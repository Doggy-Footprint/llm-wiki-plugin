"""O1: concept_pages equivalence partitions P1-P6."""
import pytest

import quiz
from quiz_support import bare_page, page, write


def got(root):
    return {p["path"]: p for p in quiz.concept_pages(root)}


def test_O1_P1_concept_page_fields(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/Alpha.md", title="알파 제목", created="2026-11-01", level=3,
         sections=[("요약", "x")])
    res = quiz.concept_pages(root)
    assert res == [{"path": "wiki/study/Alpha.md", "title": "알파 제목", "level": 3, "created": "2026-11-01"}]


def test_O1_P1_title_falls_back_to_stem_and_created_none(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/hobby/NoTitle.md", title=None, level=0)
    p = got(root)["wiki/hobby/NoTitle.md"]
    assert p["title"] == "NoTitle"
    assert p["created"] is None
    assert p["level"] == 0 and p["level"] is not None


def test_O1_P1_first_h1_line_is_title(tmp_path):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/T.md", "---\ntype: concept\n---\n\n## 먼저\n# 첫 제목\n# 둘째 제목\n")
    assert got(root)["wiki/study/T.md"]["title"] == "첫 제목"


def test_O1_P1_frontmatter_forms_inline_and_block(tmp_path):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/Inline.md",
              "---\ntype: concept\ncreated: 2026-11-01\ntags: [a, b]\nlevel: 2\n---\n# Inline\n")
    bare_page(root, "wiki/study/Block.md",
              "---\ntype: concept\ntags:\n- a\n- b\nsources:\n- raw/x.md\nlevel: 4\n---\n# Block\n")
    g = got(root)
    assert g["wiki/study/Inline.md"]["level"] == 2
    assert g["wiki/study/Block.md"]["level"] == 4


def test_O1_P2_non_concept_pages_excluded(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/journal/J.md", type_="journal", created="2026-11-01")
    page(root, "wiki/items/I.md", type_="item", created="2026-11-01")
    page(root, "wiki/study/C.md", created="2026-11-01")
    write(root / "wiki" / "notes.txt", "type: concept\n")
    assert set(got(root)) == {"wiki/study/C.md"}


def test_O1_P3_index_and_log_excluded_even_if_typed_concept(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/index.md", created="2026-11-01")
    page(root, "wiki/log.md", created="2026-11-01")
    page(root, "wiki/study/K.md", created="2026-11-01")
    assert set(got(root)) == {"wiki/study/K.md"}


def test_O1_P3_only_top_level_index_and_log_are_excluded(tmp_path):
    """F1 names exactly wiki/index.md and wiki/log.md."""
    root = tmp_path / "r"
    page(root, "wiki/study/index.md", created="2026-11-01")
    page(root, "wiki/study/log.md", created="2026-11-01")
    assert set(got(root)) == {"wiki/study/index.md", "wiki/study/log.md"}


def test_O1_P4_no_frontmatter_excluded(tmp_path):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/Plain.md", "# Plain\n\ntype: concept\n")
    bare_page(root, "wiki/study/Empty.md", "")
    page(root, "wiki/study/Ok.md", created="2026-11-01")
    assert set(got(root)) == {"wiki/study/Ok.md"}


def test_O1_P5_crlf_page(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/Crlf.md", title="CRLF 제목", created="2026-11-01", level=3, crlf=True,
         sections=[("요약", "줄")])
    p = got(root)["wiki/study/Crlf.md"]
    assert p == {"path": "wiki/study/Crlf.md", "title": "CRLF 제목", "level": 3, "created": "2026-11-01"}


@pytest.mark.parametrize("raw", ["5", "-1", "abc", "2.5", "10", "", "L2"])
def test_O1_P6_invalid_level_is_none(tmp_path, raw):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/L.md", f"---\ntype: concept\nlevel: {raw}\n---\n# L\n")
    assert got(root)["wiki/study/L.md"]["level"] is None


@pytest.mark.parametrize("raw,want", [("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4)])
def test_O1_P6_valid_levels_are_int(tmp_path, raw, want):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/L.md", f"---\ntype: concept\nlevel: {raw}\n---\n# L\n")
    lv = got(root)["wiki/study/L.md"]["level"]
    assert lv == want and isinstance(lv, int)


@pytest.mark.parametrize("fm,level,created", [
    ('type: "concept"\nlevel: \'2\'\ncreated: "2026-11-01"', 2, "2026-11-01"),
    ("type: 'concept'\nlevel: \"3\"\ncreated: '2026-11-02'", 3, "2026-11-02"),
    ('type: "concept"\nlevel: "0"', 0, None),
    ('type: "concept"\nlevel: "9"', None, None),
])
def test_O1_v3_quoted_frontmatter_values_unquoted(tmp_path, fm, level, created):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/Q.md", f"---\n{fm}\n---\n# Q\n")
    assert got(root)["wiki/study/Q.md"] == {"path": "wiki/study/Q.md", "title": "Q", "level": level, "created": created}


@pytest.mark.parametrize("typ", ['"concept\'', "\'concept\"", '"concept', "\"journal\""])
def test_O1_v3_mismatched_or_other_quoted_type_not_concept(tmp_path, typ):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/Q.md", f"---\ntype: {typ}\n---\n# Q\n")
    assert got(root) == {}


def test_O1_v3_non_utf8_md_skipped_others_kept(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/Ok.md", created="2026-11-01")
    write(root / "wiki" / "study" / "Bad.md", b"---\ntype: concept\ncreated: 2026-11-01\n---\n# Bad\n\xff\xfe\n")
    assert set(got(root)) == {"wiki/study/Ok.md"}


import importlib.util
from pathlib import Path

_LIB_PATH = Path(__file__).resolve().parents[3] / "scripts" / "_lib.py"


def _lib():
    spec = importlib.util.spec_from_file_location("_lib_oracle", _LIB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P7_VARIANTS = {
    "unterminated": "---\ntype: concept\ncreated: 2026-11-01\n# T\n",
    "unterminated_closing_missing_newline": "---\ntype: concept\ncreated: 2026-11-01",
    "comment_lines": "---\n# comment\ntype: concept\n  # indented comment\ncreated: 2026-11-01\n#level: 3\nlevel: 2\n---\n# T\n",
    "trailing_note": "---\ntype: concept # kind\ncreated: 2026-11-01 # note\nlevel: 2 # lv\n---\n# T\n",
    "indented_type": "---\n  type: concept\ncreated: 2026-11-01\n---\n# T\n",
    "indented_created": "---\ntype: concept\n  created: 2026-11-01\n level: 3\n---\n# T\n",
    "tab_indented_level": "---\ntype: concept\n\tlevel: 3\ncreated: 2026-11-01\n---\n# T\n",
    "note_without_space_before_hash": "---\ntype: concept\ncreated: 2026-11-01#x\nlevel: 2\n---\n# T\n",
    "plain_concept": "---\ntype: concept\ncreated: 2026-11-01\nlevel: 4\n---\n# T\n",
}


@pytest.mark.parametrize("name", sorted(P7_VARIANTS))
def test_O1_P7_differential_against_lib_frontmatter(tmp_path, name):
    lib = _lib()
    root = tmp_path / "r"
    f = bare_page(root, "wiki/study/V.md", P7_VARIANTS[name])
    meta = lib.frontmatter(f)
    is_concept = meta.get("type") == "concept"
    lv = meta.get("level")
    want_level = int(lv) if isinstance(lv, str) and lv in {"0", "1", "2", "3", "4"} else None
    cr = meta.get("created")
    want_created = cr if isinstance(cr, str) and cr else None
    pages = got(root)
    if not is_concept:
        assert pages == {}
    else:
        assert set(pages) == {"wiki/study/V.md"}
        assert pages["wiki/study/V.md"]["level"] == want_level
        assert pages["wiki/study/V.md"]["created"] == want_created


def test_O1_P7_variants_include_both_outcomes():
    """Guard against a vacuous differential: the variant set has concept and non-concept pages per _lib."""
    import tempfile

    lib = _lib()
    kinds = set()
    with tempfile.TemporaryDirectory() as d:
        for n, t in P7_VARIANTS.items():
            f = Path(d) / f"{n}.md"
            f.write_text(t, encoding="utf-8")
            kinds.add(lib.frontmatter(f).get("type") == "concept")
    assert kinds == {True, False}


def test_O1_P8_directory_named_md_ignored(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/Ok.md", created="2026-11-01")
    (root / "wiki" / "study" / "x.md").mkdir()
    assert set(got(root)) == {"wiki/study/Ok.md"}
    assert quiz.due(root, __import__("datetime").date(2026, 11, 5))["warnings"] == []
    assert quiz.frontier(root) == []
    assert quiz.deck(root, __import__("datetime").date(2026, 11, 5))["known"] == 1
    from quiz_support import expect_quiz_error

    expect_quiz_error(lambda: quiz.card(root, "wiki/study/x.md"), root)
