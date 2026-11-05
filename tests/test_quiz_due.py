"""O2 (FSRS replay vs in-test fsrs oracle) and O3 (due boundaries and order)."""
import datetime

import pytest

import quiz
from quiz_support import (
    bare_page, write,
    HEADER_LINE, expect_quiz_error, oracle_due, page, row, snapshot, write_csv,
)

FAR = datetime.date(2027, 3, 1)
P = "wiki/study/A.md"


def d(s):
    return datetime.date.fromisoformat(s)


def one_page_root(tmp_path, **kw):
    root = tmp_path / "r"
    kw.setdefault("created", "2026-11-01")
    page(root, P, **kw)
    return root


def item(res, path=P):
    m = {i["path"]: i for i in res["items"]}
    return m[path]


def test_constants_and_header():
    assert quiz.RATINGS == ("again", "hard", "good", "easy")
    assert quiz.REVIEWS_HEADER == ["date", "page", "rating", "mode", "source", "result_id"]
    assert (quiz.DUE_DEFAULT, quiz.DUE_MAX, quiz.FRONTIER_MAX) == (5, 10, 10)
    assert issubclass(quiz.QuizError, Exception)


def test_O2_E1_C1_no_rows(tmp_path):
    root = one_page_root(tmp_path, title="알파", level=2)
    res = quiz.due(root, d("2026-11-03"))
    assert res["warnings"] == [] and res["orphans"] == 0
    assert res["items"] == [{
        "path": P, "title": "알파", "level": 2, "due": "2026-11-03", "overdue_days": 0,
        "reviews": 0, "last_rating": None, "last_date": None,
    }]
    assert oracle_due("2026-11-01", []) == d("2026-11-03")


def test_O2_E1_no_rows_matches_oracle_for_other_created(tmp_path):
    root = one_page_root(tmp_path, created="2026-06-15")
    assert item(quiz.due(root, FAR, 10))["due"] == oracle_due("2026-06-15", []).isoformat()


