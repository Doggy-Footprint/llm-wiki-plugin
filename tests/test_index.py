import datetime
import hashlib
import json
import math
import plistlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "wiki-goal"))

import index  # noqa: E402
from goal_poc_support import (  # noqa: E402
    CLIMBING, FIXTURE_PAGES, JOIN, SUBQUERY, NORMALIZATION, WINDOW,
    FakeOpenAI, MapEmbedder, cosine, digest_tree, fixture_embedder, http_error, make_root,
    read_jsonl, run_cli, unpack, vector_rows, write_page,
)

SECRET = "sk-test-SECRET123"


def paths(result):
    return [r["path"] for r in result["results"]]


@pytest.mark.parametrize("text,expected", [
    pytest.param("", [], id="empty"),
    pytest.param("가", ["가"], id="hangul-1"),
    pytest.param("가나", ["가나"], id="hangul-2"),
    pytest.param("가나다", ["가나", "나다"], id="hangul-3"),
    pytest.param("가나다라", ["가나", "나다", "다라"], id="hangul-4"),
    pytest.param("가가가", ["가가", "가가"], id="hangul-duplicates-kept"),
    pytest.param("ab", ["ab"], id="ascii-2"),
    pytest.param("a_1 b2", ["a_1", "b2"], id="digits-underscore"),
    pytest.param("_x_", ["_x_"], id="underscore-only-edges"),
    pytest.param("!!", [], id="symbols-only"),
    pytest.param("  \t\n", [], id="whitespace-only"),
    pytest.param("SELECT", ["select"], id="uppercase"),
    pytest.param("join조인", ["join", "조인"], id="mixed-adjacent"),
    pytest.param("조인-조인", ["조인", "조인"], id="hyphen-splits-words"),
    pytest.param("2024년", ["2024", "년"], id="digits-then-hangul"),
    pytest.param("가나 ab 다라", ["가나", "ab", "다라"], id="order-preserved"),
    pytest.param("ＳＥＬＥＣＴ１", ["select1"], id="fullwidth-nfkc"),
    pytest.param("조인을 쓰는 SELECT문", ["조인", "인을", "쓰는", "select", "문"], id="spec-example"),
])
def test_tokenize(text, expected):
    assert index.tokenize(text) == expected


def _write_raw(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _by_path(pages):
    return {p["path"]: p for p in pages}


def test_load_pages_fields_and_exclusions(tmp_path):
    root = tmp_path
    _write_raw(root, "wiki/index.md", "# 색인\n")
    _write_raw(root, "wiki/log.md", "# 로그\n")
    _write_raw(root, "wiki/a-titled.md",
               "---\ntype: concept\nlevel: 0\ntags: [x, y]\naliases: [별칭1, 별칭2]\n---\n"
               "#해시태그 아님\n## 섹션\n# 진짜제목\n본문 내용\n# 두번째 제목\n")
    _write_raw(root, "wiki/b-notitle.md",
               "---\ntype: concept\nlevel: 4\naliases: 단일별칭\n---\n## 요약\n제목 줄이 없다\n")
    _write_raw(root, "wiki/sub/dir/c.md", "---\ntags: 하나\nlevel: 5\n---\n# 깊은 페이지\n")
    _write_raw(root, "wiki/d-nofront.md", "# 프런트매터 없음\n내용\n")

    pages, warnings = index.load_pages(root)
    assert warnings == []
    assert [p["path"] for p in pages] == [
        "wiki/a-titled.md", "wiki/b-notitle.md", "wiki/d-nofront.md", "wiki/sub/dir/c.md",
    ]
    by = _by_path(pages)
    for p in pages:
        assert {"path", "title", "aliases", "tags", "type", "level", "body", "text", "text_hash"} <= set(p)

    a = by["wiki/a-titled.md"]
    assert a["title"] == "진짜제목"
    assert a["aliases"] == ["별칭1", "별칭2"]
    assert a["tags"] == ["x", "y"]
    assert a["type"] == "concept"
    assert a["level"] == 0 and isinstance(a["level"], int)
    assert "본문 내용" in a["body"]
    assert "type: concept" not in a["body"] and "aliases:" not in a["body"]

    b = by["wiki/b-notitle.md"]
    assert b["title"] == "b-notitle"
    assert b["aliases"] == ["단일별칭"]
    assert b["tags"] == []
    assert b["level"] == 4

    c = by["wiki/sub/dir/c.md"]
    assert c["tags"] == ["하나"]
    assert c["aliases"] == []
    assert c["type"] == ""
    assert c["level"] is None
    assert c["title"] == "깊은 페이지"

    d = by["wiki/d-nofront.md"]
    assert d["title"] == "프런트매터 없음"
    assert d["type"] == "" and d["level"] is None and d["tags"] == [] and d["aliases"] == []
    assert "내용" in d["body"]


@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4),
    ("5", None), ("-1", None), ("abc", None), ("", None),
])
def test_load_pages_level_values(tmp_path, raw, expected):
    _write_raw(tmp_path, "wiki/p.md", f"---\ntype: concept\nlevel: {raw}\n---\n# P\n")
    (page,), _ = index.load_pages(tmp_path)
    assert page["level"] == expected
    if expected is not None:
        assert isinstance(page["level"], int)


def test_load_pages_missing_level_key(tmp_path):
    _write_raw(tmp_path, "wiki/p.md", "---\ntype: concept\n---\n# P\n")
    (page,), _ = index.load_pages(tmp_path)
    assert page["level"] is None


