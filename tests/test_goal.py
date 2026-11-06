import csv
import datetime
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "wiki-goal"))

import goal  # noqa: E402
import index  # noqa: E402
from goal_poc_support import (  # noqa: E402
    CLIMBING, CONCEPT_PAGES, ENTITY, GROUP_BY, JOIN, LINK_HEADER, NORMALIZATION, SUBQUERY,
    TRANSACTION, WINDOW, add_extra_goal, digest_tree, fixture_embedder, goal_toml, link,
    make_root, read_jsonl, read_links, review, run_cli, write_goal, write_links, write_page, write_reviews,
)

GOAL = "sqld-fixture"


def gcli(root, argv, capsys, **kw):
    return run_cli(goal, ["--root", root, *argv], capsys, **kw)


def links_bytes(root):
    p = Path(root) / "data" / "goal_links.csv"
    return p.read_bytes() if p.exists() else None


def all_files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())


BASE = """id = "g1"
title = "기본 목표"
kind = "official"

[[areas]]
id = "a1"
name = "영역1"
weight = 1

[[areas]]
id = "a2"
name = "영역2"
weight = 2

[[concepts]]
id = "c1"
name = "개념1"
area = "a1"

[[concepts]]
id = "c2"
name = "개념2"
area = "a1"

[[concepts]]
id = "c3"
name = "개념3"
area = "a2"

[[prereqs]]
from = "c1"
to = "c2"
basis = "user"
"""


def test_load_goal_valid_preserves_file_order(tmp_path):
    root = make_root(tmp_path)
    g = goal.load_goal(root, GOAL)
    assert g["id"] == GOAL and g["title"] == "SQLD 픽스처" and g["kind"] == "official"
    assert "source" in g
    assert [a["id"] for a in g["areas"]] == ["modeling", "sql"]
    assert [a["name"] for a in g["areas"]] == ["데이터 모델링의 이해", "SQL 기본 및 활용"]
    assert [a["weight"] for a in g["areas"]] == [10, 40]
    assert [(c["id"], c["area"]) for c in g["concepts"]] == [
        ("normalization", "modeling"), ("join", "sql"), ("window-function", "sql"),
        ("subquery", "sql"), ("group-by", "sql"),
    ]
    assert [c["name"] for c in g["concepts"]][:2] == ["정규화", "조인"]
    assert g["concepts"][0]["aliases"] == ["normalization"]
    assert g["concepts"][0]["section"] == "데이터 모델과 성능"
    assert [(p["from"], p["to"], p["basis"]) for p in g["prereqs"]] == [
        ("join", "subquery", "syllabus-order"),
        ("join", "window-function", "official"),
        ("group-by", "window-function", "inferred"),
    ]


def test_load_goal_minimal_valid_base(tmp_path):
    write_goal(tmp_path, "g1", BASE)
    g = goal.load_goal(tmp_path, "g1")
    assert [c["id"] for c in g["concepts"]] == ["c1", "c2", "c3"]


def test_load_goal_missing_file(tmp_path):
    (tmp_path / "goals").mkdir()
    with pytest.raises(goal.GoalError, match="goal not found: nope"):
        goal.load_goal(tmp_path, "nope")


VIOLATIONS = [
    pytest.param(lambda t: t.replace('id = "c3"', 'id = "Bad_ID"'), ["Bad_ID"], id="id-pattern"),
    pytest.param(lambda t: t.replace('id = "g1"', 'id = "other"'), ["id", "other"], id="stem-mismatch"),
    pytest.param(lambda t: t.replace('kind = "official"', 'kind = "casual"'), ["kind", "casual"], id="bad-kind"),
    pytest.param(lambda t: t.replace('id = "c3"', 'id = "c2"'), ["c2"], id="duplicate-concept-id"),
    pytest.param(lambda t: t.replace('area = "a2"', 'area = "nope"'), ["nope", "area"], id="unknown-area"),
    pytest.param(lambda t: t.replace('to = "c2"', 'to = "ghost"'), ["ghost"], id="unknown-prereq-target"),
    pytest.param(lambda t: t.replace('to = "c2"', 'to = "c1"'), ["c1"], id="self-prereq"),
    pytest.param(lambda t: t + '\n[[prereqs]]\nfrom = "c2"\nto = "c1"\nbasis = "user"\n',
                 ["c1", "c2", "cycle"], id="cycle"),
    pytest.param(lambda t: t.replace("weight = 1", "weight = 0"), ["weight", "a1"], id="weight-zero"),
    pytest.param(lambda t: t.replace("weight = 1", "weight = -1.5"), ["weight", "a1"], id="weight-negative"),
    pytest.param(lambda t: t + '\n[[areas]]\nid = "a3"\nname = "빈 영역"\nweight = 1\n',
                 ["a3"], id="empty-area"),
    pytest.param(lambda t: t.replace('basis = "user"', 'basis = "guess"'), ["basis", "guess"], id="bad-basis"),
    pytest.param(lambda t: t + "\nthis is = not [[ toml\n", [], id="toml-syntax"),
]


