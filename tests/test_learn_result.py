import re
from pathlib import Path

import pytest

import learn
from learn_support import (
    D, DS, ev_line, expect_error, fm_lines, fm_parse, has_section, make_root, result_text,
    section_lines, snapshot, write,
)

PLACEHOLDER_LINK = "- [[관련 개념]] — 어떤 관계인지"

EXISTING = """---
type: concept
created: 2026-11-01
updated: 2026-11-02
level: 1
tags: [review]
sources: []
---
# Imported

## 요약
기존 요약

## 내가 정리한 것
기존 정리

## 보충 (LLM)
기존 보충

## 이해 기록
- 2026-11-02 L1 단일구조적: old

## 오해와 교정

## 연결
- [[기존]] — 관계

## 출처
- x
"""


def made(tmp_path, **kw):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    args = dict(
        title="신경망 기초", level=2, date=D, summary="요약: 한 줄", evidence="근거\n둘째줄", out_dir=out,
        misconception="오해 하나", mine="내 정리 1\n내 정리 2", supplement="보충 1",
        links=["[[링크A]] — 관계A", "[[링크B]] — 관계B"],
    )
    args.update(kw)
    res = learn.make_result(**args)
    p = Path(res["path"])
    if not p.exists():
        p = out / p.name
    return res, p


def names(sections):
    return {s.lstrip("# ").strip() for s in sections}


def test_O17_make_result_file(tmp_path):
    res, p = made(tmp_path)
    assert p.name == "2026-11-05-신경망-기초.learn.md"
    assert p.parent == tmp_path / "out"
    text = p.read_text(encoding="utf-8")
    keys = [ln.split(":", 1)[0] for ln in fm_lines(text)]
    assert keys == ["type", "version", "title", "date", "level", "summary", "evidence", "misconception"]
    meta = fm_parse(text)
    assert meta["type"] == "learn-result" and meta["version"] == "1"
    assert meta["title"] == "신경망 기초" and meta["date"] == DS and meta["level"] == "2"
    assert meta["summary"] == "요약: 한 줄"
    assert meta["evidence"] == "근거 둘째줄"
    assert meta["misconception"] == "오해 하나"
    i = [text.index(f"## {h}") for h in ("내가 정리한 것", "보충 (LLM)", "연결")]
    assert i == sorted(i)
    assert section_lines(text, "내가 정리한 것") == ["내 정리 1", "내 정리 2"]
    assert section_lines(text, "보충 (LLM)") == ["보충 1"]
    assert section_lines(text, "연결") == ["- [[링크A]] — 관계A", "- [[링크B]] — 관계B"]


def test_O17_make_result_without_misconception_and_empty_sections(tmp_path):
    _, p = made(tmp_path, misconception=None, mine="", supplement="", links=[])
    text = p.read_text(encoding="utf-8")
    assert "misconception" not in fm_parse(text)
    for h in ("내가 정리한 것", "보충 (LLM)", "연결"):
        assert has_section(text, h) and section_lines(text, h) == []


def test_O17_I9_make_result_name_collision(tmp_path):
    _, p1 = made(tmp_path)
    before = p1.read_bytes()
    _, p2 = made(tmp_path, summary="다른 요약")
    _, p3 = made(tmp_path, summary="세번째")
    assert p2.name == "2026-11-05-신경망-기초-2.learn.md"
    assert p3.name == "2026-11-05-신경망-기초-3.learn.md"
    assert p1.read_bytes() == before
    assert fm_parse(p2.read_text(encoding="utf-8"))["summary"] == "다른 요약"


@pytest.mark.parametrize("level", [0, 4])
def test_O17_make_result_valid_levels(tmp_path, level):
    _, p = made(tmp_path, level=level)
    assert fm_parse(p.read_text(encoding="utf-8"))["level"] == str(level)