def test_load_pages_text_is_title_aliases_tags_body(tmp_path):
    _write_raw(tmp_path, "wiki/p.md",
               "---\ntype: concept\ntags: [t1, t2]\naliases: [a1, a2]\n---\n# 제목P\n본문 한 줄\n")
    (page,), _ = index.load_pages(tmp_path)
    expected = "제목P" + "\n" + "a1, a2" + "\n" + "t1, t2" + "\n" + page["body"]
    assert page["text"] == expected
    assert page["text_hash"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert "본문 한 줄" in page["body"]


def test_load_pages_text_truncated_to_8000_chars(tmp_path):
    _write_raw(tmp_path, "wiki/long.md", "---\ntype: concept\n---\n# 긴 글\n" + "가나다라" * 3000 + "\n")
    (page,), _ = index.load_pages(tmp_path)
    full = "긴 글" + "\n" + "" + "\n" + "" + "\n" + page["body"]
    assert len(full) > 8000
    assert len(page["text"]) == 8000
    assert page["text"] == full[:8000]
    assert page["text_hash"] == hashlib.sha256(page["text"].encode("utf-8")).hexdigest()


def test_load_pages_skips_non_utf8_with_warning(tmp_path):
    _write_raw(tmp_path, "wiki/ok.md", "# 정상\n")
    bad = tmp_path / "wiki" / "bad.md"
    bad.write_bytes(b"---\ntype: concept\n---\n# \xff\xfe broken\n")
    pages, warnings = index.load_pages(tmp_path)
    assert [p["path"] for p in pages] == ["wiki/ok.md"]
    assert warnings == ["wiki/bad.md: not utf-8"]


def test_build_survives_non_utf8_page(tmp_path):
    root = make_root(tmp_path)
    (root / "wiki" / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    result = index.build(root)
    assert result["pages"] == len(FIXTURE_PAGES)
    assert result["warnings"] == ["wiki/bad.md: not utf-8"]


def test_build_fixture_counts_pages_without_index_and_log(tmp_path):
    root = make_root(tmp_path)
    result = index.build(root)
    assert result == {"pages": len(FIXTURE_PAGES), "warnings": []}
    assert (root / ".cache" / "wiki-index.sqlite").exists()


def test_build_rebuilds_from_scratch(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    (root / "wiki" / "hobby" / "climbing.md").unlink()
    assert index.build(root)["pages"] == len(FIXTURE_PAGES) - 1
    assert CLIMBING not in paths(index.search(root, "클라이밍"))


def test_build_keeps_vector_table(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    before = vector_rows(root)
    assert len(before) == len(FIXTURE_PAGES)
    index.build(root)
    assert vector_rows(root) == before


def test_search_two_char_query_finds_title_page_first(tmp_path):
    root = make_root(tmp_path)
    result = index.search(root, "조인")
    assert result["mode"] == "keyword"
    assert result["results"][0]["path"] == JOIN
    assert result["results"][0]["title"] == "조인"


def test_search_keyword_only_fields(tmp_path):
    root = make_root(tmp_path)
    result = index.search(root, "조인")
    for i, r in enumerate(result["results"], start=1):
        assert r["keyword_rank"] == i
        assert r["vector_rank"] is None
        assert r["score"] == round(1 / (60 + i), 6)
    assert isinstance(result["warnings"], list)


def test_search_or_semantics_over_tokens(tmp_path):
    root = make_root(tmp_path)
    found = paths(index.search(root, "서브쿼리 정규화", k=20))
    assert SUBQUERY in found and NORMALIZATION in found


@pytest.mark.parametrize("case", ["title-vs-body", "aliases-vs-body", "tags-vs-body"])
def test_field_weight_beats_body(tmp_path, case):
    term = "정규화"
    # the winner sorts after the loser by path, so path order cannot explain the result
    if case == "title-vs-body":
        write_page(tmp_path, "wiki/a-body.md", "기타문서", "여기에 정규화 한 번 언급한다", type="concept")
        write_page(tmp_path, "wiki/z-win.md", term, "여기에 다른 설명을 적는다 문장", type="concept")
    elif case == "aliases-vs-body":
        write_page(tmp_path, "wiki/a-body.md", "기타문서", "여기에 정규화 한 번 언급한다", type="concept")
        write_page(tmp_path, "wiki/z-win.md", "문서둘", "여기에 다른 설명을 적는다 문장",
                   type="concept", aliases=f"[{term}]")
    else:
        write_page(tmp_path, "wiki/a-body.md", "기타문서", "여기에 정규화 한 번 언급한다", type="concept")
        write_page(tmp_path, "wiki/z-win.md", "문서둘", "여기에 다른 설명을 적는다 문장",
                   type="concept", tags=f"[{term}]")
    result = index.search(tmp_path, term)
    assert paths(result)[:2] == ["wiki/z-win.md", "wiki/a-body.md"]
    assert [r["keyword_rank"] for r in result["results"][:2]] == [1, 2]


def _bm25_order(docs, term, weights, k1=1.2, b=0.75):
    cols = ("title", "aliases", "tags", "body")
    n_docs = len(docs)
    n_hit = sum(1 for d in docs.values() if any(term in d[c] for c in cols))
    idf = math.log((n_docs - n_hit + 0.5) / (n_hit + 0.5))
    if idf <= 0:
        idf = 1e-6
    avg = {c: sum(len(d[c]) for d in docs.values()) / n_docs for c in cols}
    scores = {}
    for path, d in docs.items():
        total = 0.0
        for c, w in zip(cols, weights):
            tf = d[c].count(term)
            if tf:
                total += w * idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d[c]) / avg[c]))
        if total:
            scores[path] = -total
    return [p for p, _ in sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))]


def _write_token_page(root, name, title, aliases, body):
    front = "---\ntype: concept\n"
    if aliases:
        front += "aliases: [" + ", ".join(aliases) + "]\n"
    path = Path(root) / "wiki" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(front + "---\n" + " ".join(body) + "\n", encoding="utf-8")
    return f"wiki/{name}.md"


def _weights_case(root, a_title, a_aliases, a_body, b_body):
    docs = {}
    empty = []
    pa = _write_token_page(root, "-".join(a_title), a_title, a_aliases, a_body)
    docs[pa] = {"title": a_title, "aliases": a_aliases, "tags": empty, "body": a_body}
    pb = _write_token_page(root, "a-body", ["a", "body"], [], b_body)
    docs[pb] = {"title": ["a", "body"], "aliases": empty, "tags": empty, "body": b_body}
    for i in range(10):
        title = [f"f{i:02d}", f"g{i:02d}"]
        body = [f"w{i}x{j}" for j in range(10)]
        path = _write_token_page(root, "-".join(title), title, [], body)
        docs[path] = {"title": title, "aliases": empty, "tags": empty, "body": body}
    return pa, pb, docs