@pytest.mark.parametrize("mutate,tokens", VIOLATIONS)
def test_load_goal_violations(tmp_path, mutate, tokens):
    write_goal(tmp_path, "g1", mutate(BASE))
    before = all_files(tmp_path)
    digest = digest_tree(tmp_path, "goals")
    with pytest.raises(goal.GoalError) as info:
        goal.load_goal(tmp_path, "g1")
    if tokens:
        assert any(t in str(info.value) for t in tokens), str(info.value)
    assert all_files(tmp_path) == before
    assert digest_tree(tmp_path, "goals") == digest


EXPECTED_QUERIES = {"정규화 normalization", "조인 join", "윈도우 함수 window function",
                    "서브쿼리 subquery", "GROUP BY"}
TOP_PAGE = {"normalization": NORMALIZATION, "join": JOIN, "window-function": WINDOW,
            "subquery": SUBQUERY, "group-by": GROUP_BY}


def test_suggest_keyword_adds_candidates(tmp_path):
    root = make_root(tmp_path)
    res = goal.suggest(root, GOAL, k=2, date="2026-01-02")
    assert res["goal"] == GOAL
    assert [c["id"] for c in res["concepts"]] == ["normalization", "join", "window-function",
                                                  "subquery", "group-by"]
    assert [c["name"] for c in res["concepts"]][:2] == ["정규화", "조인"]
    total = 0
    for c in res["concepts"]:
        assert 1 <= len(c["candidates"]) <= 2
        assert c["candidates"][0]["page"] == TOP_PAGE[c["id"]]
        assert all(x["status"] == "candidate" for x in c["candidates"])
        total += len(c["candidates"])
    assert res["added"] == total

    raw = links_bytes(root).decode("utf-8")
    assert raw.splitlines()[0] == ",".join(LINK_HEADER)
    rows = read_links(root)
    assert len(rows) == res["added"]
    keys = [(r["goal"], r["concept"], r["page"]) for r in rows]
    assert keys == sorted(keys)
    by_key = {(r["concept"], r["page"]): r for r in rows}
    for c in res["concepts"]:
        for cand in c["candidates"]:
            row = by_key[(c["id"], cand["page"])]
            assert row["goal"] == GOAL and row["status"] == "candidate"
            assert row["method"] == "keyword" and row["date"] == "2026-01-02"
            assert float(row["score"]) == pytest.approx(cand["score"], abs=1e-6)
    assert sorted(p.name for p in (root / "data").iterdir()) == ["goal_links.csv", "reviews.csv"]

    log = read_jsonl(root, "search-log.jsonl")
    assert [e["source"] for e in log] == ["suggest"] * 5
    assert {e["query"] for e in log} == EXPECTED_QUERIES
    assert all(e["k"] == 2 for e in log)


def test_suggest_twice_adds_nothing_second_time(tmp_path):
    root = make_root(tmp_path)
    first = goal.suggest(root, GOAL, k=3, date="2026-01-02")
    assert first["added"] > 0
    snapshot = links_bytes(root)
    second = goal.suggest(root, GOAL, k=3, date="2026-02-02")
    assert second["added"] == 0
    assert links_bytes(root) == snapshot


def test_suggest_keeps_confirmed_and_rejected_rows_and_adds_only_new_keys(tmp_path):
    root = make_root(tmp_path)
    goal.suggest(root, GOAL, k=1, date="2026-01-02")
    goal.set_status(root, GOAL, [("join", JOIN)], "confirmed", date="2026-01-20")
    goal.set_status(root, GOAL, [("group-by", GROUP_BY)], "rejected", date="2026-01-21")
    before = {(r["concept"], r["page"]): r for r in read_links(root)}
    assert before[("join", JOIN)]["status"] == "confirmed"
    assert before[("group-by", GROUP_BY)]["status"] == "rejected"

    res = goal.suggest(root, GOAL, k=3, date="2026-03-01")
    after = {(r["concept"], r["page"]): r for r in read_links(root)}
    assert res["added"] > 0
    assert len(after) == len(before) + res["added"]
    for key, row in before.items():
        assert after[key] == row
    for key in set(after) - set(before):
        assert after[key]["status"] == "candidate" and after[key]["date"] == "2026-03-01"
    join = next(c for c in res["concepts"] if c["id"] == "join")
    assert {x["page"]: x["status"] for x in join["candidates"]}[JOIN] == "confirmed"


def test_suggest_concept_without_hits_has_no_candidates(tmp_path):
    root = make_root(tmp_path)
    write_goal(root, "lone", goal_toml("lone", [("a", 1)], [("x", "a", "쑯쑯쑯")]))
    res = goal.suggest(root, "lone", date="2026-01-02")
    assert res["added"] == 0
    assert res["concepts"][0]["candidates"] == []