@pytest.mark.parametrize(
    "kw",
    [dict(title="a/b"), dict(title="a\\b"), dict(title=""), dict(title=".x"), dict(title="x" * 101), dict(title="a\tb"),
     dict(level=-1), dict(level=5), dict(level="2")],
    ids=["slash", "backslash", "empty", "dot", "101", "tab", "lvl-1", "lvl5", "lvlstr"],
)
def test_O8_make_result_invalid_input(tmp_path, kw):
    out = tmp_path / "out"
    out.mkdir()
    args = dict(title="T", level=2, date=D, summary="s", evidence="e", out_dir=out)
    args.update(kw)
    msg = expect_error(2, lambda: learn.make_result(**args), tmp_path)
    if "title" in kw:
        t = kw["title"]
        if len(t) == 101:
            assert t in msg or "101" in msg
        elif t and t.isprintable():
            assert t in msg
        elif t:
            assert t not in msg
    else:
        assert str(kw["level"]) in msg


def test_O8_make_result_out_dir_missing(tmp_path):
    out = tmp_path / "nope"
    expect_error(2, lambda: learn.make_result("T", 2, D, "s", "e", out), tmp_path, [str(out)])
    assert not out.exists()


def import_file(tmp_path, name="r.learn.md", text=None):
    return write(tmp_path / "in" / name, result_text() if text is None else text)


def test_O17_I1_new_page_from_result(tmp_path):
    root = make_root(tmp_path)
    _, p = made(tmp_path, next_items=["[[다음A]] — 덜 이해함: 이유A"])
    res = learn.import_result(p, root)
    assert res["page"] == "wiki/study/신경망 기초.md"
    assert res["created"] is True and res["changed"] is True
    assert res["level"] == 2 and res["previous_level"] is None
    assert names(res["sections_added"]) == {"내가 정리한 것", "보충 (LLM)", "연결", "다음 학습"}
    page = (root / res["page"]).read_text(encoding="utf-8")
    meta = fm_parse(page)
    assert (meta["level"], meta["created"], meta["updated"]) == ("2", DS, DS)
    assert section_lines(page, "요약") == ["요약: 한 줄"]
    assert section_lines(page, "이해 기록") == [ev_line(2, "근거 둘째줄")]
    assert section_lines(page, "오해와 교정") == [f"- {DS} 오해 하나"]
    assert section_lines(page, "내가 정리한 것") == ["내 정리 1", "내 정리 2"]
    assert section_lines(page, "보충 (LLM)") == ["보충 1"]
    assert section_lines(page, "연결") == ["- [[링크A]] — 관계A", "- [[링크B]] — 관계B"]
    assert section_lines(page, "다음 학습") == ["- [[다음A]] — 덜 이해함: 이유A"]
    assert PLACEHOLDER_LINK not in page
    for ln in page.splitlines():
        assert not (ln.startswith("(") and ln.endswith(")")), ln
    assert "- [[신경망 기초]] — 요약: 한 줄" in (root / "wiki/index.md").read_text(encoding="utf-8")
    assert (root / "wiki/log.md").read_text(encoding="utf-8").endswith(f"- {DS} [learn] 신경망 기초: 새 페이지, L2\n")


def test_O17_I2_existing_page_appends_to_section_ends(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    p = import_file(tmp_path)
    res = learn.import_result(p, root)
    assert res["created"] is False and res["previous_level"] == 1 and res["level"] == 2
    assert names(res["sections_added"]) == {"내가 정리한 것", "보충 (LLM)", "연결"}
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "내가 정리한 것") == ["기존 정리", "내 정리 한 줄"]
    assert section_lines(page, "보충 (LLM)") == ["기존 보충", "보충 한 줄"]
    assert section_lines(page, "연결") == ["- [[기존]] — 관계", "- [[링크A]] — 관계A"]
    assert section_lines(page, "요약") == ["기존 요약"]
    assert section_lines(page, "출처") == ["- x"]
    assert section_lines(page, "이해 기록") == ["- 2026-11-02 L1 단일구조적: old", ev_line(2, "결과 근거")]
    assert fm_parse(page)["level"] == "2"


def test_O17_I3_second_import_no_change_new_page(tmp_path):
    root = make_root(tmp_path)
    _, p = made(tmp_path)
    learn.import_result(p, root)
    snap = snapshot(tmp_path)
    res = learn.import_result(p, root)
    assert res["changed"] is False
    assert res["sections_added"] == []
    assert snapshot(tmp_path) == snap