@pytest.mark.parametrize("case", ["title-vs-body", "aliases-vs-body"])
def test_column_weights_decide_order(tmp_path, case):
    # A: term once in a long title (or alias list); B: term in a short body. Equal weights rank B first;
    # only the specified (10, 8, 4, 1) weights put A first.
    # N=12, n=2 so IDF=ln(10.5/2.5)>0. Title case: f(A title)=2.2/(1+1.2*(.25+.75*20/3.5))=0.3414,
    # f(B body, tf=3, len 10, avg 10)=6.6/4.2=1.5714. Alias case: avg alias length makes A's ratio 12,
    # f(A)=2.2/12.1=0.1818, f(B, tf=1)=1.0; weighted 8*0.1818=1.4545 > 1.0.
    a_body = [f"u{j}" for j in range(10)]
    if case == "title-vs-body":
        a_title = ["zt", "kwq"] + [f"ta{j:02d}" for j in range(18)]
        pa, pb, docs = _weights_case(tmp_path, a_title, [], a_body, ["kwq"] * 3 + [f"v{j}" for j in range(7)])
    else:
        pa, pb, docs = _weights_case(tmp_path, ["z", "alias"], ["kwq", "al1", "al2", "al3", "al4"], a_body,
                                     ["kwq"] + [f"v{j}" for j in range(9)])
    assert pa > pb
    assert _bm25_order(docs, "kwq", (1, 1, 1, 1)) == [pb, pa]
    assert _bm25_order(docs, "kwq", (10, 8, 4, 1)) == [pa, pb]
    result = index.search(tmp_path, "kwq")
    assert paths(result) == [pa, pb]
    assert [r["keyword_rank"] for r in result["results"]] == [1, 2]


def test_equal_scores_ordered_by_path(tmp_path):
    for name in ("m", "a", "z"):
        write_page(tmp_path, f"wiki/{name}.md", "동일", "같은 본문 조인 내용", type="concept")
    result = index.search(tmp_path, "조인")
    assert paths(result) == ["wiki/a.md", "wiki/m.md", "wiki/z.md"]
    assert [r["keyword_rank"] for r in result["results"]] == [1, 2, 3]


def test_query_without_tokens_gives_empty_keyword_results(tmp_path):
    root = make_root(tmp_path)
    result = index.search(root, "!!")
    assert result["results"] == []
    assert result["mode"] == "keyword"


def test_keyword_list_capped_at_50(tmp_path):
    for i in range(55):
        write_page(tmp_path, f"wiki/p{i:02d}.md", "동일", "공통어휘 같은 본문", type="concept")
    result = index.search(tmp_path, "공통어휘", k=100)
    expected = [f"wiki/p{i:02d}.md" for i in range(50)]
    assert paths(result) == expected
    assert [r["keyword_rank"] for r in result["results"]] == list(range(1, 51))


def test_search_k_limits_results(tmp_path):
    root = make_root(tmp_path)
    full = paths(index.search(root, "조인 sql", k=20))
    assert len(full) > 3
    assert paths(index.search(root, "조인 sql", k=3)) == full[:3]


def test_search_refreshes_keyword_index_every_time(tmp_path):
    root = make_root(tmp_path)
    assert index.search(root, "새로운개념어")["results"] == []
    write_page(root, "wiki/concepts/new.md", "새로운개념어", "내용", type="concept")
    assert paths(index.search(root, "새로운개념어")) == ["wiki/concepts/new.md"]
    (root / "wiki" / "concepts" / "new.md").unlink()
    assert index.search(root, "새로운개념어")["results"] == []


