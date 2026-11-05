import datetime
import time

import pytest

import quiz
from quiz_support import (
    D, DS, SOLO, csv_bytes, deck_bytes, oracle_due, page, row, snapshot, write, write_csv,
)

A_ = "wiki/study/Alpha.md"
B_ = "wiki/study/Beta.md"


def text_of(root):
    return deck_bytes(root).decode("utf-8")


def alpha_beta_root(tmp_path, extra_rows=()):
    root = tmp_path / "r"
    page(root, A_, level=2, created="2026-10-20", sections=[
        ("요약", "요약 문장"),
        ("내가 정리한 것", "첫 줄\n둘째 줄"),
        ("오해와 교정", "- 오해 하나\n- 오해 둘"),
        ("연결", "- [[Beta]] — r\n- [[Gamma]] — r"),
    ])
    page(root, B_, created="2026-11-03", sections=[])
    write_csv(root, [row("2026-11-01", A_, "again"), *extra_rows])
    return root


def expected_alpha_beta(with_warning_line=None):
    da = oracle_due("2026-10-20", [("2026-11-01", "again")])
    overdue = (D - da).days
    assert overdue >= 0
    assert oracle_due("2026-11-03", []) == D
    lines = [
        "---", "type: quiz-deck", "version: 1", "generated: 2026-11-05", "---",
        "# Quiz deck", "",
        "## Due (2)", "",
        "### Alpha",
        "- path: wiki/study/Alpha.md",
        "- level: L2 (다중구조적)",
        f"- due: {da.isoformat()} (overdue {overdue}d)",
        "- last: 2026-11-01 again",
        "- summary: 요약 문장",
        "- mine: 첫 줄 / 둘째 줄",
        "- misconceptions:",
        "  - 오해 하나",
        "  - 오해 둘",
        "- links: Beta, Gamma",
        "",
        "### Beta",
        "- path: wiki/study/Beta.md",
        "- level: -",
        "- due: 2026-11-05 (overdue 0d)",
        "- last: -",
        "- summary: -",
        "- mine: -",
        "- misconceptions: -",
        "- links: -",
        "",
        "## Frontier (1)",
        "- [[Gamma]] — from [[Alpha]]",
        "",
        "## Known (2)",
        "- Alpha (L2)",
        "- Beta (L-)",
    ]
    if with_warning_line is not None:
        lines += ["", "## Warnings", with_warning_line]
    return "\n".join(lines) + "\n"


def test_O11_C21_exact_bytes_no_warnings(tmp_path):
    root = alpha_beta_root(tmp_path)
    res = quiz.deck(root, D)
    want = expected_alpha_beta()
    assert deck_bytes(root) == want.encode("utf-8")
    assert res == {"path": "chat/deck.md", "chars": len(want), "due": 2, "frontier": 1, "known": 2}
    assert (root / "chat" / "inbox" / ".gitkeep").exists()


def test_O11_C21_exact_bytes_is_deterministic(tmp_path):
    root = alpha_beta_root(tmp_path)
    quiz.deck(root, D)
    first = deck_bytes(root)
    quiz.deck(root, D)
    assert deck_bytes(root) == first


def test_O11_layout_rules_eol_trailing(tmp_path):
    root = alpha_beta_root(tmp_path)
    quiz.deck(root, D)
    raw = deck_bytes(root)
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n") and b"\r" not in raw
    assert all(ln == ln.rstrip() for ln in raw.decode("utf-8").split("\n"))


def test_O11_C21_with_warning_line_prefix_only(tmp_path):
    root = alpha_beta_root(tmp_path, extra_rows=[row("2026-11-02", A_, "ok")])
    res = quiz.deck(root, D)
    got = text_of(root).split("\n")
    prefix = "- data/reviews.csv:3: "
    want = expected_alpha_beta(with_warning_line=prefix).split("\n")
    assert got[:-2] == want[:-2]
    assert got[-2].startswith(prefix) and got[-1] == ""
    assert got[-4] == "" and got[-3] == "## Warnings"
    assert res["chars"] == len(text_of(root))


def test_O11_warnings_section_absent_without_warnings(tmp_path):
    root = alpha_beta_root(tmp_path)
    quiz.deck(root, D)
    assert "## Warnings" not in text_of(root)


