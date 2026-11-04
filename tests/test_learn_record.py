import pytest

import learn
from learn_support import (
    D, DS, INDEX, LOG, SOLO, TEMPLATE, collapse, ev_line, expect_error, fm_parse, has_section,
    make_root, manifest_text, read_manifest, section_lines, sha, snapshot, strip_added, write,
)

EXISTING = """---
type: concept
created: 2026-11-01
updated: 2026-11-02
level: 1
tags: [review, x]
sources: [raw/2026/11/2026-11-01-a.md]
---
# Topic

## 요약
요약 문장

## 내가 정리한 것
내용 \t탭

## 이해 기록
- 2026-11-02 L1 단일구조적: first

## 오해와 교정

## 연결
- [[Existing]] — rel

## 출처
- journal/2026/2026-11-02.md
"""

ROWS = [
    ("raw/2026/11/2026-11-03-orig.pdf", "orig.pdf", "a" * 64, "2026-11-03T00:00:00", "wiki/x.md"),
    ("raw/2026/11/2026-11-04-solo.md", "solo.md", "b" * 64, "2026-11-04T00:00:00", ""),
    ("raw/2026/11/2026-11-05-b.pdf", "b.pdf", "c" * 64, "2026-11-05T00:00:00", ""),
]
RAW_FILES = [
    "raw/2026/11/2026-11-01-a.md",
    "raw/2026/11/2026-11-03-orig.pdf",
    "raw/2026/11/2026-11-03-orig.md",
    "raw/2026/11/2026-11-04-solo.md",
    "raw/2026/11/2026-11-05-b.pdf",
    "raw/2026/11/2026-11-06-norow.md",
]


def setup_root(tmp_path, page_text=EXISTING, page_rel="study/Topic.md", rows=ROWS):
    root = make_root(tmp_path, rows=rows)
    for r in RAW_FILES:
        write(root / r, b"raw " + r.encode())
    if page_text is not None:
        write(root / "wiki" / page_rel, page_text)
    return root


def rec(root, title="Topic", level=3, evidence="ev", **kw):
    return learn.record(title, level, evidence, root, kw.pop("date", D), **kw)


def expected_new_page(title, level, summary):
    return (
        TEMPLATE.replace("{{date}}", DS)
        .replace("{{title}}", title)
        .replace("level:\n", f"level: {level}\n", 1)
        .replace("(한두 문장)", summary)
    )


# ---- O4 ----
def test_O4_T2_new_page_builtin_template(tmp_path):
    root = make_root(tmp_path)
    assert not (root / "templates").exists()
    res = rec(root, "개념A", 2, "e v", summary="한 줄 요약")
    assert res == {
        "page": "wiki/study/개념A.md",
        "created": True,
        "previous_level": None,
        "level": 2,
        "changed": True,
    }
    page = (root / res["page"]).read_text(encoding="utf-8")
    line = ev_line(2, "e v")
    assert section_lines(page, "이해 기록") == [line]
    assert section_lines(page, "요약") == ["한 줄 요약"]
    assert collapse(strip_added(page, [line])) == collapse(expected_new_page("개념A", 2, "한 줄 요약"))
    meta = fm_parse(page)
    assert (meta["created"], meta["updated"], meta["level"]) == (DS, DS, "2")
    assert (root / "wiki/index.md").read_text(encoding="utf-8") == INDEX.replace(
        "- [[Existing2]] — exist two\n", "- [[Existing2]] — exist two\n- [[개념A]] — 한 줄 요약\n"
    )
    assert (root / "wiki/log.md").read_text(encoding="utf-8") == LOG + f"- {DS} [learn] 개념A: 새 페이지, L2\n"