def test_O2_E2_C2_good_rows(tmp_path):
    root = one_page_root(tmp_path)
    rows = [("2026-11-03", "good"), ("2026-11-14", "good")]
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    it = item(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", rows).isoformat()
    assert it["reviews"] == 2
    assert (it["last_rating"], it["last_date"]) == ("good", "2026-11-14")
    assert it["overdue_days"] == (FAR - oracle_due("2026-11-01", rows)).days


@pytest.mark.parametrize("rating", ["again", "hard", "good", "easy"])
def test_O2_E2_E3_each_rating_single_row(tmp_path, rating):
    root = one_page_root(tmp_path)
    write_csv(root, [row("2026-11-03", P, rating)])
    it = item(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", [("2026-11-03", rating)]).isoformat()
    assert it["last_rating"] == rating


def test_O2_E3_again_row_after_good(tmp_path):
    root = one_page_root(tmp_path)
    rows = [("2026-11-03", "good"), ("2026-11-14", "again")]
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    it = item(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", rows).isoformat()
    assert it["last_rating"] == "again" and it["last_date"] == "2026-11-14"


def test_O2_E4_E5_E6_broken_rows_skipped_and_named(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [
        row("2026-13-40", P, "good"),            # line 2: invalid date
        row("2026-11-03", P, "ok"),              # line 3: invalid rating
        "2026-11-03," + P,                       # line 4: short row
        row("2026-11-03", P, "good"),            # line 5: valid
    ])
    res = quiz.due(root, FAR, 10)
    it = item(res)
    assert it["due"] == oracle_due("2026-11-01", [("2026-11-03", "good")]).isoformat()
    assert it["reviews"] == 1
    assert len(res["warnings"]) == 3
    for line, w in zip((2, 3, 4), sorted(res["warnings"])):
        assert w.startswith(f"data/reviews.csv:{line}: "), w
    assert res["orphans"] == 0


@pytest.mark.parametrize("bad,line", [
    ("2026-02-30,%s,good,review,code,r1" % P, 2),
    ("11/03/2026,%s,good,review,code,r1" % P, 2),
    (",%s,good,review,code,r1" % P, 2),
    ("2026-11-03,%s,,review,code,r1" % P, 2),
])
def test_O2_E4_E5_E6_each_bad_row_alone(tmp_path, bad, line):
    """Fields listed in F3: invalid date/rating/missing fields."""
    root = one_page_root(tmp_path)
    write_csv(root, [bad])
    res = quiz.due(root, FAR, 10)
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith(f"data/reviews.csv:{line}: ")
    it = item(res)
    assert it["due"] == oracle_due("2026-11-01", []).isoformat()
    assert it["reviews"] == 0 and it["last_rating"] is None


def test_O2_E7_C7_orphan_rows(tmp_path):
    root = one_page_root(tmp_path)
    page(root, "wiki/journal/J.md", type_="journal", created="2026-11-01")
    write_csv(root, [
        row("2026-11-02", "wiki/study/Gone.md", "good"),
        row("2026-11-03", "wiki/study/Gone.md", "good"),
        row("2026-11-03", "wiki/journal/J.md", "good"),
    ])
    res = quiz.due(root, FAR, 10)
    assert res["orphans"] == 3
    assert res["warnings"] == []
    it = item(res)
    assert it["reviews"] == 0 and it["due"] == oracle_due("2026-11-01", []).isoformat()


def test_O2_E7_single_orphan_row_C7(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [row("2026-11-02", "wiki/study/Gone.md", "good")])
    res = quiz.due(root, d("2026-11-03"))
    assert res["orphans"] == 1 and len(res["items"]) == 1


def test_O2_E8_created_missing_uses_updated(tmp_path):
    root = tmp_path / "r"
    page(root, P, created=None, updated="2026-10-20")
    res = quiz.due(root, FAR, 10)
    assert item(res)["due"] == oracle_due("2026-10-20", []).isoformat()
    assert res["warnings"] == []


def test_O2_E8_created_wins_over_updated(tmp_path):
    root = tmp_path / "r"
    page(root, P, created="2026-10-01", updated="2026-11-04")
    assert item(quiz.due(root, FAR, 10))["due"] == oracle_due("2026-10-01", []).isoformat()


def test_O2_E9_C8_no_created_nor_updated_warns_and_excluded(tmp_path):
    root = one_page_root(tmp_path)
    page(root, "wiki/study/NoDate.md", created=None)
    page(root, "wiki/journal/J.md", type_="journal", created="2026-01-01")
    page(root, "wiki/index.md", created="2026-01-01")
    page(root, "wiki/log.md", created="2026-01-01")
    res = quiz.due(root, FAR, 10)
    assert [i["path"] for i in res["items"]] == [P]
    assert len(res["warnings"]) == 1
    assert res["warnings"][0].startswith("wiki/study/NoDate.md")


def test_O2_E10_row_before_created_is_ordered_by_date(tmp_path):
    root = one_page_root(tmp_path)
    rows = [("2026-10-30", "good")]
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    it = item(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", rows).isoformat()


def test_O2_E10_same_date_synthetic_first(tmp_path):
    from quiz_support import oracle_events_due

    root = one_page_root(tmp_path)
    rows = [("2026-11-01", "easy")]
    synthetic_first = oracle_events_due([("2026-11-01", "good"), ("2026-11-01", "easy")])
    real_first = oracle_events_due([("2026-11-01", "easy"), ("2026-11-01", "good")])
    assert synthetic_first != real_first  # the input distinguishes the two orders
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    got_due = item(quiz.due(root, FAR, 10))["due"]
    assert got_due == oracle_due("2026-11-01", rows).isoformat()
    assert got_due == synthetic_first.isoformat()
    assert got_due != real_first.isoformat()


@pytest.mark.parametrize("rows", [
    [("2026-11-05", "good"), ("2026-11-05", "again")],
    [("2026-11-05", "again"), ("2026-11-05", "good")],
    [("2026-11-14", "good"), ("2026-11-03", "good")],
    [("2026-11-20", "hard"), ("2026-11-03", "easy"), ("2026-11-10", "again"), ("2026-11-03", "good")],
])
def test_O2_E10_file_order_and_date_sorting(tmp_path, rows):
    root = one_page_root(tmp_path)
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    it = item(quiz.due(root, FAR, 10))
    assert it["due"] == oracle_due("2026-11-01", rows).isoformat()
    assert it["reviews"] == len(rows)


def test_O2_rows_of_other_pages_do_not_leak(tmp_path):
    root = one_page_root(tmp_path)
    page(root, "wiki/study/B.md", created="2026-11-01")
    write_csv(root, [row("2026-11-03", "wiki/study/B.md", "easy")])
    res = quiz.due(root, FAR, 10)
    assert item(res, P)["due"] == oracle_due("2026-11-01", []).isoformat()
    assert item(res, "wiki/study/B.md")["due"] == oracle_due("2026-11-01", [("2026-11-03", "easy")]).isoformat()


def test_O2_no_data_dir_is_fine_and_creates_nothing(tmp_path):
    root = one_page_root(tmp_path)
    before = snapshot(root)
    quiz.due(root, FAR, 10)
    assert snapshot(root) == before


def test_O2_header_only_csv(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [])
    res = quiz.due(root, d("2026-11-03"))
    assert res["warnings"] == [] and len(res["items"]) == 1


# ---------------- O3 ----------------

def test_O3_C3_due_date_boundary_three_values(tmp_path):
    root = one_page_root(tmp_path)  # due 2026-11-03
    assert quiz.due(root, d("2026-11-02"))["items"] == []
    on = quiz.due(root, d("2026-11-03"))["items"]
    assert len(on) == 1 and on[0]["overdue_days"] == 0
    after = quiz.due(root, d("2026-11-04"))["items"]
    assert len(after) == 1 and after[0]["overdue_days"] == 1


def make_many(tmp_path, n, created="2026-11-01"):
    root = tmp_path / "r"
    for i in range(n):
        page(root, f"wiki/study/P{i:02d}.md", created=created)
    return root


@pytest.mark.parametrize("limit", [0, 11, -1])
def test_O3_C4_limit_out_of_range(tmp_path, limit):
    root = make_many(tmp_path, 3)
    expect_quiz_error(lambda: quiz.due(root, d("2026-11-03"), limit), root)


@pytest.mark.parametrize("limit", [1, 10])
def test_O3_C4_limit_accepted(tmp_path, limit):
    root = make_many(tmp_path, 12)
    assert len(quiz.due(root, d("2026-11-03"), limit)["items"]) == limit


def test_O3_default_limit_is_five(tmp_path):
    root = make_many(tmp_path, 7)
    assert len(quiz.due(root, d("2026-11-03"))["items"]) == 5


def test_O3_limit_cuts_after_sorting(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/A.md", created="2026-11-01")  # overdue 0
    page(root, "wiki/study/B.md", created="2026-10-28")  # overdue 4
    res = quiz.due(root, d("2026-11-03"), 1)
    assert [i["path"] for i in res["items"]] == ["wiki/study/B.md"]


def test_O3_C5_order_overdue_desc_then_path_asc(tmp_path):
    root = tmp_path / "r"
    # titles deliberately sort opposite to paths
    page(root, "wiki/study/D.md", title="Aaa", created="2026-11-01")  # overdue 0
    page(root, "wiki/study/C.md", title="Zed", created="2026-10-28")  # overdue 4
    page(root, "wiki/study/A.md", title="Mid", created="2026-10-28")  # overdue 4
    res = quiz.due(root, d("2026-11-03"))
    assert [(i["path"], i["overdue_days"]) for i in res["items"]] == [
        ("wiki/study/A.md", 4), ("wiki/study/C.md", 4), ("wiki/study/D.md", 0),
    ]


def test_O3_item_fields_for_page_with_rows(tmp_path):
    root = one_page_root(tmp_path, title="Alpha", level=1)
    rows = [("2026-11-02", "hard"), ("2026-11-04", "good")]
    write_csv(root, [row(dt, P, r) for dt, r in rows])
    it = item(quiz.due(root, FAR, 10))
    assert set(it) == {"path", "title", "level", "due", "overdue_days", "reviews", "last_rating", "last_date"}
    assert it["title"] == "Alpha" and it["level"] == 1
    assert (it["last_rating"], it["last_date"]) == ("good", "2026-11-04")


# ---------------- v3 clarifications ----------------

def test_O2_v3_last_is_last_in_replay_order_not_file_order(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [row("2026-11-14", P, "good"), row("2026-11-03", P, "again")])
    it = item(quiz.due(root, FAR, 10))
    assert (it["last_rating"], it["last_date"]) == ("good", "2026-11-14")
    assert it["reviews"] == 2


def test_O2_v3_last_same_date_takes_later_file_row(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [row("2026-11-05", P, "again"), row("2026-11-05", P, "easy"), row("2026-11-02", P, "hard")])
    it = item(quiz.due(root, FAR, 10))
    assert (it["last_rating"], it["last_date"]) == ("easy", "2026-11-05")


@pytest.mark.parametrize("bad", [
    "2026-11-03,%s,GOOD,review,code,r1" % P,        # case-sensitive rating
    "2026-11-03,%s,Good,review,code,r1" % P,
    "2026-11-03,%s,good,review,code" % P,           # 5 columns
    "2026-11-03,%s,good" % P,
    "2026-11-03,,good,review,code,r1",              # empty page
    "2026-13-03,%s,good,review,code,r1" % P,
])
def test_O2_v3_broken_row_definition(tmp_path, bad):
    root = one_page_root(tmp_path)
    write_csv(root, [bad])
    res = quiz.due(root, FAR, 10)
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith("data/reviews.csv:2: ")
    assert res["orphans"] == 0
    assert item(res)["reviews"] == 0


@pytest.mark.parametrize("good_row", [
    "2026-11-03,%s,good,other,web,r1" % P,   # mode/source values are not checked
    "2026-11-03,%s,good,,,"  % P,            # empty mode/source/result_id
    "2026-11-03,%s,good,review,code,r1,extra" % P,
])
def test_O2_v3_mode_source_result_id_not_checked(tmp_path, good_row):
    root = one_page_root(tmp_path)
    write_csv(root, [good_row])
    res = quiz.due(root, FAR, 10)
    assert res["warnings"] == []
    it = item(res)
    assert it["reviews"] == 1
    assert it["due"] == oracle_due("2026-11-01", [("2026-11-03", "good")]).isoformat()


def test_O2_v3_header_mismatch_warns_line_one_rows_still_read(tmp_path):
    root = one_page_root(tmp_path)
    write(root / "data" / "reviews.csv", "date,page,rating\n" + row("2026-11-03", P, "good") + "\n")
    res = quiz.due(root, FAR, 10)
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith("data/reviews.csv:1: ")
    assert item(res)["reviews"] == 1


def test_O2_v3_matching_header_no_warning(tmp_path):
    root = one_page_root(tmp_path)
    write_csv(root, [row("2026-11-03", P, "good")])
    assert quiz.due(root, FAR, 10)["warnings"] == []


def test_O2_v3_non_utf8_wiki_file_warned_and_skipped(tmp_path):
    root = one_page_root(tmp_path)
    write(root / "wiki" / "study" / "Bad.md", b"---\ntype: concept\ncreated: 2026-11-01\n---\n# Bad\n\xff\xfe\n")
    write_csv(root, [row("2026-11-03", "wiki/study/Bad.md", "good")])
    res = quiz.due(root, FAR, 10)
    assert [i["path"] for i in res["items"]] == [P]
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith("wiki/study/Bad.md")
    assert res["orphans"] == 1  # not a concept page, so its csv row is an orphan


def test_O2_v3_quoted_frontmatter_created_schedules(tmp_path):
    root = tmp_path / "r"
    bare_page(root, P, '---\ntype: "concept"\ncreated: \'2026-11-01\'\nlevel: "2"\n---\n# A\n')
    it = item(quiz.due(root, d("2026-11-03")))
    assert it["due"] == "2026-11-03" and it["level"] == 2


# ---------------- v4: E11 / E12 ----------------

@pytest.mark.parametrize("bad_created", ["2026-02-30", "soon", "2026-13-01", "11/01/2026"])
def test_O2_E11_invalid_created_falls_back_to_updated(tmp_path, bad_created):
    root = tmp_path / "r"
    page(root, P, created=bad_created, updated="2026-10-20")
    res = quiz.due(root, FAR, 10)
    assert item(res)["due"] == oracle_due("2026-10-20", []).isoformat()
    assert [i["path"] for i in res["items"]] == [P]


@pytest.mark.parametrize("created,updated", [
    ("2026-02-30", None), ("soon", None), ("soon", "2026-02-30"), ("soon", "later"), ("2026-02-30", "soon"),
])
def test_O2_E12_invalid_created_and_no_valid_updated_excluded_with_warning(tmp_path, created, updated):
    root = tmp_path / "r"
    page(root, P, created=created, updated=updated)
    page(root, "wiki/study/Ok.md", created="2026-11-01")
    res = quiz.due(root, FAR, 10)
    assert [i["path"] for i in res["items"]] == ["wiki/study/Ok.md"]
    assert len(res["warnings"]) == 1 and res["warnings"][0].startswith(P)
