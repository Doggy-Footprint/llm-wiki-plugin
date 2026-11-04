import pytest

import learn
from learn_support import expect_error, make_root, snapshot, write


def page(root, rel, text):
    write(root / "wiki" / rel, text)


def ids(results):
    return [(r["path"], r["score"]) for r in results]


def test_O3_R1_title_stem_page_exact(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/Stemname.md", "nothing here\n")
    assert learn.related("stemname", root) == [
        {"path": "wiki/study/Stemname.md", "title": "Stemname", "level": None, "score": 10}
    ]


def test_O3_R1_title_heading_plus_body_line(tmp_path):
    # body (frontmatter excluded) includes the "# Alpha" line itself: +10 title, +1 body occurrence
    root = make_root(tmp_path)
    page(root, "study/a.md", "# Alpha Beta\n\nnothing\n")
    res = learn.related("BETA", root)
    assert res == [{"path": "wiki/study/a.md", "title": "Alpha Beta", "level": None, "score": 11}]


def test_O3_multi_term_sum_and_case(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/Alpha Beta.md", "zzz\n")
    assert [r["score"] for r in learn.related("ALPHA   beta", root)] == [20]


def test_O3_R2_tags(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/t.md", "---\ntags: [Alphabet, other]\n---\n# Zed\n")
    assert [r["score"] for r in learn.related("alpha", root)] == [5]


def test_O3_R3_aliases_inline_and_block(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/i.md", "---\naliases: [Alpine, ALPHA2]\n---\n# Zed\n")
    page(root, "study/b.md", "---\naliases:\n- Other\n- alphaBlock\n---\n# Yak\n")
    res = learn.related("alpha", root)
    assert sorted(ids(res)) == [("wiki/study/b.md", 5), ("wiki/study/i.md", 5)]


def test_O3_R2_R3_tags_and_aliases_count_once(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/t.md", "---\ntags: [alpha]\naliases: [alpha]\n---\n# Zed\n")
    assert [r["score"] for r in learn.related("alpha", root)] == [5]


def test_O3_R4_body_occurrences(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/g.md", "# Zed\ngamma gamma\nGamma\n")
    assert [r["score"] for r in learn.related("GAMMA", root)] == [3]


def test_O3_R5_body_cap_per_term(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/g.md", "# Zed\n" + "gamma " * 6 + "\ndelta delta\n")
    assert [r["score"] for r in learn.related("gamma", root)] == [5]
    assert [r["score"] for r in learn.related("gamma delta", root)] == [7]


def test_O3_R6_tie_sorted_by_title(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/Bravo.md", "---\ntags: [kw]\n---\nx\n")
    page(root, "hobby/Alpha2.md", "---\ntags: [kw]\n---\nx\n")
    res = learn.related("kw", root)
    assert [(r["title"], r["score"]) for r in res] == [("Alpha2", 5), ("Bravo", 5)]


def test_O3_score_descending(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/low.md", "kw kw\n")
    page(root, "study/mid.md", "---\ntags: [kw]\n---\nx\n")
    page(root, "study/kw-page.md", "x\n")
    assert ids(learn.related("kw", root)) == [
        ("wiki/study/kw-page.md", 10),
        ("wiki/study/mid.md", 5),
        ("wiki/study/low.md", 2),
    ]


def test_O3_zero_scores_excluded(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/a.md", "nothing\n")
    assert learn.related("kw", root) == []


def test_O3_frontmatter_not_counted_as_body(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/t.md", "---\ntags: [alpha]\n---\n# Zed\n")
    assert [r["score"] for r in learn.related("alpha", root)] == [5]


def test_O3_R7_index_log_and_non_wiki_excluded(tmp_path):
    root = make_root(
        tmp_path,
        index="# Index\nkw kw kw\n",
        log="# Log\nkw kw\n",
    )
    write(root / "raw" / "2026" / "11" / "r.md", "kw kw kw\n")
    assert learn.related("kw", root) == []
    page(root, "study/kw.md", "x\n")
    assert ids(learn.related("kw", root)) == [("wiki/study/kw.md", 10)]


def test_O3_R8_limit(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/kw-one.md", "x\n")
    page(root, "study/two.md", "---\ntags: [kw]\n---\nx\n")
    page(root, "study/three.md", "kw\n")
    page(root, "study/four.md", "kw\n")
    res = learn.related("kw", root, limit=2)
    assert ids(res) == [("wiki/study/kw-one.md", 10), ("wiki/study/two.md", 5)]
    assert len(learn.related("kw", root, limit=1)) == 1


def test_O3_R8_default_limit_10(tmp_path):
    root = make_root(tmp_path)
    for i in range(1, 13):
        page(root, f"study/p{i:02d}.md", "kw\n")
    res = learn.related("kw", root)
    assert [r["title"] for r in res] == [f"p{i:02d}" for i in range(1, 11)]


@pytest.mark.parametrize("q", ["", "   "])
def test_O3_R9_empty_query(tmp_path, q):
    root = make_root(tmp_path)
    expect_error(2, lambda: learn.related(q, root), tmp_path)


@pytest.mark.parametrize("limit", [0, -1])
def test_O3_R10_limit_below_one(tmp_path, limit):
    root = make_root(tmp_path)
    page(root, "study/kw.md", "x\n")
    expect_error(2, lambda: learn.related("kw", root, limit=limit), tmp_path, [str(limit)])


@pytest.mark.parametrize(
    "raw,expected",
    [("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", None), ("-1", None), ("x", None), ("2.5", None), (None, None)],
)
def test_O3_R11_level(tmp_path, raw, expected):
    root = make_root(tmp_path)
    lv = "" if raw is None else f"level: {raw}\n"
    page(root, "study/l.md", f"---\n{lv}tags: [kw]\n---\nx\n")
    res = learn.related("kw", root)
    assert len(res) == 1
    assert res[0]["level"] == expected
    assert type(res[0]["level"]) is type(expected)


def test_O3_R12_title_fallback_and_first_h1(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/Sub.md", "## Heading\ntext\n")
    page(root, "study/x.md", "---\ntags: [qq]\n---\nintro\n# Real Title\n# Second\n")
    res = {r["path"]: r for r in learn.related("sub qq", root)}
    assert res["wiki/study/Sub.md"]["title"] == "Sub" and res["wiki/study/Sub.md"]["score"] == 10
    assert res["wiki/study/x.md"]["title"] == "Real Title" and res["wiki/study/x.md"]["score"] == 5


def test_O3_related_does_not_write(tmp_path):
    root = make_root(tmp_path)
    page(root, "study/kw.md", "x\n")
    before = snapshot(tmp_path)
    learn.related("kw", root)
    assert snapshot(tmp_path) == before


def _r13_pages(root):
    page(root, "aaa/z.md", "---\ntags: [kw]\n---\n# Bravo\n")
    page(root, "bbb/m.md", "---\ntags: [kw]\n---\n# Charlie\n")
    page(root, "ccc/a.md", "---\ntags: [kw]\n---\n# Alpha\n")


def test_O3_R13_tie_order_follows_title_not_path_or_stem(tmp_path):
    # path order: Bravo, Charlie, Alpha; stem order: Alpha, Charlie, Bravo; title order: Alpha, Bravo, Charlie
    root = make_root(tmp_path)
    _r13_pages(root)
    res = learn.related("kw", root)
    assert [(r["title"], r["score"]) for r in res] == [("Alpha", 5), ("Bravo", 5), ("Charlie", 5)]


def test_O3_R13_limit_applied_after_sorting(tmp_path):
    root = make_root(tmp_path)
    _r13_pages(root)
    assert [r["title"] for r in learn.related("kw", root, limit=2)] == ["Alpha", "Bravo"]
    assert [r["title"] for r in learn.related("kw", root, limit=1)] == ["Alpha"]