def test_O17_I3_second_import_no_change_existing_page(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    p = import_file(tmp_path)
    learn.import_result(p, root)
    snap = snapshot(tmp_path)
    res = learn.import_result(p, root)
    assert res["sections_added"] == []
    assert snapshot(tmp_path) == snap


def test_O17_I4_link_lines_deduplicated(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING.replace("- [[기존]] — 관계", "- [[링크A]] — 관계A"))
    body = "## 내가 정리한 것\n\n## 보충 (LLM)\n\n## 연결\n- [[링크A]] — 관계A\n- [[링크B]] — 관계B\n"
    res = learn.import_result(import_file(tmp_path, text=result_text(body=body)), root)
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "연결") == ["- [[링크A]] — 관계A", "- [[링크B]] — 관계B"]
    assert names(res["sections_added"]) == {"연결"}


def test_O17_I4_all_links_present_not_reported(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING.replace("- [[기존]] — 관계", "- [[링크A]] — 관계A"))
    body = "## 내가 정리한 것\n\n## 보충 (LLM)\n\n## 연결\n- [[링크A]] — 관계A\n"
    res = learn.import_result(import_file(tmp_path, text=result_text(body=body)), root)
    assert res["sections_added"] == []
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "연결") == ["- [[링크A]] — 관계A"]


def test_O17_I10_empty_sections_not_appended(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    body = "## 내가 정리한 것\n내 것만\n\n## 보충 (LLM)\n\n## 연결\n"
    res = learn.import_result(import_file(tmp_path, text=result_text(body=body)), root)
    assert names(res["sections_added"]) == {"내가 정리한 것"}
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "내가 정리한 것") == ["기존 정리", "내 것만"]
    assert section_lines(page, "보충 (LLM)") == ["기존 보충"]
    assert section_lines(page, "연결") == ["- [[기존]] — 관계"]


def test_O17_I10_all_empty(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    body = "## 내가 정리한 것\n\n## 보충 (LLM)\n\n## 연결\n"
    res = learn.import_result(import_file(tmp_path, text=result_text(body=body)), root)
    assert res["sections_added"] == []


def test_O17_import_without_misconception_adds_no_correction(tmp_path):
    root = make_root(tmp_path)
    res = learn.import_result(import_file(tmp_path), root)
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "오해와 교정") == []


def test_O17_import_with_misconception_line(tmp_path):
    root = make_root(tmp_path)
    res = learn.import_result(import_file(tmp_path, text=result_text(misconception="잘못 알던 것")), root)
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "오해와 교정") == [f"- {DS} 잘못 알던 것"]


def test_O17_I5_file_missing(tmp_path):
    root = make_root(tmp_path)
    p = tmp_path / "in" / "nope.learn.md"
    expect_error(2, lambda: learn.import_result(p, root), tmp_path, [str(p)])


def test_O17_I6_type_differs(tmp_path):
    root = make_root(tmp_path)
    p = import_file(tmp_path, text=result_text(type="concept"))
    msg = expect_error(2, lambda: learn.import_result(p, root), tmp_path)
    assert str(p) in msg or "type" in msg or "concept" in msg


@pytest.mark.parametrize("key", ["type", "version", "title", "date", "level", "summary", "evidence"])
def test_O17_I7_required_key_missing(tmp_path, key):
    root = make_root(tmp_path)
    p = import_file(tmp_path, text=result_text(**{key: None}))
    msg = expect_error(2, lambda: learn.import_result(p, root), tmp_path)
    assert key in msg or str(p) in msg


def test_O17_I7_no_frontmatter(tmp_path):
    root = make_root(tmp_path)
    p = import_file(tmp_path, text="## 내가 정리한 것\nx\n")
    expect_error(2, lambda: learn.import_result(p, root), tmp_path, [str(p)])


@pytest.mark.parametrize(
    "over",
    [dict(level="9"), dict(level="abc"), dict(level="-1"), dict(date="11/05/2026"), dict(date="2026-13-45")],
    ids=["lvl9", "lvlabc", "lvl-1", "date_fmt", "date_invalid"],
)
def test_O17_I7_malformed_values(tmp_path, over):
    root = make_root(tmp_path)
    p = import_file(tmp_path, text=result_text(**over))
    (key, value), = over.items()
    msg = expect_error(2, lambda: learn.import_result(p, root), tmp_path)
    assert str(p) in msg or key in msg or value in msg