def test_O4_T1_new_page_root_template(tmp_path):
    root = make_root(tmp_path)
    write(
        root / "templates" / "concept.md",
        "---\ntype: concept\ncreated: {{date}}\nupdated: {{date}}\nlevel:\ntags: [custom]\nsources: []\n---\n"
        "# {{title}}\n\n## 요약\n(한두 문장)\n\n## 이해 기록\n\n## 오해와 교정\n\nCUSTOM-TEMPLATE-MARKER\n",
    )
    res = rec(root, "Cust", 1, "ev", summary="sum")
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert "CUSTOM-TEMPLATE-MARKER" in page
    assert "tags: [custom]" in page
    assert "LLM 지식으로" not in page
    assert "{{" not in page
    meta = fm_parse(page)
    assert meta["level"] == "1" and meta["created"] == DS
    assert section_lines(page, "요약") == ["sum"]
    assert section_lines(page, "이해 기록") == [ev_line(1, "ev")]


def test_O4_new_page_template_not_in_wiki_when_title_exists_elsewhere(tmp_path):
    root = setup_root(tmp_path, page_rel="hobby/Topic.md")
    rec(root, "Topic", 3)
    assert not (root / "wiki/study/Topic.md").exists()


def test_O4_index_section_missing_created_at_eof(tmp_path):
    idx = "# Index\n\n## 개념 (concepts/)\n- [[Old]] — old\n"
    root = make_root(tmp_path, index=idx)
    rec(root, "NewT", 2, "e", summary="s1")
    text = (root / "wiki/index.md").read_text(encoding="utf-8")
    assert text.startswith(idx)
    tail = text[len(idx):]
    assert tail.count("## 공부 (study/)") == 1
    assert tail.index("## 공부 (study/)") < tail.index("- [[NewT]] — s1")
    assert text.count("- [[NewT]] — s1") == 1


def test_O4_index_insert_before_next_section(tmp_path):
    root = make_root(tmp_path)
    rec(root, "Z", 0, "e", summary="sz")
    text = (root / "wiki/index.md").read_text(encoding="utf-8").split("\n")
    i = text.index("- [[Z]] — sz")
    assert text[i - 1] == "- [[Existing2]] — exist two"
    assert text[i + 1] == ""


def test_O4_T4_existing_level_updated_c14(tmp_path):
    root = setup_root(tmp_path)
    idx0 = (root / "wiki/index.md").read_bytes()
    src = "raw/2026/11/2026-11-05-b.pdf"
    res = rec(root, "Topic", 3, "ev", misconception="mis", sources=[src])
    assert res == {
        "page": "wiki/study/Topic.md", "created": False, "previous_level": 1, "level": 3, "changed": True,
    }
    page = (root / res["page"]).read_text(encoding="utf-8")
    new_ev, new_mis = ev_line(3, "ev"), f"- {DS} mis"
    exp = (
        EXISTING.replace("updated: 2026-11-02", f"updated: {DS}")
        .replace("level: 1\n", "level: 3\n", 1)
        .replace(
            "sources: [raw/2026/11/2026-11-01-a.md]",
            "sources: [raw/2026/11/2026-11-01-a.md, raw/2026/11/2026-11-05-b.pdf]",
        )
    )
    assert collapse(strip_added(page, [new_ev, new_mis])) == collapse(exp)
    assert section_lines(page, "이해 기록") == ["- 2026-11-02 L1 단일구조적: first", new_ev]
    assert section_lines(page, "오해와 교정") == [new_mis]
    assert new_ev.index("L3") and SOLO[3] in new_ev
    _, rows = read_manifest(root)
    by = {r["raw_path"]: r["extracted_to"] for r in rows}
    assert by["raw/2026/11/2026-11-05-b.pdf"] == "wiki/study/Topic.md"
    assert by["raw/2026/11/2026-11-03-orig.pdf"] == "wiki/x.md"
    assert by["raw/2026/11/2026-11-04-solo.md"] == ""
    assert (root / "wiki/log.md").read_text(encoding="utf-8") == LOG + f"- {DS} [learn] Topic: L1→L3\n"
    assert (root / "wiki/index.md").read_bytes() == idx0