def test_suggest_hybrid_method_with_embedder(tmp_path):
    root = make_root(tmp_path)
    emb = fixture_embedder()
    index.embed(root, emb)
    res = goal.suggest(root, GOAL, k=2, embedder=fixture_embedder(), date="2026-01-02")
    assert res["added"] > 0
    assert {r["method"] for r in read_links(root)} == {"hybrid"}
    assert {e["mode"] for e in read_jsonl(root, "search-log.jsonl")} == {"hybrid"}


def test_suggest_default_date_is_today(tmp_path):
    root = make_root(tmp_path)
    lo = datetime.date.today().isoformat()
    goal.suggest(root, GOAL, k=1)
    hi = datetime.date.today().isoformat()
    assert {r["date"] for r in read_links(root)} <= {lo, hi}


def test_cli_suggest_without_key_uses_keyword(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = gcli(root, ["suggest", GOAL, "--k", "2", "--date", "2026-01-02"], capsys, environ={})
    assert code == 0, err
    assert len(out.splitlines()) == 1 and out.endswith("\n")
    res = json.loads(out)
    assert res["added"] == len(read_links(root)) > 0
    assert {r["method"] for r in read_links(root)} == {"keyword"}
    assert "정규화" in out and "\\u" not in out


def test_confirm_without_existing_row_is_manual(tmp_path):
    root = make_root(tmp_path)
    res = goal.set_status(root, GOAL, [("join", JOIN)], "confirmed", date="2026-02-01")
    assert res == {"goal": GOAL, "updated": 0, "added": 1}
    (row,) = read_links(root)
    assert row == {"goal": GOAL, "concept": "join", "page": JOIN, "status": "confirmed",
                   "score": "", "method": "manual", "date": "2026-02-01"}


def test_candidate_to_confirmed_to_rejected(tmp_path):
    root = make_root(tmp_path)
    goal.suggest(root, GOAL, k=1, date="2026-01-02")
    before = next(r for r in read_links(root) if r["concept"] == "join" and r["page"] == JOIN)
    assert before["status"] == "candidate"

    res = goal.set_status(root, GOAL, [("join", JOIN)], "confirmed", date="2026-02-01")
    assert res == {"goal": GOAL, "updated": 1, "added": 0}
    row = next(r for r in read_links(root) if r["concept"] == "join" and r["page"] == JOIN)
    assert row["status"] == "confirmed" and row["date"] == "2026-02-01"
    assert row["method"] == before["method"] and row["score"] == before["score"]

    goal.set_status(root, GOAL, [("join", JOIN)], "rejected", date="2026-03-05")
    rows = [r for r in read_links(root) if r["concept"] == "join" and r["page"] == JOIN]
    assert len(rows) == 1
    assert rows[0]["status"] == "rejected" and rows[0]["date"] == "2026-03-05"


def test_set_status_mixed_pairs_and_sorted_output(tmp_path):
    root = make_root(tmp_path)
    goal.set_status(root, GOAL, [("join", JOIN)], "confirmed", date="2026-02-01")
    res = goal.set_status(
        root, GOAL,
        [("subquery", SUBQUERY), ("join", JOIN), ("group-by", GROUP_BY)], "rejected", date="2026-02-02",
    )
    assert res == {"goal": GOAL, "updated": 1, "added": 2}
    rows = read_links(root)
    assert [r["concept"] for r in rows] == ["group-by", "join", "subquery"]
    assert {r["status"] for r in rows} == {"rejected"}
    assert {r["date"] for r in rows} == {"2026-02-02"}
    assert sorted(p.name for p in (root / "data").iterdir()) == ["goal_links.csv", "reviews.csv"]


def test_cli_confirm_and_reject_output(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = gcli(root, ["confirm", GOAL, f"join={JOIN}", f"subquery={SUBQUERY}",
                                 "--date", "2026-02-01"], capsys)
    assert code == 0, err
    res = json.loads(out)
    assert (res["goal"], res["updated"], res["added"]) == (GOAL, 0, 2)
    code, out, _ = gcli(root, ["reject", GOAL, f"join={JOIN}", "--date", "2026-02-03"], capsys)
    assert code == 0
    assert (json.loads(out)["updated"], json.loads(out)["added"]) == (1, 0)
    assert {r["concept"]: r["status"] for r in read_links(root)} == {"join": "rejected",
                                                                     "subquery": "confirmed"}


BAD_PAIRS = [
    pytest.param(("nope", JOIN), "nope", id="unknown-concept"),
    pytest.param(("join", "wiki/concepts/missing.md"), "wiki/concepts/missing.md", id="missing-page"),
    pytest.param(("join", "data/reviews.csv"), "data/reviews.csv", id="page-outside-wiki"),
    pytest.param(("join", "wiki/notes.txt"), "wiki/notes.txt", id="not-markdown"),
    pytest.param(("join", "wiki/concepts"), "wiki/concepts", id="directory"),
]


@pytest.mark.parametrize("seeded", [False, True], ids=["no-links-file", "existing-links-file"])
@pytest.mark.parametrize("pair,token", BAD_PAIRS)
def test_invalid_pair_writes_nothing(tmp_path, pair, token, seeded):
    root = make_root(tmp_path)
    (root / "wiki" / "notes.txt").write_text("text", encoding="utf-8")
    if seeded:
        goal.suggest(root, GOAL, k=1, date="2026-01-02")
    before = links_bytes(root)
    with pytest.raises(goal.GoalError) as info:
        goal.set_status(root, GOAL, [("subquery", SUBQUERY), pair], "confirmed", date="2026-02-01")
    assert token in str(info.value)
    assert links_bytes(root) == before


def test_cli_malformed_pair_exits_2_and_keeps_csv(tmp_path, capsys):
    root = make_root(tmp_path)
    goal.suggest(root, GOAL, k=1, date="2026-01-02")
    before = links_bytes(root)
    code, out, err = gcli(root, ["confirm", GOAL, f"subquery={SUBQUERY}", "join"], capsys)
    assert code == 2
    assert out == ""
    assert "join" in err
    assert links_bytes(root) == before


def test_cli_confirm_missing_page_exits_2_and_keeps_csv(tmp_path, capsys):
    root = make_root(tmp_path)
    goal.suggest(root, GOAL, k=1, date="2026-01-02")
    before = links_bytes(root)
    code, out, err = gcli(root, ["confirm", GOAL, f"join={JOIN}", "subquery=wiki/missing.md"], capsys)
    assert code == 2
    assert out == ""
    assert "wiki/missing.md" in err
    assert links_bytes(root) == before


@pytest.mark.parametrize("argv", [
    pytest.param(["suggest", GOAL, "--date", "2026-01-02"], id="suggest"),
    pytest.param(["confirm", GOAL, f"join={JOIN}"], id="confirm"),
    pytest.param(["reject", GOAL, f"join={JOIN}"], id="reject"),
    pytest.param(["coverage", GOAL], id="coverage"),
    pytest.param(["start", GOAL], id="start"),
    pytest.param(["overlap"], id="overlap"),
])
def test_bad_links_header_exits_2_and_leaves_file(tmp_path, capsys, argv):
    root = make_root(tmp_path)
    write_links(root, [], header=["goal", "concept", "page"])
    before = links_bytes(root)
    code, out, err = gcli(root, argv, capsys, environ={})
    assert code == 2
    assert out == ""
    assert "bad goal_links.csv header" in err
    assert links_bytes(root) == before


@pytest.mark.parametrize("cmd", ["coverage", "start", "overlap"])
def test_reviews_without_required_columns_exits_2(tmp_path, capsys, cmd):
    root = make_root(tmp_path)
    write_links(root, [link(GOAL, "join", JOIN)])
    write_reviews(root, [["2026-01-01", JOIN]], header=["date", "page"])
    before = digest_tree(root, "data", "wiki", "goals")
    argv = [cmd] if cmd == "overlap" else [cmd, GOAL]
    code, out, err = gcli(root, argv, capsys)
    assert code == 2
    assert out == ""
    assert "bad reviews.csv" in err
    assert digest_tree(root, "data", "wiki", "goals") == before


def _area(res, area_id):
    return next(a for a in res["areas"] if a["id"] == area_id)


def _concept(res, cid):
    for a in res["areas"]:
        for c in a["concepts"]:
            if c["id"] == cid:
                return c
    raise KeyError(cid)


def test_coverage_decision_table(tmp_path):
    root = make_root(tmp_path)
    concepts = [("c-none", "main"), ("c-note", "main"), ("c-l2", "main"), ("c-l3-again", "main"),
                ("c-l4-good", "main"), ("c-unk", "main"), ("c-l0", "main")]
    write_goal(root, "cells", goal_toml("cells", [("main", 1)], concepts, title="칸"))
    write_links(root, [
        link("cells", "c-none", GROUP_BY, status="candidate"),
        link("cells", "c-none", JOIN, status="rejected"),
        link("cells", "c-note", NORMALIZATION),
        link("cells", "c-l2", SUBQUERY),
        link("cells", "c-l3-again", JOIN),
        link("cells", "c-l4-good", GROUP_BY),
        link("cells", "c-unk", ENTITY),
        link("cells", "c-l0", TRANSACTION),
    ])
    write_reviews(root, [
        review("2026-01-10", JOIN, "again"),
        review("2026-01-11", GROUP_BY, "good"),
        review("2026-01-12", ENTITY, "good"),
    ])
    res = goal.coverage(root, "cells")
    assert (res["goal"], res["title"], res["kind"]) == ("cells", "칸", "official")
    (area,) = res["areas"]
    assert (area["id"], area["name"], area["weight"]) == ("main", "main", 1)
    assert [c["id"] for c in area["concepts"]] == [c[0] for c in concepts]
    expected = {
        "c-none": ("none", None, None, []),
        "c-note": ("note-only", None, None, [NORMALIZATION]),
        "c-l2": ("weak", 2, None, [SUBQUERY]),
        "c-l3-again": ("weak", 3, "again", [JOIN]),
        "c-l4-good": ("ok", 4, "good", [GROUP_BY]),
        "c-unk": ("unknown", None, "good", [ENTITY]),
        "c-l0": ("weak", 0, None, [TRANSACTION]),
    }
    for cid, (status, level, rating, pages) in expected.items():
        c = _concept(res, cid)
        assert c["status"] == status, cid
        assert c["level"] == level, cid
        assert c["last_rating"] == rating, cid
        assert c["pages"] == pages, cid
        assert c["name"] == cid
    assert area["counts"] == {"none": 1, "note-only": 1, "weak": 3, "ok": 1, "unknown": 1}
    assert res["weighted_ok"] == round(1 / 7, 4)


def test_coverage_two_pages_uses_max_level_and_latest_review_rules(tmp_path):
    root = make_root(tmp_path)
    concepts = [("c-pages", "m"), ("c-tail", "m"), ("c-date", "m")]
    write_goal(root, "variants", goal_toml("variants", [("m", 1)], concepts))
    write_links(root, [
        link("variants", "c-pages", WINDOW),
        link("variants", "c-pages", JOIN),
        link("variants", "c-tail", GROUP_BY),
        link("variants", "c-date", CLIMBING),
    ])
    write_reviews(root, [
        review("2026-03-02", GROUP_BY, "again"),
        review("2026-03-02", GROUP_BY, "good"),
        review("2026-03-02", CLIMBING, "good"),
        review("2026-03-02", CLIMBING, "again"),
        review("2026-03-01", CLIMBING, "easy"),
    ])
    res = goal.coverage(root, "variants")
    pages = _concept(res, "c-pages")
    assert pages["level"] == 3 and pages["status"] == "ok"
    assert set(pages["pages"]) == {WINDOW, JOIN}
    tail = _concept(res, "c-tail")
    assert tail["last_rating"] == "good" and tail["status"] == "ok"
    dated = _concept(res, "c-date")
    assert dated["last_rating"] == "again" and dated["status"] == "weak"


def test_coverage_without_reviews_file(tmp_path):
    root = make_root(tmp_path)
    (root / "data" / "reviews.csv").unlink()
    write_links(root, [link(GOAL, "join", JOIN), link(GOAL, "normalization", NORMALIZATION)])
    res = goal.coverage(root, GOAL)
    assert _concept(res, "join")["status"] == "ok"
    assert _concept(res, "join")["last_rating"] is None
    assert _concept(res, "normalization")["status"] == "note-only"


def test_coverage_weighted_ok_hand_calculation(tmp_path):
    root = make_root(tmp_path)
    concepts = [("a1", "a"), ("a2", "a"), ("b1", "b"), ("b2", "b"), ("b3", "b"), ("b4", "b")]
    write_goal(root, "w1", goal_toml("w1", [("a", 10), ("b", 40)], concepts))
    write_links(root, [link("w1", c, GROUP_BY) for c in ("a1", "b1", "b2", "b3")])
    res = goal.coverage(root, "w1")
    assert _area(res, "a")["counts"]["ok"] == 1 and _area(res, "a")["counts"]["none"] == 1
    assert _area(res, "b")["counts"]["ok"] == 3 and _area(res, "b")["counts"]["none"] == 1
    assert res["weighted_ok"] == 0.7


def test_coverage_weighted_ok_rounds_to_four_decimals(tmp_path):
    root = make_root(tmp_path)
    concepts = [("a1", "a"), ("a2", "a"), ("a3", "a"), ("b1", "b")]
    write_goal(root, "w2", goal_toml("w2", [("a", 1), ("b", 2)], concepts))
    write_links(root, [link("w2", "a1", GROUP_BY), link("w2", "b1", GROUP_BY)])
    assert goal.coverage(root, "w2")["weighted_ok"] == 0.7778


def test_cli_coverage_is_one_json_line(tmp_path, capsys):
    root = make_root(tmp_path)
    write_links(root, [link(GOAL, "join", JOIN)])
    code, out, err = gcli(root, ["coverage", GOAL], capsys)
    assert code == 0, err
    assert len(out.splitlines()) == 1 and out.endswith("\n")
    assert "SQL 기본 및 활용" in out and "\\u" not in out
    assert json.loads(out)["goal"] == GOAL


T_AREAS = [("a", 24), ("b", 8), ("d", 5), ("c", 2)]
T_CONCEPTS = [("a-root", "a"), ("a-child1", "a"), ("a-child2", "a"), ("a-grand", "a"),
              ("a-mid", "a"), ("a-leaf", "a"), ("b-root", "b"), ("b-leaf", "b"),
              ("d-note", "d"), ("c-solo", "c")]
T_PREREQS = [
    ("a-root", "a-child1", "syllabus-order"),
    ("a-root", "a-child2", "official"),
    ("a-root", "a-grand", "inferred"),
    ("a-child1", "a-grand", "user"),
    ("a-child2", "a-grand", "syllabus-order"),
    ("a-child2", "a-mid", "official"),
    ("a-mid", "a-leaf", "inferred"),
    ("b-root", "b-leaf", "user"),
]


def _project(items):
    return [{k: i[k] for k in ("id", "status", "score", "unlocks", "prereqs")} for i in items]


def _t_root(tmp_path):
    root = make_root(tmp_path)
    write_goal(root, "t-goal", goal_toml("t-goal", T_AREAS, T_CONCEPTS, T_PREREQS))
    return root


def test_start_orders_by_score_unlocks_then_id(tmp_path):
    root = _t_root(tmp_path)
    write_links(root, [link("t-goal", "a-root", GROUP_BY), link("t-goal", "d-note", NORMALIZATION)])
    res = goal.start(root, "t-goal", n=10)
    assert res["goal"] == "t-goal"
    assert _project(res["items"]) == [
        {"id": "d-note", "status": "note-only", "score": pytest.approx(4.5), "unlocks": 0, "prereqs": []},
        {"id": "a-child2", "status": "none", "score": pytest.approx(4.0), "unlocks": 3,
         "prereqs": [{"id": "a-root", "basis": "official"}]},
        {"id": "a-child1", "status": "none", "score": pytest.approx(4.0), "unlocks": 1,
         "prereqs": [{"id": "a-root", "basis": "syllabus-order"}]},
        {"id": "b-root", "status": "none", "score": pytest.approx(4.0), "unlocks": 1, "prereqs": []},
        {"id": "c-solo", "status": "none", "score": pytest.approx(2.0), "unlocks": 0, "prereqs": []},
    ]
    assert [i["name"] for i in res["items"]][:2] == ["d-note", "a-child2"]
    assert res["blocked"] == 4


def test_start_n_limits_items_but_not_blocked(tmp_path):
    root = _t_root(tmp_path)
    write_links(root, [link("t-goal", "a-root", GROUP_BY), link("t-goal", "d-note", NORMALIZATION)])
    res = goal.start(root, "t-goal", n=3)
    assert [i["id"] for i in res["items"]] == ["d-note", "a-child2", "a-child1"]
    assert res["blocked"] == 4


def test_start_default_n_is_five(tmp_path):
    root = make_root(tmp_path)
    write_goal(root, "many", goal_toml("many", [("m", 6)], [(f"k{i}", "m") for i in range(1, 8)]))
    res = goal.start(root, "many")
    assert [i["id"] for i in res["items"]] == ["k1", "k2", "k3", "k4", "k5"]
    assert res["blocked"] == 0


def test_start_deficiency_levels_by_status(tmp_path):
    root = make_root(tmp_path)
    concepts = [("x-none", "x"), ("x-note", "x"), ("x-unk", "x"), ("x-weak", "x"), ("y-ok", "y")]
    write_goal(root, "defs", goal_toml("defs", [("x", 40), ("y", 10)], concepts))
    write_links(root, [
        link("defs", "x-note", NORMALIZATION),
        link("defs", "x-unk", ENTITY),
        link("defs", "x-weak", TRANSACTION),
        link("defs", "y-ok", GROUP_BY),
    ])
    write_reviews(root, [review("2026-01-12", ENTITY, "good")])
    res = goal.start(root, "defs", n=10)
    assert [(i["id"], i["status"], i["score"]) for i in res["items"]] == [
        ("x-none", "none", pytest.approx(10.0)),
        ("x-note", "note-only", pytest.approx(9.0)),
        ("x-unk", "unknown", pytest.approx(7.0)),
        ("x-weak", "weak", pytest.approx(6.0)),
    ]
    assert res["blocked"] == 0


def test_start_empty_wiki_only_roots_are_candidates(tmp_path):
    root = _t_root(tmp_path)
    shutil.rmtree(root / "wiki")
    (root / "wiki").mkdir()
    res = goal.start(root, "t-goal", n=10)
    assert _project(res["items"]) == [
        {"id": "d-note", "status": "none", "score": pytest.approx(5.0), "unlocks": 0, "prereqs": []},
        {"id": "a-root", "status": "none", "score": pytest.approx(4.0), "unlocks": 5, "prereqs": []},
        {"id": "b-root", "status": "none", "score": pytest.approx(4.0), "unlocks": 1, "prereqs": []},
        {"id": "c-solo", "status": "none", "score": pytest.approx(2.0), "unlocks": 0, "prereqs": []},
    ]
    assert res["blocked"] == 6


def test_cli_start_n_flag(tmp_path, capsys):
    root = _t_root(tmp_path)
    code, out, err = gcli(root, ["start", "t-goal", "--n", "2"], capsys)
    assert code == 0, err
    res = json.loads(out)
    assert [i["id"] for i in res["items"]] == ["d-note", "a-root"]


def _overlap_root(tmp_path):
    root = make_root(tmp_path)
    add_extra_goal(root, "extra")
    add_extra_goal(root, "broken")
    write_links(root, [
        link(GOAL, "join", JOIN),
        link(GOAL, "group-by", GROUP_BY),
        link(GOAL, "normalization", NORMALIZATION, status="candidate", method="keyword", score="0.5"),
        link(GOAL, "subquery", SUBQUERY, status="candidate", method="keyword", score="0.5"),
        link(GOAL, "subquery", JOIN, status="candidate", method="keyword", score="0.3"),
        link(GOAL, "subquery", WINDOW, status="rejected"),
        link("alpha-subj", "wf", WINDOW),
        link("alpha-subj", "tx", TRANSACTION),
        link("alpha-subj", "wf", JOIN, status="candidate", method="keyword", score="0.2"),
    ])
    return root


def test_overlap_goals_errors_and_unlinked_pages(tmp_path):
    root = _overlap_root(tmp_path)
    res = goal.overlap(root)
    assert [g["goal"] for g in res["goals"]] == [GOAL, "alpha-subj"]
    sqld, subj = res["goals"]
    assert (sqld["title"], sqld["kind"], sqld["concepts"]) == ("SQLD 픽스처", "official", 5)
    assert sqld["counts"] == {"none": 3, "note-only": 0, "weak": 0, "ok": 2, "unknown": 0}
    assert sqld["weighted_ok"] == pytest.approx(0.4)
    assert sqld["candidate_concepts"] == 2
    assert (subj["title"], subj["kind"], subj["concepts"]) == ("내 DB 공부 목표", "subjective", 2)
    assert subj["counts"] == {"none": 0, "note-only": 0, "weak": 2, "ok": 0, "unknown": 0}
    assert subj["weighted_ok"] == pytest.approx(0.0)
    assert subj["candidate_concepts"] == 1

    (err,) = res["errors"]
    assert "zz-broken" in err["file"]
    assert isinstance(err["error"], str) and err["error"]

    assert res["unlinked_pages"] == sorted([ENTITY, NORMALIZATION, SUBQUERY])
    assert CLIMBING not in res["unlinked_pages"]


def test_overlap_sorts_by_weighted_ok_then_goal_id(tmp_path):
    root = make_root(tmp_path)
    (root / "goals" / f"{GOAL}.toml").unlink()
    for gid in ("bb", "aa", "cc"):
        write_goal(root, gid, goal_toml(gid, [("m", 1)], [("x", "m"), ("y", "m")]))
    write_links(root, [link("cc", "x", GROUP_BY), link("cc", "y", JOIN)])
    res = goal.overlap(root)
    assert [g["goal"] for g in res["goals"]] == ["cc", "aa", "bb"]
    assert [g["weighted_ok"] for g in res["goals"]] == [1.0, 0.0, 0.0]
    assert res["errors"] == []


def test_overlap_without_goals_lists_all_concept_pages(tmp_path):
    root = make_root(tmp_path)
    (root / "goals" / f"{GOAL}.toml").unlink()
    res = goal.overlap(root)
    assert res["goals"] == [] and res["errors"] == []
    assert res["unlinked_pages"] == CONCEPT_PAGES


def test_subjective_goal_has_same_output_shape_as_official(tmp_path, capsys):
    root = _overlap_root(tmp_path)
    off_cov, sub_cov = goal.coverage(root, GOAL), goal.coverage(root, "alpha-subj")
    assert set(off_cov) == set(sub_cov)
    assert set(off_cov["areas"][0]) == set(sub_cov["areas"][0])
    assert set(off_cov["areas"][0]["concepts"][0]) == set(sub_cov["areas"][0]["concepts"][0])
    assert sub_cov["kind"] == "subjective"
    off_start, sub_start = goal.start(root, GOAL), goal.start(root, "alpha-subj")
    assert set(off_start) == set(sub_start)
    for cmd in (["coverage", "alpha-subj"], ["start", "alpha-subj"], ["overlap"]):
        code, out, err = gcli(root, cmd, capsys)
        assert code == 0, err
        assert len(out.splitlines()) == 1


@pytest.mark.parametrize("argv", [
    pytest.param(["coverage", "nope"], id="coverage"),
    pytest.param(["start", "nope"], id="start"),
    pytest.param(["suggest", "nope"], id="suggest"),
    pytest.param(["confirm", "nope", f"join={JOIN}"], id="confirm"),
])
def test_unknown_goal_exits_2(tmp_path, capsys, argv):
    root = make_root(tmp_path)
    before = all_files(root)
    code, out, err = gcli(root, argv, capsys, environ={})
    assert code == 2
    assert out == ""
    assert "goal not found: nope" in err
    assert all_files(root) == before


def test_invalid_goal_file_exits_2_without_writes(tmp_path, capsys):
    root = make_root(tmp_path)
    write_goal(root, "bad", BASE.replace('id = "g1"', 'id = "bad"').replace('kind = "official"', 'kind = "x"'))
    before = all_files(root)
    code, out, err = gcli(root, ["coverage", "bad"], capsys)
    assert code == 2 and out == "" and "kind" in err
    assert all_files(root) == before


def test_goal_cli_argument_error_exits_2(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = gcli(root, ["confirm", GOAL], capsys)
    assert code == 2
    assert out == ""
    assert err.strip()


def test_full_command_sequence_leaves_wiki_and_reviews_untouched(tmp_path, capsys):
    root = make_root(tmp_path)
    before = digest_tree(root, "wiki", "data/reviews.csv")
    assert len(before) == 11
    seq = [
        (index, ["build"]),
        (index, ["embed"]),
        (index, ["search", "조인"]),
        (goal, ["suggest", GOAL, "--date", "2026-01-02"]),
        (goal, ["confirm", GOAL, f"join={JOIN}", "--date", "2026-01-03"]),
        (goal, ["coverage", GOAL]),
        (goal, ["start", GOAL]),
        (goal, ["overlap"]),
    ]
    for module, argv in seq:
        code, out, err = run_cli(module, ["--root", root, *argv], capsys,
                                 embedder=fixture_embedder(), environ={})
        assert code == 0, (argv, err)
        json.loads(out)
    assert digest_tree(root, "wiki", "data/reviews.csv") == before
    assert read_links(root)


def test_check_reports_areas_concepts_and_prereq_count(tmp_path, capsys):
    root = make_root(tmp_path)
    write_goal(root, "g1", BASE)
    code, out, err = gcli(root, ["check", "g1"], capsys)
    assert code == 0, err
    assert len(out.splitlines()) == 1
    assert json.loads(out) == {
        "goal": "g1",
        "title": "기본 목표",
        "kind": "official",
        "areas": [
            {"id": "a1", "name": "영역1", "weight": 1,
             "concepts": [{"id": "c1", "name": "개념1"}, {"id": "c2", "name": "개념2"}]},
            {"id": "a2", "name": "영역2", "weight": 2, "concepts": [{"id": "c3", "name": "개념3"}]},
        ],
        "prereqs": 1,
    }


def test_check_invalid_goal_exits_2_without_writes(tmp_path, capsys):
    root = make_root(tmp_path)
    add_extra_goal(root, "broken")
    before = all_files(root)
    code, out, err = gcli(root, ["check", "zz-broken"], capsys)
    assert code == 2 and out == "" and "cycle" in err
    assert all_files(root) == before


def test_list_goals_and_errors_in_file_order(tmp_path, capsys):
    root = make_root(tmp_path)
    add_extra_goal(root, "extra")
    add_extra_goal(root, "broken")
    before = all_files(root)
    code, out, err = gcli(root, ["list"], capsys)
    assert code == 0, err
    res = json.loads(out)
    assert res["goals"] == [
        {"goal": "alpha-subj", "title": "내 DB 공부 목표", "kind": "subjective", "areas": ["핵심"], "concepts": 2},
        {"goal": GOAL, "title": "SQLD 픽스처", "kind": "official",
         "areas": ["데이터 모델링의 이해", "SQL 기본 및 활용"], "concepts": 5},
    ]
    (e,) = res["errors"]
    assert e["file"] == "zz-broken.toml" and "cycle" in e["error"]
    assert all_files(root) == before


def test_list_without_goals_dir(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    assert goal.list_goals(root) == {"goals": [], "errors": []}


def test_suggest_ignores_non_concept_pages(tmp_path):
    root = make_root(tmp_path)
    write_page(root, "wiki/life/insights/조인 정규화 메모.md", "조인 정규화 메모", "조인 정규화 조인 정규화",
               type="insight", status="active")
    res = goal.suggest(root, GOAL, k=5, date="2026-01-02")
    pages = {cand["page"] for c in res["concepts"] for cand in c["candidates"]}
    assert pages and all("/insights/" not in p and "/hobby/" not in p for p in pages)


def test_cli_root_from_env(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, _ = run_cli(goal, ["check", GOAL], capsys, environ={"LLM_WIKI_ROOT": str(root)}, cwd=tmp_path)
    assert code == 0
    assert json.loads(out)["goal"] == GOAL