def test_O17_I8_version_2(tmp_path):
    root = make_root(tmp_path)
    p = import_file(tmp_path, text=result_text(version="2"))
    msg = expect_error(2, lambda: learn.import_result(p, root), tmp_path)
    assert str(p) in msg or "version" in msg


def test_O17_I11_frontmatter_values_one_line(tmp_path):
    _, p = made(
        tmp_path, summary="첫째 줄\n둘째  줄\r\n셋째", misconception="오해 가\n오해  나", evidence="e1\n\ne2"
    )
    text = p.read_text(encoding="utf-8")
    lines = fm_lines(text)
    assert [ln.split(":", 1)[0] for ln in lines] == [
        "type", "version", "title", "date", "level", "summary", "evidence", "misconception",
    ]
    meta = fm_parse(text)
    assert meta["summary"] == "첫째 줄 둘째 줄 셋째"
    assert meta["misconception"] == "오해 가 오해 나"
    assert meta["evidence"] == "e1 e2"


NEXT = ["[[다음A]] — 덜 이해함: 이유A", "[[다음B]] — 이어서: 이유B"]


def test_next_section_in_result_file_after_links(tmp_path):
    _, p = made(tmp_path, next_items=NEXT)
    text = p.read_text(encoding="utf-8")
    i = [text.index(f"## {h}") for h in ("내가 정리한 것", "보충 (LLM)", "연결", "다음 학습")]
    assert i == sorted(i)
    assert section_lines(text, "다음 학습") == [f"- {n}" for n in NEXT]


def test_next_section_empty_in_result_file(tmp_path):
    _, p = made(tmp_path)
    text = p.read_text(encoding="utf-8")
    assert "## 다음 학습" in text and section_lines(text, "다음 학습") == []


def test_next_section_created_between_links_and_sources_on_old_page(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    body = "## 다음 학습\n- [[다음A]] — 덜 이해함: 이유A\n"
    res = learn.import_result(import_file(tmp_path, text=result_text(body=body)), root)
    assert names(res["sections_added"]) == {"다음 학습"}
    page = (root / res["page"]).read_text(encoding="utf-8")
    heads = [ln for ln in page.splitlines() if ln.startswith("## ")]
    assert heads[-3:] == ["## 연결", "## 다음 학습", "## 출처"]
    assert section_lines(page, "다음 학습") == ["- [[다음A]] — 덜 이해함: 이유A"]
    assert section_lines(page, "연결") == ["- [[기존]] — 관계"]


def test_next_lines_deduplicated_and_appended_without_blank(tmp_path):
    root = make_root(tmp_path)
    write(root / "wiki/study/Imported.md", EXISTING)
    first = "## 다음 학습\n- [[다음A]] — 덜 이해함: 이유A\n"
    learn.import_result(import_file(tmp_path, "a.learn.md", result_text(body=first)), root)
    second = "## 다음 학습\n- [[다음A]] — 덜 이해함: 이유A\n- [[다음B]] — 이어서: 이유B\n"
    res = learn.import_result(import_file(tmp_path, "b.learn.md", result_text(body=second)), root)
    assert names(res["sections_added"]) == {"다음 학습"}
    page = (root / res["page"]).read_text(encoding="utf-8")
    assert section_lines(page, "다음 학습") == [f"- {n}" for n in NEXT]
    res = learn.import_result(import_file(tmp_path, "c.learn.md", result_text(body=second)), root)
    assert res["sections_added"] == []


def test_links_section_created_before_existing_next_section(tmp_path):
    root = make_root(tmp_path)
    page_text = EXISTING.replace("## 연결\n- [[기존]] — 관계\n\n", "## 다음 학습\n- [[다음A]] — 이어서: x\n\n")
    write(root / "wiki/study/Imported.md", page_text)
    res = learn.import_result(import_file(tmp_path, text=result_text(body="## 연결\n- [[링크A]] — 관계A\n")), root)
    page = (root / res["page"]).read_text(encoding="utf-8")
    heads = [ln for ln in page.splitlines() if ln.startswith("## ")]
    assert heads[-3:] == ["## 연결", "## 다음 학습", "## 출처"]
    assert section_lines(page, "연결") == ["- [[링크A]] — 관계A"]