def test_O4_T3_level_missing_added_before_closing(tmp_path):
    page = "---\ntype: concept\ncreated: 2026-11-01\nupdated: 2026-11-02\ntags: [review]\nsources: []\n---\n# T3\n\n## 이해 기록\n\n## 오해와 교정\n\n## 연결\n"
    root = setup_root(tmp_path, page, "study/T3.md")
    res = rec(root, "T3", 3)
    assert res["previous_level"] is None and res["changed"] is True and res["created"] is False
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert "sources: []\nlevel: 3\n---\n" in out
    assert fm_parse(out)["updated"] == DS
    exp = page.replace("updated: 2026-11-02", f"updated: {DS}").replace("sources: []\n", "sources: []\nlevel: 3\n")
    assert collapse(strip_added(out, [ev_line(3, "ev")])) == collapse(exp)
    assert (root / "wiki/log.md").read_text(encoding="utf-8").endswith(f"- {DS} [learn] T3: L-→L3\n")


def test_O4_T5_sections_missing_before_connections(tmp_path):
    page = "---\nlevel: 1\nupdated: 2026-11-02\n---\n# T5\n\n## 요약\ns\n\n## 연결\n- [[A]] — a\n\n## 출처\n- x\n"
    root = setup_root(tmp_path, page, "study/T5.md")
    res = rec(root, "T5", 2, "ev5", misconception="m5")
    out = (root / res["page"]).read_text(encoding="utf-8")
    i1, i2, i3 = out.index("## 이해 기록"), out.index("## 오해와 교정"), out.index("## 연결")
    assert i1 < i2 < i3
    assert section_lines(out, "이해 기록") == [ev_line(2, "ev5")]
    assert section_lines(out, "오해와 교정") == [f"- {DS} m5"]
    base = page.replace("level: 1", "level: 2").replace("updated: 2026-11-02", f"updated: {DS}")
    assert out[i3:] == base[base.index("## 연결"):]
    assert out[:i1].rstrip("\n") == base[: base.index("## 연결")].rstrip("\n")


def test_O4_T6_sections_missing_no_connections_appended_at_end(tmp_path):
    page = "---\nlevel: 1\nupdated: 2026-11-02\n---\n# T6\n\n## 요약\ns\n"
    root = setup_root(tmp_path, page, "study/T6.md")
    res = rec(root, "T6", 2, "ev6", misconception="m6")
    out = (root / res["page"]).read_text(encoding="utf-8")
    base = page.replace("level: 1", "level: 2").replace("updated: 2026-11-02", f"updated: {DS}")
    assert out.startswith(base)
    tail = out[len(base):]
    assert tail.index("## 이해 기록") < tail.index("## 오해와 교정")
    assert section_lines(out, "이해 기록") == [ev_line(2, "ev6")]
    assert section_lines(out, "오해와 교정") == [f"- {DS} m6"]


def test_O4_T7_same_title_other_folder_updated_in_place(tmp_path):
    root = setup_root(tmp_path, page_rel="hobby/Topic.md")
    idx0 = (root / "wiki/index.md").read_bytes()
    res = rec(root, "Topic", 3)
    assert res["page"] == "wiki/hobby/Topic.md" and res["created"] is False
    assert not (root / "wiki/study/Topic.md").exists()
    assert fm_parse((root / res["page"]).read_text(encoding="utf-8"))["level"] == "3"
    assert (root / "wiki/index.md").read_bytes() == idx0
    assert (root / "wiki/log.md").read_text(encoding="utf-8").endswith(f"- {DS} [learn] Topic: L1→L3\n")


def test_O4_new_page_with_source_updates_manifest(tmp_path):
    root = setup_root(tmp_path, page_text=None)
    src = "raw/2026/11/2026-11-05-b.pdf"
    res = rec(root, "NewS", 2, "e", summary="s", sources=[src])
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert fm_parse(page)["sources"] == [src]
    _, rows = read_manifest(root)
    assert {r["raw_path"]: r["extracted_to"] for r in rows}[src] == "wiki/study/NewS.md"


# ---- F10 / C18 ----
def test_O4_F10_idempotent_new_page(tmp_path):
    root = make_root(tmp_path)
    rec(root, "Idem", 2, "ev", summary="s")
    snap = snapshot(tmp_path)
    res = rec(root, "Idem", 2, "ev", summary="s")
    assert res["changed"] is False and res["created"] is False
    assert snapshot(tmp_path) == snap