def test_O11_page_warning_listed_and_page_still_known(tmp_path):
    root = alpha_beta_root(tmp_path)
    page(root, "wiki/study/NoDate.md", level=1)
    quiz.deck(root, D)
    t = text_of(root)
    assert t.endswith("\n")
    head, _, warn = t.partition("\n## Warnings\n")
    assert warn.startswith("- wiki/study/NoDate.md")
    assert "- NoDate (L1)" in head and "### NoDate" not in head
    assert "\n\n## Warnings\n" in t


def test_O11_empty_wiki_exact_bytes(tmp_path):
    root = tmp_path / "r"
    (root / "wiki").mkdir(parents=True)
    res = quiz.deck(root, D)
    want = (
        "---\ntype: quiz-deck\nversion: 1\ngenerated: 2026-11-05\n---\n# Quiz deck\n\n"
        "## Due (0)\n\n## Frontier (0)\n\n## Known (0)\n"
    )
    assert deck_bytes(root) == want.encode()
    assert res == {"path": "chat/deck.md", "chars": len(want), "due": 0, "frontier": 0, "known": 0}
    assert csv_bytes(root) is None


def test_O11_zero_due_zero_frontier_with_known_exact(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/study/Later.md", created="2026-11-05")
    quiz.deck(root, D)
    assert text_of(root) == (
        "---\ntype: quiz-deck\nversion: 1\ngenerated: 2026-11-05\n---\n# Quiz deck\n\n"
        "## Due (0)\n\n## Frontier (0)\n\n## Known (1)\n- Later (L-)\n"
    )


def test_O11_known_sorted_by_title_then_path(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/b/X.md", title="Same", level=3, created="2026-11-05")
    page(root, "wiki/a/Y.md", title="Same", level=1, created="2026-11-05")
    page(root, "wiki/c/Z.md", title="Beta", created="2026-11-05")
    page(root, "wiki/c/W.md", title="가나다", level=0, created="2026-11-05")
    page(root, "wiki/c/V.md", title="Alpha", level=4, created="2026-11-05")
    quiz.deck(root, D)
    known = text_of(root).split("## Known (5)\n")[1].split("\n")
    assert known[:5] == ["- Alpha (L4)", "- Beta (L-)", "- Same (L1)", "- Same (L3)", "- 가나다 (L0)"]


def test_O11_level_lines_for_all_levels(tmp_path):
    root = tmp_path / "r"
    for n in range(5):
        page(root, f"wiki/s/L{n}.md", title=f"Lv{n}", level=n, created="2026-10-01")
    quiz.deck(root, D)
    t = text_of(root)
    for n in range(5):
        chunk = t.split(f"### Lv{n}\n")[1].split("\n")
        assert chunk[1] == f"- level: L{n} ({SOLO[n]})"
        assert f"- Lv{n} (L{n})" in t


def test_O11_due_item_order_follows_due_rule(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/B.md", title="First", created="2026-10-28")
    page(root, "wiki/s/A.md", title="Second", created="2026-11-01")
    page(root, "wiki/s/C.md", title="Third", created="2026-11-01")
    quiz.deck(root, D)
    heads = [ln for ln in text_of(root).split("\n") if ln.startswith("### ")]
    assert heads == ["### First", "### Second", "### Third"]


def test_O11_caps_applied_in_deck_items(tmp_path):
    root = tmp_path / "r"
    s = "".join(chr(0xAC00 + i) for i in range(301))
    page(root, "wiki/s/A.md", created="2026-10-01", sections=[
        ("요약", s), ("오해와 교정", "- m1\n- m2\n- m3\n- m4"),
        ("연결", "\n".join(f"- [[T{i:02d}]]" for i in range(1, 12))),
    ])
    quiz.deck(root, D)
    t = text_of(root)
    assert f"- summary: {s[:299]}…\n" in t
    assert "- misconceptions:\n  - m2\n  - m3\n  - m4\n" in t and "  - m1" not in t
    assert "- links: " + ", ".join(f"T{i:02d}" for i in range(1, 11)) + "\n" in t


def due_root(tmp_path, n):
    root = tmp_path / "r"
    for i in range(n):
        page(root, f"wiki/s/P{i:02d}.md", title=f"P{i:02d}", created="2026-10-01")
    return root


@pytest.mark.parametrize("n,listed", [(9, 9), (10, 10), (11, 10), (12, 10)])
def test_O11_C22_due_boundaries(tmp_path, n, listed):
    root = due_root(tmp_path, n)
    res = quiz.deck(root, D)
    t = text_of(root)
    assert f"## Due ({listed})\n" in t
    assert sum(1 for ln in t.split("\n") if ln.startswith("### ")) == listed
    assert res["due"] == listed and res["known"] == n and res["frontier"] == 0
    assert f"## Known ({n})\n" in t


@pytest.mark.parametrize("n,listed", [(9, 9), (10, 10), (11, 10), (12, 10)])
def test_O11_C22_frontier_boundaries(tmp_path, n, listed):
    root = tmp_path / "r"
    body = [f"- [[T{i:02d}]]" for i in range(1, n + 1)]
    for k in range(0, n, 5):
        page(root, f"wiki/s/F{k}.md", created="2026-11-05", sections=[("연결", "\n".join(body[k:k + 5]))])
    res = quiz.deck(root, D)
    t = text_of(root)
    sec = t.split(f"## Frontier ({listed})\n")[1].split("\n\n## ")[0].split("\n")
    assert len(sec) == listed and all(ln.startswith("- [[T") for ln in sec)
    assert [ln.split("]]")[0][4:] for ln in sec] == [f"T{i:02d}" for i in range(1, listed + 1)]
    assert res["frontier"] == listed


def test_O11_C22_twelve_and_twelve(tmp_path):
    root = tmp_path / "r"
    for i in range(12):
        page(root, f"wiki/s/P{i:02d}.md", title=f"P{i:02d}", created="2026-10-01",
             sections=[("연결", f"- [[T{i:02d}]]")])
    res = quiz.deck(root, D)
    assert (res["due"], res["frontier"], res["known"]) == (10, 10, 12)
    t = text_of(root)
    assert "## Due (10)\n" in t and "## Frontier (10)\n" in t and "## Known (12)\n" in t


def long_text(n, seed):
    return (seed + "".join(chr(0xAC00 + (i * 7) % 11000) for i in range(n)))[:n]


def test_Q1_deck_size_cap(tmp_path):
    root = tmp_path / "r"
    for i in range(1, 291):
        page(root, f"wiki/k/k{i:03d}.md", title=f"K{i:03d}-" + "x" * 15, created="2026-11-05")
    for i in range(1, 11):
        links = [f"[[f{i:02d}]]"] + [f"[[k{j:03d}]]" for j in range(1, 11)]
        page(root, f"wiki/study/d{i:02d}.md", title=f"Due-concept-title-{i:02d}", level=2, created="2026-10-01",
             sections=[
                 ("요약", long_text(400, "s")),
                 ("내가 정리한 것", long_text(450, "m") + "\n" + long_text(450, "n")),
                 ("오해와 교정", "\n".join(f"- {long_text(300, 'q' + str(k))}" for k in range(4))),
                 ("연결", "\n".join(f"- {l} — r" for l in links)),
             ])
    res = quiz.deck(root, D)
    t = text_of(root)
    assert (res["due"], res["frontier"], res["known"]) == (10, 10, 300)
    assert res["chars"] == len(t)
    assert res["chars"] <= 30000


def test_Q2_deck_time_1000_pages_5000_rows(tmp_path):
    root = tmp_path / "r"
    n = 1000
    for i in range(n):
        page(root, f"wiki/s/p{i:04d}.md", title=f"Page {i:04d}", level=i % 5,
             created=(datetime.date(2026, 6, 1) + datetime.timedelta(days=i % 30)).isoformat(),
             sections=[("요약", f"요약 {i}"), ("연결", f"- [[Missing{i % 50:02d}]] — r")])
    dates = ["2026-07-01", "2026-07-15", "2026-08-01", "2026-08-20", "2026-09-10"]
    ratings = ["good", "again", "easy", "hard", "good"]
    rows = [row(dates[k], f"wiki/s/p{i:04d}.md", ratings[(i + k) % 5], rid=f"r{i}-{k}")
            for i in range(n) for k in range(5)]
    assert len(rows) == 5000
    write_csv(root, rows)
    t0 = time.perf_counter()
    res = quiz.deck(root, D)
    elapsed = time.perf_counter() - t0
    assert res["known"] == 1000
    assert elapsed <= 10.0, elapsed


def test_O11_v3_mine_placeholder_only_and_blank_lines_render_dash_or_joined(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", title="A", created="2026-10-01", sections=[
        ("내가 정리한 것", "(사용자가 말하거나 자료에서 온 내용)")])
    page(root, "wiki/s/B.md", title="B", created="2026-10-01", sections=[
        ("내가 정리한 것", "  가  \n\n나")])
    quiz.deck(root, D)
    t = text_of(root)
    assert "### A\n" in t and t.split("### A\n")[1].split("\n\n")[0].split("\n")[5] == "- mine: -"
    assert "- mine: 가 / 나\n" in t


def test_O11_v3_non_utf8_page_warned_not_known(tmp_path):
    root = alpha_beta_root(tmp_path)
    write(root / "wiki" / "study" / "Bad.md", b"---\ntype: concept\n---\n# Bad\n\xff\xfe\n")
    res = quiz.deck(root, D)
    t = text_of(root)
    assert res["known"] == 2 and "Bad" not in t.split("## Warnings")[0]
    assert t.split("## Warnings\n")[1].startswith("- wiki/study/Bad.md")


def test_O11_v3_header_mismatch_warning_line(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/A.md", created="2026-11-05")
    write(root / "data" / "reviews.csv", "date,page\n")
    quiz.deck(root, D)
    t = text_of(root)
    assert t.split("## Warnings\n")[1].startswith("- data/reviews.csv:1: ")


def frontier_lines(root):
    return text_of(root).split("## Frontier (")[1].split("\n\n## ")[0].split("\n")[1:]


def test_O11_v4_frontier_line_with_multiple_sources_sorted_titles(tmp_path):
    root = tmp_path / "r"
    page(root, "wiki/s/Zed.md", title="Alpha", created="2026-11-05", sections=[("연결", "- [[T]]\n- [[U]]")])
    page(root, "wiki/s/Amy.md", title="Beta", created="2026-11-05", sections=[("연결", "- [[T]]")])
    page(root, "wiki/s/Mid.md", title="Gamma", created="2026-11-05", sections=[("연결", "- [[T]]")])
    quiz.deck(root, D)
    assert frontier_lines(root) == ["- [[T]] — from [[Alpha]], [[Beta]], [[Gamma]]", "- [[U]] — from [[Alpha]]"]


def test_O11_v4_frontier_order_and_cut_follow_F6_keys_not_title(tmp_path):
    root = tmp_path / "r"
    linkers = {}

    def mk(title, level, targets):
        page(root, f"wiki/s/{title}.md", title=title, level=level, created="2026-11-05",
             sections=[("연결", "\n".join(f"- [[{t}]]" for t in targets))])
        for t in targets:
            linkers.setdefault(t, {})[title] = level

    for lv in range(5):
        mk(f"Lv{lv}", lv, [f"t{lv}_{k}" for k in range(3)])
    mk("LvN", None, ["tn_0", "tn_1"])
    mk("Pa", 1, ["Shared", "ZZ"])
    mk("Pb", 2, ["Shared"])
    assert len(linkers) > 10

    def key(t):
        lvls = [v for v in linkers[t].values() if v is not None]
        return (-len(linkers[t]), -(max(lvls) if lvls else -1), t)

    want_targets = sorted(linkers, key=key)[:10]
    want = [f"- [[{t}]] — from " + ", ".join(f"[[{x}]]" for x in sorted(linkers[t])) for t in want_targets]
    res = quiz.deck(root, D)
    assert res["frontier"] == 10
    assert "## Frontier (10)\n" in text_of(root)
    assert frontier_lines(root) == want
    # the fixture distinguishes F6 order from plain title order and from the unsorted cut
    assert want_targets != sorted(linkers)[:10]
    assert want_targets[0] == "Shared" and want_targets[1:4] == ["t4_0", "t4_1", "t4_2"]
