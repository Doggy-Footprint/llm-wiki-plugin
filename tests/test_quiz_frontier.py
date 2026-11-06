import pytest

import quiz
from quiz_support import expect_quiz_error, page, snapshot


def links(*targets):
    return [("연결", "\n".join(f"- {t} — r" for t in targets))]


def test_O6_C12_spec_example(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/A.md", level=3, sections=links("[[X]]", "[[Y]]", "[[B]]", "[[관련 개념]]", "[[Z|z]]", "[[W#h]]"))
    page(root, "wiki/study/B.md", level=1, sections=links("[[X]]"))
    assert quiz.frontier(root) == [
        {"title": "X", "from": ["A", "B"], "max_level": 3},
        {"title": "W", "from": ["A"], "max_level": 3},
        {"title": "Y", "from": ["A"], "max_level": 3},
        {"title": "Z", "from": ["A"], "max_level": 3},
    ]


def test_O6_rule_sort_keys_len_then_level_then_title(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", level=3, sections=links("[[X]]", "[[Y]]", "[[Z]]", "[[W]]"))
    page(root, "wiki/s/B.md", level=1, sections=links("[[X]]"))
    page(root, "wiki/s/C.md", level=4, sections=links("[[Zq]]"))
    page(root, "wiki/s/D.md", sections=links("[[P]]"))
    page(root, "wiki/s/E.md", level=0, sections=links("[[R]]"))
    got = quiz.frontier(root)
    assert [(g["title"], g["max_level"]) for g in got] == [
        ("X", 3),
        ("Zq", 4),
        ("W", 3), ("Y", 3), ("Z", 3),
        ("R", 0),
        ("P", None),
    ]
    assert got[0]["from"] == ["A", "B"]


def test_O6_max_level_none_when_all_linkers_have_no_level(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=links("[[X]]"))
    page(root, "wiki/s/B.md", level=2, sections=links("[[X]]"))
    page(root, "wiki/s/C.md", sections=links("[[N]]"))
    got = {g["title"]: g for g in quiz.frontier(root)}
    assert got["X"]["max_level"] == 2
    assert got["N"]["max_level"] is None


def test_O6_from_is_sorted_unique_titles_not_filenames(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/Amy.md", title="Beta", sections=links("[[X]]", "[[X]]"))
    page(root, "wiki/s/Zed.md", title="Alpha", sections=links("[[X]]"))
    page(root, "wiki/s/Mid.md", title="Gamma", sections=links("[[X|again]]", "[[X#h]]"))
    assert quiz.frontier(root) == [{"title": "X", "from": ["Alpha", "Beta", "Gamma"], "max_level": None}]


def test_O6_existing_target_in_any_wiki_folder_is_not_frontier(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=links("[[Deep]]", "[[Jr]]", "[[Missing]]"))
    page(root, "wiki/a/b/c/Deep.md", created="2026-11-01")
    page(root, "wiki/journal/Jr.md", type_="journal")
    assert [g["title"] for g in quiz.frontier(root)] == ["Missing"]


def test_O6_placeholder_alias_anchor(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=links("[[관련 개념]]", "[[Z|z]]", "[[W#h]]", "[[V#h|v]]"))
    assert [g["title"] for g in quiz.frontier(root)] == ["V", "W", "Z"]


def test_O6_only_connection_section_of_concept_pages_count(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=[("요약", "[[InSummary]]"), ("연결", "- [[In]]"), ("출처", "- [[InSrc]]")])
    page(root, "wiki/journal/J.md", type_="journal", sections=links("[[FromJournal]]"))
    page(root, "wiki/index.md", sections=links("[[FromIndex]]"))
    assert [g["title"] for g in quiz.frontier(root)] == ["In"]


def test_O6_no_missing_targets_gives_empty(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=links("[[B]]"))
    page(root, "wiki/s/B.md", sections=links("[[A]]"))
    assert quiz.frontier(root) == []


def test_O6_fresh_root_without_pages(tmp_path):
    root = tmp_path / "r"
    (root / "wiki").mkdir(parents=True)
    assert quiz.frontier(root) == []


def many(tmp_path, n):
    root = tmp_path / "r"
    body = [f"[[T{i:02d}]]" for i in range(1, n + 1)]
    for k in range(0, n, 5):
        page(root, f"wiki/s/P{k}.md", sections=links(*body[k:k + 5]))
    return root


def test_O6_limit_default_ten(tmp_path):
    root = many(tmp_path, 12)
    assert [g["title"] for g in quiz.frontier(root)] == [f"T{i:02d}" for i in range(1, 11)]


@pytest.mark.parametrize("limit,count", [(1, 1), (10, 10)])
def test_O6_limit_accepted(tmp_path, limit, count):
    root = many(tmp_path, 12)
    assert len(quiz.frontier(root, limit)) == count


@pytest.mark.parametrize("limit", [0, 11, -3])
def test_O6_limit_rejected(tmp_path, limit):
    root = many(tmp_path, 12)
    expect_quiz_error(lambda: quiz.frontier(root, limit), root)


def test_O6_does_not_write(tmp_path):
    root = many(tmp_path, 6)
    before = snapshot(root)
    quiz.frontier(root)
    assert snapshot(root) == before


def test_O6_v3_no_link_cap_missing_targets_beyond_tenth_count(tmp_path):
    root = tmp_path / "r"
    existing = [f"E{i:02d}" for i in range(1, 11)]
    for e in existing:
        page(root, f"wiki/s/{e}.md", created="2026-11-05")
    page(root, "wiki/s/A.md", sections=links(*[f"[[{e}]]" for e in existing], "[[Late11]]", "[[Late12]]"))
    assert quiz.frontier(root) == [
        {"title": "Late11", "from": ["A"], "max_level": None},
        {"title": "Late12", "from": ["A"], "max_level": None},
    ]


def test_O6_v3_quoted_frontmatter_page_counts(tmp_path):
    root = tmp_path / "r"
    (root / "wiki" / "s").mkdir(parents=True)
    (root / "wiki" / "s" / "Q.md").write_text(
        "---\ntype: 'concept'\nlevel: \"2\"\n---\n# Q\n\n## 연결\n- [[Gone]]\n", encoding="utf-8")
    assert quiz.frontier(root) == [{"title": "Gone", "from": ["Q"], "max_level": 2}]


def test_O6_non_utf8_page_contributes_no_links(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=links("[[Real]]"))
    (root / "wiki" / "s" / "Bad.md").write_bytes(
        b"---\ntype: concept\n---\n# Bad\n\n## \xec\x97\xb0\xea\xb2\xb0\n- [[Ghost]]\n\xff\xfe\n")
    assert [g["title"] for g in quiz.frontier(root)] == ["Real"]


def test_next_study_section_links_count_as_frontier(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", level=2, sections=[("연결", "- [[X]] — r"), ("다음 학습", "- [[N]] — 덜 이해함: r\n- [[X]] — 이어서: r")])
    page(root, "wiki/s/B.md", level=1, sections=[("다음 학습", "- [[N]] — 이어서: r")])
    assert quiz.frontier(root) == [
        {"title": "N", "from": ["A", "B"], "max_level": 2},
        {"title": "X", "from": ["A"], "max_level": 2},
    ]


def test_card_links_still_only_from_connection_section(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", sections=[("연결", "- [[X]] — r"), ("다음 학습", "- [[N]] — 이어서: r")])
    assert quiz.card(root, "wiki/s/A.md")["links"] == ["X"]