def test_O4_F10_idempotent_with_misconception_and_sources(tmp_path):
    root = setup_root(tmp_path)
    kw = dict(misconception="mis", sources=["raw/2026/11/2026-11-05-b.pdf"])
    assert rec(root, "Topic", 3, "ev", **kw)["changed"] is True
    snap = snapshot(tmp_path)
    assert rec(root, "Topic", 3, "ev", **kw)["changed"] is False
    assert snapshot(tmp_path) == snap


@pytest.mark.parametrize(
    "kw",
    [
        dict(level=2),
        dict(evidence="other"),
        dict(date=D.replace(day=6)),
        dict(misconception="new mis"),
        dict(sources=["raw/2026/11/2026-11-05-b.pdf"]),
    ],
    ids=["level", "evidence", "date", "misconception", "source"],
)
def test_O4_F10_any_difference_writes(tmp_path, kw):
    root = setup_root(tmp_path)
    base = dict(level=3, evidence="ev")
    rec(root, "Topic", **base)
    before = snapshot(tmp_path)
    args = {**base, **kw}
    res = rec(root, "Topic", **args)
    assert res["changed"] is True
    assert snapshot(tmp_path) != before


def test_O4_F10_updated_differs_is_a_change(tmp_path):
    page = EXISTING.replace("level: 1", "level: 3").replace(
        "- 2026-11-02 L1 단일구조적: first", ev_line(3, "ev")
    )
    root = setup_root(tmp_path, page)
    res = rec(root, "Topic", 3, "ev")
    assert res["changed"] is True
    assert fm_parse((root / res["page"]).read_text(encoding="utf-8"))["updated"] == DS


# ---- O5 ----
@pytest.mark.parametrize("level", [0, 4])
def test_O5_valid_levels(tmp_path, level):
    root = make_root(tmp_path)
    res = rec(root, "Lv", level, "ev", summary="s")
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert res["level"] == level
    assert fm_parse(page)["level"] == str(level)
    assert section_lines(page, "이해 기록") == [ev_line(level, "ev")]
    assert (root / "wiki/log.md").read_text(encoding="utf-8").endswith(f"[learn] Lv: 새 페이지, L{level}\n")


@pytest.mark.parametrize("level", [-1, 5, "3", 2.5], ids=["m1", "5", "str", "float"])
def test_O5_invalid_levels_new_and_existing(tmp_path, level):
    root = setup_root(tmp_path)
    expect_error(2, lambda: rec(root, "Brand", level, "ev", summary="s"), tmp_path, [str(level)])
    expect_error(2, lambda: rec(root, "Topic", level, "ev"), tmp_path, [str(level)])


# ---- O6 ----
def test_O6_V1_hangul_title(tmp_path):
    root = make_root(tmp_path)
    res = rec(root, "한글 개념", 1, "e", summary="s")
    assert res["page"] == "wiki/study/한글 개념.md"
    assert "- [[한글 개념]] — s" in (root / "wiki/index.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "title",
    ["a/b", "a\\b", "..x", ".x", "../evil", "x" * 101],
    ids=["V2_slash", "V3_backslash", "V4_dotdot", "V5_dot", "dotdot_slash", "V9_101"],
)
def test_O6_invalid_titles_with_value_in_message(tmp_path, title):
    sandbox = tmp_path / "sandbox"
    root = make_root(sandbox)
    msg = expect_error(2, lambda: rec(root, title, 2, "e", summary="s"), tmp_path)
    assert title in msg or (len(title) == 101 and "101" in msg)


@pytest.mark.parametrize("title", ["", "a\tb", "a\nb", "a\x00b", "a\x1fb"], ids=["V6_empty", "V7_tab", "V7_nl", "V7_nul", "V7_us"])
def test_O6_V6_V7_empty_and_control(tmp_path, title):
    root = make_root(tmp_path / "sandbox")
    msg = expect_error(2, lambda: rec(root, title, 2, "e", summary="s"), tmp_path)
    escaped = {"a\tb": "a\\tb", "a\nb": "a\\nb", "a\x00b": "a\\x00b", "a\x1fb": "a\\x1fb"}
    if title:
        assert escaped[title] in msg
        assert title not in msg