def test_search_empty_query_raises(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(index.IndexToolError, match="empty query"):
        index.search(root, "   ")


def _texts_by_path(root):
    pages, _ = index.load_pages(root)
    return {p["path"]: p["text"] for p in pages}


def test_embed_state_transitions(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    n = len(FIXTURE_PAGES)

    emb = fixture_embedder()
    first = index.embed(root, emb)
    assert first["embedded"] == n and first["unchanged"] == 0 and first["removed"] == 0
    assert first["skipped"] is None
    assert first["model"] == "fake-a" and first["dim"] == 4
    assert sorted(emb.all_texts) == sorted(_texts_by_path(root).values())
    rows = vector_rows(root)
    assert [r[0] for r in rows] == FIXTURE_PAGES
    pages, _ = index.load_pages(root)
    hashes = {p["path"]: p["text_hash"] for p in pages}
    for path, model, dim, text_hash, vec in rows:
        assert model == "fake-a" and dim == 4 and text_hash == hashes[path]
        assert len(unpack(vec, dim)) == 4

    emb2 = fixture_embedder()
    second = index.embed(root, emb2)
    assert second["embedded"] == 0 and second["unchanged"] == n and second["removed"] == 0
    assert emb2.calls == []

    join = root / JOIN
    join.write_text(join.read_text(encoding="utf-8") + "\n## 추가\n새 문장 UNIQUEMARK.\n", encoding="utf-8")
    emb3 = fixture_embedder()
    third = index.embed(root, emb3)
    assert third["embedded"] == 1 and third["unchanged"] == n - 1 and third["removed"] == 0
    assert len(emb3.all_texts) == 1
    assert "UNIQUEMARK" in emb3.all_texts[0]
    assert emb3.all_texts[0] == _texts_by_path(root)[JOIN]

    (root / CLIMBING).unlink()
    emb4 = fixture_embedder()
    fourth = index.embed(root, emb4)
    assert fourth["removed"] == 1 and fourth["embedded"] == 0 and fourth["unchanged"] == n - 1
    assert CLIMBING not in [r[0] for r in vector_rows(root)]
    assert len(vector_rows(root)) == n - 1

    emb5 = fixture_embedder(model="fake-b")
    fifth = index.embed(root, emb5)
    assert fifth["embedded"] == n - 1 and fifth["unchanged"] == 0
    assert fifth["removed"] == n - 1
    assert fifth["model"] == "fake-b"
    rows = vector_rows(root)
    assert len(rows) == n - 1 and {r[1] for r in rows} == {"fake-b"}


def test_embed_dim_change_reembeds_all(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, MapEmbedder(model="fake-a", dim=4))
    emb = MapEmbedder(model="fake-a", dim=5)
    result = index.embed(root, emb)
    assert result["embedded"] == len(FIXTURE_PAGES) and result["unchanged"] == 0
    assert result["removed"] == len(FIXTURE_PAGES)
    rows = vector_rows(root)
    assert len(rows) == len(FIXTURE_PAGES)
    assert {(r[1], r[2]) for r in rows} == {("fake-a", 5)}
    assert all(len(unpack(r[4], 5)) == 5 for r in rows)


def test_search_ignores_vectors_of_other_model(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder(model="fake-a"))
    result = index.search(root, "조인", embedder=fixture_embedder(model="fake-b"))
    assert result["stale_vectors"] == len(FIXTURE_PAGES)
    assert all(r["vector_rank"] is None for r in result["results"])


def test_embed_batches_of_64(tmp_path):
    root = make_root(tmp_path)
    for i in range(70):
        write_page(root, f"wiki/gen/g{i:02d}.md", f"생성{i:02d}", f"본문 {i}", type="concept")
    emb = MapEmbedder()
    result = index.embed(root, emb)
    total = len(FIXTURE_PAGES) + 70
    assert result["embedded"] == total
    assert [len(c) for c in emb.calls] == [64, total - 64]
    assert len(vector_rows(root)) == total


def test_embed_stores_float32_little_endian(tmp_path):
    root = make_root(tmp_path)
    index.embed(root, fixture_embedder())
    rows = {r[0]: r for r in vector_rows(root)}
    assert unpack(rows[JOIN][4], 4) == [1.0, 0.0, 0.0, 0.0]
    got = unpack(rows[SUBQUERY][4], 4)
    assert got == pytest.approx([0.8, 0.6, 0.0, 0.0], abs=1e-6)


@pytest.mark.parametrize("free,expect_skipped", [
    pytest.param(999.0, "memory", id="free-999-skips"),
    pytest.param(1000.0, None, id="free-1000-proceeds"),
    pytest.param(None, None, id="free-unknown-proceeds"),
])
def test_embed_memory_gate(tmp_path, free, expect_skipped):
    root = make_root(tmp_path)
    index.build(root)
    before = vector_rows(root)
    emb = fixture_embedder()
    result = index.embed(root, emb, min_free_mb=1000, free_mb=lambda: free)
    assert result["skipped"] == expect_skipped
    assert result["free_mb"] == free
    if expect_skipped:
        assert emb.calls == []
        assert vector_rows(root) == before == []
    else:
        assert result["embedded"] == len(FIXTURE_PAGES)
        assert len(vector_rows(root)) == len(FIXTURE_PAGES)


def test_embed_memory_skip_leaves_existing_vectors(tmp_path):
    root = make_root(tmp_path)
    index.embed(root, fixture_embedder())
    (root / CLIMBING).unlink()
    before = vector_rows(root)
    result = index.embed(root, fixture_embedder(), min_free_mb=1000, free_mb=lambda: 10.0)
    assert result["skipped"] == "memory"
    assert vector_rows(root) == before


def test_embed_zero_threshold_never_asks_free_memory(tmp_path):
    root = make_root(tmp_path)

    def boom():
        raise AssertionError("free_mb must not be called when min_free_mb is 0")

    result = index.embed(root, fixture_embedder(), min_free_mb=0, free_mb=boom)
    assert result["skipped"] is None
    assert result["embedded"] == len(FIXTURE_PAGES)


QUERY = "조인"


def _expected_vector_ranks(root, query_vec):
    pages, _ = index.load_pages(root)
    emb = fixture_embedder()
    scored = [(-cosine(query_vec, emb.vec_for(p["text"])), p["path"]) for p in pages]
    return {path: i for i, (_, path) in enumerate(sorted(scored), start=1)}


def test_hybrid_rrf_scores(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    result = index.search(root, QUERY, k=20, embedder=fixture_embedder())
    assert result["mode"] == "hybrid"
    assert result["stale_vectors"] == 0

    expected_vr = _expected_vector_ranks(root, [1, 0, 0, 0])
    assert expected_vr[JOIN] == 1 and expected_vr[SUBQUERY] == 2
    by = {r["path"]: r for r in result["results"]}
    assert set(by) == set(FIXTURE_PAGES)
    assert by[JOIN]["vector_rank"] == 1 and by[JOIN]["keyword_rank"] == 1
    assert by[JOIN]["score"] == round(1 / 61 + 1 / 61, 6)
    for path, r in by.items():
        assert r["vector_rank"] == expected_vr[path]
        score = 0.0
        if r["keyword_rank"] is not None:
            score += 1 / (60 + r["keyword_rank"])
        score += 1 / (60 + r["vector_rank"])
        assert r["score"] == round(score, 6)
    ordered = [(-r["score"], r["path"]) for r in result["results"]]
    assert ordered == sorted(ordered)
    assert result["results"][0]["path"] == JOIN

    top3 = index.search(root, QUERY, k=3, embedder=fixture_embedder())
    assert paths(top3) == paths(result)[:3]


def test_hybrid_vector_only_results(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    result = index.search(root, "zzqvec", k=5, embedder=fixture_embedder())
    assert result["mode"] == "hybrid"
    assert len(result["results"]) == 5
    expected_vr = _expected_vector_ranks(root, [1, 0, 0, 0])
    for i, r in enumerate(result["results"], start=1):
        assert r["keyword_rank"] is None
        assert r["vector_rank"] == i
        assert r["score"] == round(1 / (60 + i), 6)
        assert expected_vr[r["path"]] == i
    assert result["results"][0]["path"] == JOIN


def test_vector_list_capped_at_50(tmp_path):
    n = 60
    for i in range(n):
        body = "zzqvec 키워드 적중" if i == 9 else f"일반 본문 {i}"
        write_page(tmp_path, f"wiki/gen/p{i:02d}.md", f"문서{i:02d}", body, type="concept")
    # page i has cosine rank n - i with the query vector [1, 0, 0, 0]; path order is the reverse
    prefixes = {f"문서{i:02d}": [1.0, 0.1 * (n - 1 - i), 0.0, 0.0] for i in range(n)}
    make = lambda **kw: MapEmbedder(exact={"zzqvec": [1.0, 0.0, 0.0, 0.0]}, prefixes=prefixes, **kw)
    index.build(tmp_path)
    index.embed(tmp_path, make())
    result = index.search(tmp_path, "zzqvec", k=100, embedder=make())
    assert result["mode"] == "hybrid" and result["stale_vectors"] == 0
    by = {r["path"]: r for r in result["results"]}
    ranked = {p: r["vector_rank"] for p, r in by.items() if r["vector_rank"] is not None}
    assert max(ranked.values()) == 50
    assert sorted(ranked.values()) == list(range(1, 51))
    for rank, i in enumerate(range(n - 1, 9, -1), start=1):
        assert ranked[f"wiki/gen/p{i:02d}.md"] == rank
    fifty_first = by["wiki/gen/p09.md"]
    assert fifty_first["vector_rank"] is None
    assert fifty_first["keyword_rank"] == 1
    assert fifty_first["score"] == round(1 / 61, 6)
    assert not any(p in by for p in (f"wiki/gen/p{i:02d}.md" for i in range(0, 9)))


@pytest.mark.parametrize("vectors", [
    pytest.param([], id="zero-query-vectors"),
    pytest.param([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], id="two-query-vectors"),
])
def test_wrong_query_vector_count_falls_back_to_keyword(tmp_path, vectors):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    result = index.search(root, "조인", embedder=fixture_embedder(query_result=vectors))
    assert result["mode"] == "keyword"
    assert result["warnings"]
    assert result["results"][0]["path"] == JOIN
    assert all(r["vector_rank"] is None for r in result["results"])


def test_stale_vector_page_has_no_vector_rank(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    page = root / SUBQUERY
    page.write_text(page.read_text(encoding="utf-8") + "\n수정으로 벡터가 낡아졌다.\n", encoding="utf-8")
    result = index.search(root, "서브쿼리", k=20, embedder=fixture_embedder())
    assert result["stale_vectors"] == 1
    by = {r["path"]: r for r in result["results"]}
    assert by[SUBQUERY]["vector_rank"] is None
    assert by[SUBQUERY]["keyword_rank"] is not None
    assert by[SUBQUERY]["score"] == round(1 / (60 + by[SUBQUERY]["keyword_rank"]), 6)
    others = [r for p, r in by.items() if p != SUBQUERY and r["vector_rank"] is not None]
    assert others
    assert sorted(r["vector_rank"] for r in others) == list(range(1, len(others) + 1))


def test_query_embedding_failure_falls_back_to_keyword(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    result = index.search(root, "조인", embedder=fixture_embedder(fail_on_text="조인"))
    assert result["mode"] == "keyword"
    assert any("IndexToolError" in w for w in result["warnings"])
    assert result["results"][0]["path"] == JOIN
    assert all(r["vector_rank"] is None for r in result["results"])


def test_query_embedding_generic_exception_falls_back_without_leaking_message(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    emb = fixture_embedder(fail_on_text="조인", fail_exc=RuntimeError("secret-msg"))
    result = index.search(root, "조인", embedder=emb)
    assert result["mode"] == "keyword"
    assert any("RuntimeError" in w for w in result["warnings"])
    assert not any("secret-msg" in w for w in result["warnings"])
    assert result["results"][0]["path"] == JOIN


def test_query_embedding_wrong_length_vector_falls_back_to_keyword(tmp_path):
    root = make_root(tmp_path)
    index.build(root)
    index.embed(root, fixture_embedder())
    emb = fixture_embedder(query_vec=[1.0, 0.0])
    result = index.search(root, "조인", embedder=emb)
    assert result["mode"] == "keyword"
    assert result["warnings"]
    assert result["results"][0]["path"] == JOIN
    assert all(r["vector_rank"] is None for r in result["results"])


def test_stale_vectors_without_embedder_uses_config_model_and_dim(tmp_path):
    root = make_root(tmp_path)
    (root / "config.toml").write_text('[embedding]\nmodel = "cfg-m"\ndim = 4\n', encoding="utf-8")
    index.embed(root, MapEmbedder(model="cfg-m", dim=4))
    assert index.search(root, "조인")["stale_vectors"] == 0
    page = root / JOIN
    page.write_text(page.read_text(encoding="utf-8") + "\n변경\n", encoding="utf-8")
    assert index.search(root, "조인")["stale_vectors"] == 1
    (root / "config.toml").write_text('[embedding]\nmodel = "other-m"\ndim = 4\n', encoding="utf-8")
    assert index.search(root, "조인")["stale_vectors"] == len(FIXTURE_PAGES)
    (root / "config.toml").write_text('[embedding]\nmodel = "cfg-m"\ndim = 5\n', encoding="utf-8")
    assert index.search(root, "조인")["stale_vectors"] == len(FIXTURE_PAGES)


def _seed_and_snapshot(root):
    index.build(root)
    index.embed(root, fixture_embedder())
    return vector_rows(root)


def test_second_batch_failure_rolls_back(tmp_path, capsys):
    root = make_root(tmp_path)
    before = _seed_and_snapshot(root)
    for i in range(70):
        write_page(root, f"wiki/gen/g{i:02d}.md", f"생성{i:02d}", f"본문 {i}", type="concept")
    (root / CLIMBING).unlink()
    emb = fixture_embedder(fail_on_call=2)
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys, embedder=emb)
    assert code == 2
    assert out == ""
    assert err.strip()
    assert [len(c) for c in emb.calls][:2] == [64, 6]
    assert vector_rows(root) == before
    log = read_jsonl(root, "embed-log.jsonl")
    assert log[-1].get("error")


@pytest.mark.parametrize("kwargs", [
    pytest.param({"count_delta": -1}, id="too-few-vectors"),
    pytest.param({"count_delta": 1}, id="too-many-vectors"),
    pytest.param({"dim_delta": 1}, id="wrong-dimension"),
])
def test_bad_embedder_output_rolls_back(tmp_path, capsys, kwargs):
    root = make_root(tmp_path)
    before = _seed_and_snapshot(root)
    page = root / WINDOW
    page.write_text(page.read_text(encoding="utf-8") + "\n변경\n", encoding="utf-8")
    (root / CLIMBING).unlink()
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys,
                             embedder=fixture_embedder(**kwargs))
    assert code == 2
    assert out == ""
    assert err.strip()
    assert vector_rows(root) == before
    assert read_jsonl(root, "embed-log.jsonl")[-1].get("error")
    assert index.build(root)["pages"] == len(FIXTURE_PAGES) - 1


def test_generic_exception_from_embedder_rolls_back(tmp_path, capsys):
    root = make_root(tmp_path)
    before = _seed_and_snapshot(root)
    page = root / JOIN
    page.write_text(page.read_text(encoding="utf-8") + "\n변경\n", encoding="utf-8")
    (root / CLIMBING).unlink()
    with pytest.raises(index.IndexToolError) as info:
        index.embed(root, fixture_embedder(fail_on_call=1, fail_exc=RuntimeError("secret-msg")))
    assert "secret-msg" not in str(info.value)
    assert vector_rows(root) == before
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys,
                             embedder=fixture_embedder(fail_on_call=1, fail_exc=RuntimeError("secret-msg")))
    assert code == 2 and out == ""
    assert "RuntimeError" in err and "secret-msg" not in err
    assert vector_rows(root) == before
    line = read_jsonl(root, "embed-log.jsonl")[-1]
    assert set(line) == {"ts", "error"}
    assert "secret-msg" not in line["error"]


def test_failed_embed_python_api_raises_and_keeps_rows(tmp_path):
    root = make_root(tmp_path)
    before = _seed_and_snapshot(root)
    page = root / JOIN
    page.write_text(page.read_text(encoding="utf-8") + "\n변경\n", encoding="utf-8")
    with pytest.raises(index.IndexToolError):
        index.embed(root, fixture_embedder(count_delta=-1))
    assert vector_rows(root) == before


def _openai(monkeypatch, error=None):
    fake = FakeOpenAI(error=error)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def test_api_key_environment_wins_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text('OPENAI_API_KEY="sk-file"\n', encoding="utf-8")
    assert index.api_key(tmp_path, {"OPENAI_API_KEY": "sk-env"}) == "sk-env"


@pytest.mark.parametrize("line,expected", [
    pytest.param('OPENAI_API_KEY="sk-dq"', "sk-dq", id="double-quoted"),
    pytest.param("OPENAI_API_KEY='sk-sq'", "sk-sq", id="single-quoted"),
    pytest.param("OPENAI_API_KEY=sk-bare   ", "sk-bare", id="bare-trailing-space"),
])
def test_api_key_from_dotenv(tmp_path, line, expected):
    (tmp_path / ".env").write_text(f"# note\nOTHER=zzz\n{line}\nMORE=1\n", encoding="utf-8")
    assert index.api_key(tmp_path, {}) == expected


def test_api_key_empty_environment_value_falls_back_to_dotenv(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-file\n", encoding="utf-8")
    assert index.api_key(tmp_path, {"OPENAI_API_KEY": ""}) == "sk-file"


def test_api_key_absent_everywhere(tmp_path):
    assert index.api_key(tmp_path, {}) is None
    (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
    assert index.api_key(tmp_path, {}) is None


@pytest.mark.parametrize("source,expected_key", [
    pytest.param("env", "sk-env", id="environment-only"),
    pytest.param("dotenv", "sk-file", id="dotenv-only-quotes-stripped"),
    pytest.param("both", "sk-env", id="both-environment-wins"),
])
def test_cli_embed_uses_key_source(tmp_path, monkeypatch, capsys, source, expected_key):
    root = make_root(tmp_path)
    fake = _openai(monkeypatch)
    environ = {}
    if source in ("env", "both"):
        environ["OPENAI_API_KEY"] = "sk-env"
    if source in ("dotenv", "both"):
        (root / ".env").write_text('OPENAI_API_KEY="sk-file"\n', encoding="utf-8")
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys, environ=environ)
    assert code == 0, err
    result = json.loads(out)
    assert result["embedded"] == len(FIXTURE_PAGES)
    assert fake.requests
    assert {r["auth"] for r in fake.requests} == {f"Bearer {expected_key}"}


def test_cli_embed_without_key_fails_and_logs(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    fake = _openai(monkeypatch)
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys, environ={})
    assert code == 2
    assert out == ""
    assert "OPENAI_API_KEY not set" in err
    assert fake.requests == []
    assert vector_rows(root) == []
    line = read_jsonl(root, "embed-log.jsonl")[-1]
    assert set(line) == {"ts", "error"}
    assert "OPENAI_API_KEY not set" in line["error"]


def test_cli_embed_builds_embedder_from_config(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    (root / "config.toml").write_text('[embedding]\nmodel = "cfg-model"\ndim = 6\nmin_free_mb = 0\n',
                                      encoding="utf-8")
    fake = _openai(monkeypatch)
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys, environ={"OPENAI_API_KEY": "sk-x"})
    assert code == 0, err
    assert {(r["body"]["model"], r["body"]["dimensions"]) for r in fake.requests} == {("cfg-model", 6)}
    result = json.loads(out)
    assert result["model"] == "cfg-model" and result["dim"] == 6
    assert {(r[1], r[2]) for r in vector_rows(root)} == {("cfg-model", 6)}


@pytest.mark.parametrize("text,expected", [
    pytest.param(None, ("text-embedding-3-small", 768, 0), id="no-file"),
    pytest.param("[other]\nx = 1\n", ("text-embedding-3-small", 768, 0), id="no-table"),
    pytest.param("[embedding]\n", ("text-embedding-3-small", 768, 0), id="empty-table"),
    pytest.param("[embedding]\ndim = 256\n", ("text-embedding-3-small", 256, 0), id="partial-keys"),
    pytest.param('[embedding]\nmodel = "m"\ndim = 8\nmin_free_mb = 1500\n', ("m", 8, 1500), id="all-keys"),
])
def test_embedding_config(tmp_path, text, expected):
    if text is not None:
        (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    cfg = index.embedding_config(tmp_path)
    assert (cfg["model"], cfg["dim"], cfg["min_free_mb"]) == expected


def test_cli_min_free_mb_from_config_and_flag(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    (root / "config.toml").write_text("[embedding]\nmin_free_mb = 500\n", encoding="utf-8")
    monkeypatch.setattr(index, "free_memory_mb", lambda: 100.0)
    code, out, _ = run_cli(index, ["--root", root, "embed"], capsys, embedder=fixture_embedder())
    assert code == 0
    assert json.loads(out)["skipped"] == "memory"
    assert vector_rows(root) == []
    code, out, _ = run_cli(index, ["--root", root, "embed", "--min-free-mb", "0"], capsys,
                           embedder=fixture_embedder())
    assert code == 0
    assert json.loads(out)["embedded"] == len(FIXTURE_PAGES)


def test_cli_embed_success_log(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, _ = run_cli(index, ["--root", root, "embed"], capsys, embedder=fixture_embedder())
    assert code == 0
    assert out.endswith("\n") and len(out.splitlines()) == 1
    result = json.loads(out)
    log = read_jsonl(root, "embed-log.jsonl")
    assert len(log) == 1
    for key, value in result.items():
        assert log[0][key] == value
    ts = log[0]["ts"]
    datetime.datetime.fromisoformat(ts)
    assert "." not in ts


def test_cli_embed_twice_appends_two_log_lines(tmp_path, capsys):
    root = make_root(tmp_path)
    for _ in range(2):
        code, _, _ = run_cli(index, ["--root", root, "embed"], capsys, embedder=fixture_embedder())
        assert code == 0
    log = read_jsonl(root, "embed-log.jsonl")
    assert len(log) == 2
    assert log[0]["embedded"] == len(FIXTURE_PAGES) and log[0]["unchanged"] == 0
    assert log[1]["embedded"] == 0 and log[1]["unchanged"] == len(FIXTURE_PAGES)


def test_cli_embed_skipped_log(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    monkeypatch.setattr(index, "free_memory_mb", lambda: 5.0)
    code, out, _ = run_cli(index, ["--root", root, "embed", "--min-free-mb", "1000"], capsys,
                           embedder=fixture_embedder())
    assert code == 0
    log = read_jsonl(root, "embed-log.jsonl")
    assert len(log) == 1 and log[0]["skipped"] == "memory" and "ts" in log[0]
    assert json.loads(out)["skipped"] == "memory"


def test_cli_embed_failure_log(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys,
                             embedder=fixture_embedder(fail_on_call=1))
    assert code == 2
    log = read_jsonl(root, "embed-log.jsonl")
    assert len(log) == 1
    assert set(log[0]) == {"ts", "error"}
    assert log[0]["error"].strip() and log[0]["error"].strip() in err


def test_cli_search_output_and_log(tmp_path, capsys):
    root = make_root(tmp_path)
    emb = fixture_embedder()
    run_cli(index, ["--root", root, "embed"], capsys, embedder=emb)
    code, out, _ = run_cli(index, ["--root", root, "search", "조인", "--k", "3"], capsys,
                           embedder=fixture_embedder())
    assert code == 0
    assert out.endswith("\n") and len(out.splitlines()) == 1
    assert "조인" in out and "\\u" not in out
    result = json.loads(out)
    assert result["mode"] == "hybrid"
    assert len(result["results"]) == 3
    log = read_jsonl(root, "search-log.jsonl")
    assert len(log) == 1
    assert log[0]["query"] == "조인" and log[0]["k"] == 3
    assert log[0]["mode"] == "hybrid" and log[0]["source"] == "search"
    assert log[0]["results"] == paths(result)
    datetime.datetime.fromisoformat(log[0]["ts"])
    assert "." not in log[0]["ts"]

    run_cli(index, ["--root", root, "search", "정규화"], capsys, embedder=fixture_embedder())
    assert len(read_jsonl(root, "search-log.jsonl")) == 2


def test_cli_search_without_key_is_keyword_with_warning(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    fake = _openai(monkeypatch)
    code, out, _ = run_cli(index, ["--root", root, "search", "조인"], capsys, environ={})
    assert code == 0
    result = json.loads(out)
    assert result["mode"] == "keyword"
    assert "vector search disabled: OPENAI_API_KEY not set" in result["warnings"]
    assert fake.requests == []
    assert read_jsonl(root, "search-log.jsonl")[0]["mode"] == "keyword"


def test_cli_search_with_key_is_hybrid(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    _openai(monkeypatch)
    run_cli(index, ["--root", root, "embed"], capsys, environ={"OPENAI_API_KEY": "sk-x"})
    code, out, err = run_cli(index, ["--root", root, "search", "조인"], capsys,
                             environ={"OPENAI_API_KEY": "sk-x"})
    assert code == 0, err
    assert json.loads(out)["mode"] == "hybrid"


def test_openai_embedder_request_and_response(monkeypatch):
    fake = _openai(monkeypatch)
    emb = index.OpenAIEmbedder("text-embedding-3-small", 3, SECRET)
    assert emb.model == "text-embedding-3-small" and emb.dim == 3
    vectors = emb.embed(["a", "bb"])
    assert vectors == [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    (req,) = fake.requests
    assert req["url"] == "https://api.openai.com/v1/embeddings"
    assert req["method"] == "POST"
    assert req["auth"] == f"Bearer {SECRET}"
    assert req["body"]["model"] == "text-embedding-3-small"
    assert req["body"]["input"] == ["a", "bb"]
    assert req["body"]["dimensions"] == 3
    assert fake.timeouts == [60]


@pytest.mark.parametrize("error", [
    pytest.param(http_error(401, b'{"error": "bad key ' + SECRET.encode() + b'"}'), id="http-error"),
    pytest.param(urllib.error.URLError("connection refused"), id="url-error"),
])
def test_openai_embedder_errors_do_not_leak_key(monkeypatch, error):
    _openai(monkeypatch, error=error)
    emb = index.OpenAIEmbedder("text-embedding-3-small", 3, SECRET)
    with pytest.raises(index.IndexToolError) as info:
        emb.embed(["a"])
    assert SECRET not in str(info.value)


def _scan_for_secret(root, outputs):
    for text in outputs:
        assert SECRET not in text
    cache = root / ".cache"
    files = [p for p in cache.rglob("*") if p.is_file()]
    assert files, "scan would be vacuous without .cache files"
    for p in files:
        assert SECRET.encode() not in p.read_bytes(), p
    links = root / "data" / "goal_links.csv"
    if links.exists():
        assert SECRET not in links.read_text(encoding="utf-8")


def test_secret_never_written_anywhere(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    (root / ".env").write_text(f"OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
    outputs = []

    ok = _openai(monkeypatch)
    for argv in (["embed"], ["search", "조인"], ["build"]):
        code, out, err = run_cli(index, ["--root", root, *argv], capsys, environ={})
        assert code == 0, err
        outputs += [out, err]
    assert {r["auth"] for r in ok.requests} == {f"Bearer {SECRET}"}

    page = root / JOIN
    page.write_text(page.read_text(encoding="utf-8") + "\n변경\n", encoding="utf-8")
    _openai(monkeypatch, error=http_error(401, f'{{"error": "{SECRET}"}}'.encode()))
    code, out, err = run_cli(index, ["--root", root, "embed"], capsys, environ={})
    assert code == 2
    outputs += [out, err]
    code, out, err = run_cli(index, ["--root", root, "search", "조인"], capsys, environ={})
    outputs += [out, err]

    _scan_for_secret(root, outputs)
    assert read_jsonl(root, "embed-log.jsonl")


VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               4596.
Pages active:                            55119.
Pages inactive:                          50904.
Pages speculative:                        3588.
Pages wired down:                       755624.
"""


def _patch_run(monkeypatch, stdout=None, exc=None):
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    return calls


def test_free_memory_mb_sample_and_call_arguments(monkeypatch):
    calls = _patch_run(monkeypatch, VM_STAT)
    assert index.free_memory_mb() == pytest.approx((4596 + 50904 + 3588) * 16384 / 1048576)
    assert index.free_memory_mb() == pytest.approx(923.25)
    (args, kwargs) = calls[0]
    assert args[0] == ["vm_stat"]
    assert kwargs.get("timeout") == 10
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("check") is True


@pytest.mark.parametrize("stdout", [
    pytest.param(VM_STAT.replace("Pages speculative:                        3588.\n", ""), id="no-speculative-line"),
    pytest.param(VM_STAT.replace("Mach Virtual Memory Statistics: (page size of 16384 bytes)\n", ""),
                 id="no-page-size-header"),
])
def test_free_memory_mb_missing_line_is_none(monkeypatch, stdout):
    assert stdout != VM_STAT
    _patch_run(monkeypatch, stdout)
    assert index.free_memory_mb() is None


@pytest.mark.parametrize("exc", [
    pytest.param(FileNotFoundError("vm_stat"), id="file-not-found"),
    pytest.param(subprocess.CalledProcessError(1, ["vm_stat"]), id="called-process-error"),
    pytest.param(subprocess.TimeoutExpired(["vm_stat"], 10), id="timeout-expired"),
])
def test_free_memory_mb_failure_is_none(monkeypatch, exc):
    _patch_run(monkeypatch, exc=exc)
    assert index.free_memory_mb() is None


def test_plist_content(tmp_path):
    root = tmp_path.resolve()
    py = "/opt/venv/bin/python3"
    data = plistlib.loads(index.plist(root, py).encode("utf-8"))
    assert data["Label"] == "io.github.doggyfootprint.wiki-embed"
    assert data["StartCalendarInterval"]["Hour"] == 4
    assert data["StartCalendarInterval"]["Minute"] == 0
    args = data["ProgramArguments"]
    assert len(args) == 3
    assert args[0] == "/bin/sh" and args[1] == "-c"
    script = Path(index.__file__).resolve()
    assert args[2] == (
        f"cd {root} && {py} {script} --root {root} build"
        f" && {py} {script} --root {root} embed"
    )
    assert data["StandardOutPath"] == f"{root}/.cache/launchd.log"
    assert data["StandardErrorPath"] == f"{root}/.cache/launchd.log"


def test_cli_plist_with_python_flag(tmp_path, capsys):
    root = tmp_path.resolve()
    code, out, _ = run_cli(index, ["--root", root, "plist", "--python", "/x/py"], capsys)
    assert code == 0
    data = plistlib.loads(out.encode("utf-8"))
    assert f"/x/py {Path(index.__file__).resolve()} --root" in data["ProgramArguments"][2]
    assert str(root) in data["ProgramArguments"][2]


def test_cli_plist_defaults_to_current_python(tmp_path, capsys):
    root = tmp_path.resolve()
    code, out, _ = run_cli(index, ["--root", root, "plist"], capsys)
    assert code == 0
    data = plistlib.loads(out.encode("utf-8"))
    assert f"{sys.executable} {Path(index.__file__).resolve()} --root" in data["ProgramArguments"][2]


def test_cli_empty_query_is_user_error(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = run_cli(index, ["--root", root, "search", "   "], capsys, environ={})
    assert code == 2
    assert out == ""
    assert "empty query" in err
    assert read_jsonl(root, "search-log.jsonl") == []


def test_cli_missing_subcommand_argument_exits_2(tmp_path, capsys):
    root = make_root(tmp_path)
    code, out, err = run_cli(index, ["--root", root, "search"], capsys, environ={})
    assert code == 2
    assert out == ""
    assert err.strip()


def test_search_500_pages_within_3_seconds(tmp_path):
    words = ["조인", "서브쿼리", "정규화", "트랜잭션", "인덱스", "테이블", "컬럼", "제약조건", "select", "where"]
    for i in range(500):
        body = " ".join(words[(i + j) % len(words)] + str(j % 7) for j in range(260))
        body = body[:2000]
        write_page(tmp_path, f"wiki/gen/p{i:03d}.md", f"문서{i:03d}", body, type="concept")
    start = time.perf_counter()
    result = index.search(tmp_path, "조인 서브쿼리")
    elapsed = time.perf_counter() - start
    assert result["results"]
    assert elapsed <= 3.0


def test_index_commands_leave_wiki_and_reviews_untouched(tmp_path, capsys):
    root = make_root(tmp_path)
    before = digest_tree(root, "wiki", "data/reviews.csv")
    assert before
    for argv in (["build"], ["embed"], ["search", "조인"], ["plist"]):
        code, _, err = run_cli(index, ["--root", root, *argv], capsys, embedder=fixture_embedder(), environ={})
        assert code == 0, err
    assert digest_tree(root, "wiki", "data/reviews.csv") == before


def test_resolve_root_order(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    assert index.resolve_root("x", {"LLM_WIKI_ROOT": "/env"}, sub) == sub / "x"
    assert index.resolve_root(str(tmp_path), {"LLM_WIKI_ROOT": "/env"}, sub) == tmp_path
    assert index.resolve_root(None, {"LLM_WIKI_ROOT": str(tmp_path)}, sub) == tmp_path
    assert index.resolve_root(None, {}, sub) == repo
    bare = tmp_path / "bare"
    bare.mkdir()
    assert index.resolve_root(None, {}, bare) in (bare, *[d for d in bare.parents if (d / ".git").exists()])


def test_cli_without_root_uses_git_top(tmp_path, capsys):
    root = make_root(tmp_path)
    (root / ".git").mkdir()
    code, out, _ = run_cli(index, ["build"], capsys, environ={}, cwd=root / "wiki")
    assert code == 0
    assert json.loads(out)["pages"] == len(FIXTURE_PAGES)