def test_O6_V8_exactly_100_chars(tmp_path):
    sandbox = tmp_path / "sandbox"
    root = make_root(sandbox)
    title = "x" * 100
    res = rec(root, title, 2, "e", summary="s")
    assert res["page"] == f"wiki/study/{title}.md"
    assert (root / res["page"]).exists()
    created = set(snapshot(tmp_path)) - {"sandbox"}
    for rel in created:
        assert rel.startswith("sandbox/root")


def test_O6_V10_duplicate_title_in_two_folders(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Dup.md", "---\nlevel: 1\n---\n# Dup\n")
    write(root / "wiki/hobby/Dup.md", "---\nlevel: 1\n---\n# Dup\n")
    expect_error(2, lambda: rec(root, "Dup", 2, "e"), tmp_path, ["Dup"])


def test_O6_no_outside_writes_on_success(tmp_path):
    root = make_root(tmp_path / "sandbox")
    before = snapshot(tmp_path)
    rec(root, "OkTitle", 2, "e", summary="s")
    for rel in set(snapshot(tmp_path)) - set(before):
        assert rel.startswith("sandbox/root/wiki") or rel.startswith("sandbox/root/raw"), rel


def test_O8_summary_missing_for_new_page(tmp_path):
    root = make_root(tmp_path)
    expect_error(2, lambda: rec(root, "Brand", 2, "e"), tmp_path)


def test_O4_summary_optional_for_existing_page(tmp_path):
    root = setup_root(tmp_path)
    assert rec(root, "Topic", 3)["changed"] is True


# ---- O7 ----
def manifest_by(root):
    return {r["raw_path"]: r["extracted_to"] for r in read_manifest(root)[1]}


def test_O7_S1_original_row(tmp_path):
    root = setup_root(tmp_path)
    rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-03-orig.pdf"])
    by = manifest_by(root)
    assert by["raw/2026/11/2026-11-03-orig.pdf"] == "wiki/x.md;wiki/study/Topic.md"
    assert by["raw/2026/11/2026-11-04-solo.md"] == ""
    assert by["raw/2026/11/2026-11-05-b.pdf"] == ""


def test_O7_S1_row_with_raw_equal_md(tmp_path):
    root = setup_root(tmp_path)
    rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-04-solo.md"])
    assert manifest_by(root)["raw/2026/11/2026-11-04-solo.md"] == "wiki/study/Topic.md"


def test_O7_S2_converted_md_matches_original_row_by_stem(tmp_path):
    root = setup_root(tmp_path)
    res = rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-03-orig.md"])
    by = manifest_by(root)
    assert by["raw/2026/11/2026-11-03-orig.pdf"] == "wiki/x.md;wiki/study/Topic.md"
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert "raw/2026/11/2026-11-03-orig.md" in fm_parse(page)["sources"]


def test_O7_S3_no_row_manifest_unchanged(tmp_path):
    root = setup_root(tmp_path)
    m0 = (root / "raw/MANIFEST.csv").read_bytes()
    res = rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-06-norow.md"])
    assert (root / "raw/MANIFEST.csv").read_bytes() == m0
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert fm_parse(page)["sources"][-1] == "raw/2026/11/2026-11-06-norow.md"


@pytest.mark.parametrize("make_new", [False, True], ids=["existing", "new_page"])
def test_O7_S4_missing_source_file(tmp_path, make_new):
    root = setup_root(tmp_path)
    bad = "raw/2026/11/does-not-exist.md"
    title = "Brandnew" if make_new else "Topic"
    expect_error(
        2, lambda: rec(root, title, 3, summary="s", sources=["raw/2026/11/2026-11-05-b.pdf", bad]), tmp_path, [bad]
    )


@pytest.mark.parametrize(
    "bad",
    ["wiki/study/Other.md", "raw/../wiki/study/Other.md", "../outside.md", "raw/2026/11", "raw"],
    ids=["wiki_file", "dotdot_traversal", "outside_root", "raw_subdir", "raw_dir"],
)
def test_O7_S5_source_outside_raw_or_not_file(tmp_path, bad):
    root = setup_root(tmp_path)
    write(root / "wiki/study/Other.md", "x\n")
    write(tmp_path / "outside.md", "x\n")
    expect_error(2, lambda: rec(root, "Topic", 3, sources=[bad]), tmp_path, [bad])
    expect_error(2, lambda: rec(root, "Brandnew", 3, summary="s", sources=[bad]), tmp_path, [bad])


def test_O7_S6_inline_form_preserved(tmp_path):
    root = setup_root(tmp_path)
    rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-03-orig.pdf"])
    out = (root / "wiki/study/Topic.md").read_text(encoding="utf-8")
    assert (
        "\nsources: [raw/2026/11/2026-11-01-a.md, raw/2026/11/2026-11-03-orig.pdf]\n" in out
    )


def test_O7_S6_two_sources_in_order(tmp_path):
    root = setup_root(tmp_path)
    rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-03-orig.pdf", "raw/2026/11/2026-11-04-solo.md"])
    out = (root / "wiki/study/Topic.md").read_text(encoding="utf-8")
    assert fm_parse(out)["sources"] == [
        "raw/2026/11/2026-11-01-a.md", "raw/2026/11/2026-11-03-orig.pdf", "raw/2026/11/2026-11-04-solo.md",
    ]


def test_O7_S7_block_form_preserved(tmp_path):
    page = EXISTING.replace(
        "sources: [raw/2026/11/2026-11-01-a.md]", "sources:\n- raw/2026/11/2026-11-01-a.md"
    )
    root = setup_root(tmp_path, page)
    res = rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-03-orig.pdf"])
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert "\nsources:\n- raw/2026/11/2026-11-01-a.md\n- raw/2026/11/2026-11-03-orig.pdf\n" in out
    assert "sources: [" not in out
    assert fm_parse(out)["sources"] == ["raw/2026/11/2026-11-01-a.md", "raw/2026/11/2026-11-03-orig.pdf"]


def test_O7_S8_already_in_sources_not_duplicated_but_manifest_updated(tmp_path):
    root = setup_root(tmp_path)
    res = rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-01-a.md"])
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert fm_parse(out)["sources"] == ["raw/2026/11/2026-11-01-a.md"]
    assert out.count("raw/2026/11/2026-11-01-a.md") == 1


def test_O7_S8_extracted_to_already_has_page(tmp_path):
    rows = [
        ("raw/2026/11/2026-11-05-b.pdf", "b.pdf", "c" * 64, "2026-11-05T00:00:00", "wiki/study/Topic.md;wiki/y.md"),
    ]
    root = setup_root(tmp_path, rows=rows)
    rec(root, "Topic", 3, sources=["raw/2026/11/2026-11-05-b.pdf"])
    assert manifest_by(root)["raw/2026/11/2026-11-05-b.pdf"] == "wiki/study/Topic.md;wiki/y.md"


def test_O7_S9_key_absent_added_inline(tmp_path):
    page = "---\nlevel: 1\nupdated: 2026-11-02\n---\n# T9\n\n## 이해 기록\n"
    root = setup_root(tmp_path, page, "study/T9.md")
    res = rec(root, "T9", 2, sources=["raw/2026/11/2026-11-05-b.pdf"])
    out = (root / res["page"]).read_text(encoding="utf-8")
    meta = fm_parse(out)
    assert meta["sources"] == ["raw/2026/11/2026-11-05-b.pdf"]
    assert "\nsources: [raw/2026/11/2026-11-05-b.pdf]\n---\n" in out


# ---- O14 ----
def lf_crlf_pair(tmp_path, page, extra):
    out = {}
    for tag, text in (("lf", page), ("crlf", page.replace("\n", "\r\n"))):
        sub = tmp_path / tag
        root = setup_root(sub, text.encode("utf-8") if tag == "crlf" else text, "study/Topic.md")
        rec(root, "Topic", 3, "ev", **extra)
        out[tag] = (root / "wiki/study/Topic.md").read_bytes()
    return out


@pytest.mark.parametrize(
    "page",
    [EXISTING, "---\nlevel: 1\nupdated: 2026-11-02\n---\n# Topic\n\n## 요약\ns\n\n## 연결\n- a\n", "---\nlevel: 1\nupdated: 2026-11-02\n---\n# Topic\n\nbody\n"],
    ids=["all_sections", "sections_missing_before_links", "sections_missing_at_end"],
)
def test_O14_G1_crlf_preserved(tmp_path, page):
    pair = lf_crlf_pair(tmp_path, page, dict(misconception="mis", sources=["raw/2026/11/2026-11-05-b.pdf"]))
    import re

    assert re.search(rb"(?<!\r)\n", pair["crlf"]) is None
    assert pair["crlf"].replace(b"\r\n", b"\n") == pair["lf"]


def test_O14_G2_no_frontmatter(tmp_path):
    page = "# Topic\n\nbody text\nlevel: 9\n"
    root = setup_root(tmp_path, page, "study/Topic.md")
    res = rec(root, "Topic", 3)
    out = (root / res["page"]).read_text(encoding="utf-8")
    prefix = f"---\nlevel: 3\nupdated: {DS}\n---\n"
    assert out.startswith(prefix)
    assert out[len(prefix):].startswith(page)
    assert res["previous_level"] is None


def test_O14_G3_body_level_text_untouched(tmp_path):
    page = EXISTING.replace("## 요약", "## 요약\nlevel: 9\nthe old level: 9 text", 1)
    root = setup_root(tmp_path, page)
    res = rec(root, "Topic", 3)
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert out.count("level: 9") == 2
    assert "\nlevel: 9\nthe old level: 9 text\n" in out
    assert fm_parse(out)["level"] == "3"
    assert res["previous_level"] == 1


def test_O14_G3_level_absent_in_frontmatter_body_has_level(tmp_path):
    page = "---\nupdated: 2026-11-02\n---\n# T\nlevel: 9\n"
    root = setup_root(tmp_path, page, "study/Topic.md")
    res = rec(root, "Topic", 2)
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert fm_parse(out)["level"] == "2"
    assert "\n# T\nlevel: 9\n" in out
    assert res["previous_level"] is None


def test_O14_G4_multiline_evidence_and_misconception_one_line(tmp_path):
    root = setup_root(tmp_path)
    res = rec(root, "Topic", 3, "  line one\n\n   line   two\r\nthree\t four  ", misconception="m1\nm2   m3 ")
    out = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(out, "이해 기록")[-1] == ev_line(3, "line one line two three four")
    assert len(section_lines(out, "이해 기록")) == 2
    assert section_lines(out, "오해와 교정") == [f"- {DS} m1 m2 m3"]


def test_O7_S10_manifest_only_change(tmp_path):
    raw = "raw/2026/11/2026-11-05-x.md"
    row = (raw, "x.md", "d" * 64, "2026-11-05T00:00:00", "")
    root = make_root(tmp_path, rows=[row])
    write(root / raw, "# x\n")
    kw = dict(summary="s", sources=[raw])
    assert rec(root, "Mo", 2, "ev", **kw)["changed"] is True
    page_path = root / "wiki/study/Mo.md"
    assert manifest_by(root)[raw] == "wiki/study/Mo.md"
    page_after_first = page_path.read_bytes()
    log_after_first = (root / "wiki/log.md").read_text(encoding="utf-8")

    write(root / "raw/MANIFEST.csv", manifest_text([row]))
    res = rec(root, "Mo", 2, "ev", **kw)
    assert res["changed"] is True and res["created"] is False
    assert page_path.read_bytes() == page_after_first
    assert manifest_by(root)[raw] == "wiki/study/Mo.md"
    log = (root / "wiki/log.md").read_text(encoding="utf-8")
    assert log == log_after_first + f"- {DS} [learn] Mo: L2→L2\n"

    snap = snapshot(tmp_path)
    assert rec(root, "Mo", 2, "ev", **kw)["changed"] is False
    assert snapshot(tmp_path) == snap
