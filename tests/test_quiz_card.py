"""O4 (card content, caps) and O5 (card path rejection)."""
import pytest

import quiz
from quiz_support import bare_page, expect_quiz_error, page, write

P = "wiki/study/A.md"
ELL = "…"


def txt(n: int, seed: str = "") -> str:
    base = seed + "".join(chr(0xAC00 + (i * 7) % 11000) for i in range(n))
    return base[:n]


def mk(tmp_path, sections, **kw):
    root = tmp_path / "r"
    kw.setdefault("created", "2026-11-01")
    page(root, P, sections=sections, **kw)
    return root


def test_O4_C9_full_page(tmp_path):
    root = mk(tmp_path, [
        ("요약", "(한두 문장)\n요약 문장 하나\n\n요약 문장 둘"),
        ("내가 정리한 것", "첫 줄\n둘째 줄"),
        ("보충 (LLM)", "보충은 카드에 안 들어간다"),
        ("이해 기록", "- 2026-11-01 L2 다중구조적: ev"),
        ("오해와 교정", "- 오해 하나\n- 오해 둘"),
        ("연결", "- [[Beta]] — 관계\n- [[Gamma]] — 관계"),
        ("출처", "- [[NotALink]] x"),
    ], title="알파", level=2)
    c = quiz.card(root, P)
    assert c == {
        "path": P, "title": "알파", "level": 2,
        "summary": "요약 문장 하나 요약 문장 둘",
        "mine": "첫 줄\n둘째 줄",
        "misconceptions": ["오해 하나", "오해 둘"],
        "links": ["Beta", "Gamma"],
    }


def test_O4_level_none_and_title_stem(tmp_path):
    root = mk(tmp_path, [], title=None)
    c = quiz.card(root, P)
    assert c["level"] is None and c["title"] == "A"


# ----- caps -----

@pytest.mark.parametrize("n,truncated", [(299, False), (300, False), (301, True), (450, True)])
def test_O4_C10_summary_cap(tmp_path, n, truncated):
    s = txt(n)
    root = mk(tmp_path, [("요약", s)])
    got = quiz.card(root, P)["summary"]
    if truncated:
        assert got == s[:299] + ELL
        assert len(got) == 300 and got.endswith(ELL)
    else:
        assert got == s


@pytest.mark.parametrize("n2,truncated", [(399, False), (400, False), (401, True), (700, True)])
def test_O4_C10_mine_cap(tmp_path, n2, truncated):
    a, b = txt(399, "a"), txt(n2, "b")
    joined = a + "\n" + b
    root = mk(tmp_path, [("내가 정리한 것", a + "\n" + b)])
    got = quiz.card(root, P)["mine"]
    if truncated:
        assert got == joined[:799] + ELL
        assert len(got) == 800
    else:
        assert got == joined
        assert len(got) <= 800


@pytest.mark.parametrize("n,truncated", [(199, False), (200, False), (201, True), (400, True)])
def test_O4_C10_misconception_cap_each(tmp_path, n, truncated):
    m = txt(n)
    root = mk(tmp_path, [("오해와 교정", f"- {m}\n- 짧은 오해")])
    got = quiz.card(root, P)["misconceptions"]
    assert got[1] == "짧은 오해"
    if truncated:
        assert got[0] == m[:199] + ELL and len(got[0]) == 200
    else:
        assert got[0] == m


@pytest.mark.parametrize("count,want", [
    (0, []),
    (1, ["m1"]),
    (2, ["m1", "m2"]),
    (3, ["m1", "m2", "m3"]),
    (4, ["m2", "m3", "m4"]),
    (6, ["m4", "m5", "m6"]),
])
def test_O4_misconception_counts_keep_last_three(tmp_path, count, want):
    body = "\n".join(f"- m{i}" for i in range(1, count + 1))
    root = mk(tmp_path, [("오해와 교정", body)])
    assert quiz.card(root, P)["misconceptions"] == want


def test_O4_misconceptions_ignore_non_bullet_lines(tmp_path):
    root = mk(tmp_path, [("오해와 교정", "설명 문장\n- m1\n메모\n- m2\n")])
    assert quiz.card(root, P)["misconceptions"] == ["m1", "m2"]


# ----- links -----

def test_O4_links_alias_anchor_placeholder_duplicate(tmp_path):
    body = "\n".join([
        "- [[Beta]] — 관계",
        "- [[Gamma|감마]] — 별칭",
        "- [[Delta#소제목]] — 앵커",
        "- [[관련 개념]] — 어떤 관계인지",
        "- [[Beta]] — 중복",
        "- [[Eps]] — 끝",
    ])
    root = mk(tmp_path, [("연결", body)])
    assert quiz.card(root, P)["links"] == ["Beta", "Gamma", "Delta", "Eps"]


def test_O4_links_only_from_connection_section(tmp_path):
    root = mk(tmp_path, [
        ("요약", "[[Elsewhere]] 를 본다"),
        ("연결", "- [[In]] — x"),
        ("출처", "- [[Out]]"),
    ])
    assert quiz.card(root, P)["links"] == ["In"]


@pytest.mark.parametrize("n,want", [(9, 9), (10, 10), (11, 10), (14, 10)])
def test_O4_links_max_ten_in_order(tmp_path, n, want):
    body = "\n".join(f"- [[T{i:02d}]] — r" for i in range(1, n + 1))
    root = mk(tmp_path, [("연결", body)])
    assert quiz.card(root, P)["links"] == [f"T{i:02d}" for i in range(1, want + 1)]


# ----- missing sections / placeholders -----

def test_O4_missing_sections_give_empty_values(tmp_path):
    root = mk(tmp_path, [("보충 (LLM)", "x")])
    c = quiz.card(root, P)
    assert (c["summary"], c["mine"], c["misconceptions"], c["links"]) == ("", "", [], [])


def test_O4_template_placeholders_give_empty_summary_and_links(tmp_path):
    root = mk(tmp_path, [
        ("요약", "(한두 문장)"),
        ("오해와 교정", ""),
        ("연결", "- [[관련 개념]] — 어떤 관계인지"),
    ])
    c = quiz.card(root, P)
    assert c["summary"] == "" and c["misconceptions"] == [] and c["links"] == []


def test_O4_placeholder_is_whole_line_in_parentheses_only(tmp_path):
    root = mk(tmp_path, [("요약", "(a) 번호 붙은 문장\n(placeholder)\n끝 (괄호)")])
    assert quiz.card(root, P)["summary"] == "(a) 번호 붙은 문장 끝 (괄호)"


def test_O4_section_ends_at_next_heading(tmp_path):
    root = mk(tmp_path, [("요약", "S"), ("내가 정리한 것", "M")])
    c = quiz.card(root, P)
    assert c["summary"] == "S" and c["mine"] == "M"


def test_O4_crlf_page_has_no_carriage_returns(tmp_path):
    root = mk(tmp_path, [
        ("요약", "요약 하나\n요약 둘"), ("내가 정리한 것", "a\nb"),
        ("오해와 교정", "- m"), ("연결", "- [[Beta]] — r"),
    ], crlf=True, title="CR", level=1)
    c = quiz.card(root, P)
    assert c == {"path": P, "title": "CR", "level": 1, "summary": "요약 하나 요약 둘", "mine": "a\nb",
                 "misconceptions": ["m"], "links": ["Beta"]}


def test_O4_card_on_page_without_dates_still_works(tmp_path):
    """Errors: a page without created/updated is still usable by card."""
    root = mk(tmp_path, [("요약", "S")], created=None)
    assert quiz.card(root, P)["summary"] == "S"


def test_O4_card_does_not_write(tmp_path):
    from quiz_support import snapshot

    root = mk(tmp_path, [("요약", "S")])
    before = snapshot(root)
    quiz.card(root, P)
    assert snapshot(root) == before


# ----- O5 -----

def test_O5_dotdot_rejected(tmp_path):
    root = mk(tmp_path, [("요약", "S")])
    page(tmp_path, "outside.md", created="2026-11-01")  # a real concept page outside root
    expect_quiz_error(lambda: quiz.card(root, "../outside.md"), root)
    expect_quiz_error(lambda: quiz.card(root, "wiki/../../outside.md"), root)
    expect_quiz_error(lambda: quiz.card(root, "../x.md"), root)


def test_O5_absolute_rejected(tmp_path):
    root = mk(tmp_path, [("요약", "S")])
    outside = page(tmp_path / "other", "wiki/study/Z.md", created="2026-11-01")
    expect_quiz_error(lambda: quiz.card(root, "/abs.md"), root)
    expect_quiz_error(lambda: quiz.card(root, str(outside)), root)
    expect_quiz_error(lambda: quiz.card(root, str(root / P)), root)


def test_O5_outside_wiki_rejected(tmp_path):
    root = mk(tmp_path, [("요약", "S")])
    page(root, "notwiki/B.md", created="2026-11-01")
    page(root, "raw/C.md", created="2026-11-01")
    expect_quiz_error(lambda: quiz.card(root, "notwiki/B.md"), root)
    expect_quiz_error(lambda: quiz.card(root, "raw/C.md"), root)


@pytest.mark.parametrize("rel", ["wiki/index.md", "wiki/log.md", "wiki/journal/J.md", "wiki/study/Plain.md"])
def test_O5_non_concept_rejected(tmp_path, rel):
    root = mk(tmp_path, [("요약", "S")])
    page(root, "wiki/index.md", created="2026-11-01")
    page(root, "wiki/log.md", created="2026-11-01")
    page(root, "wiki/journal/J.md", type_="journal")
    bare_page(root, "wiki/study/Plain.md", "# Plain\n")
    expect_quiz_error(lambda: quiz.card(root, rel), root)


@pytest.mark.parametrize("rel", ["wiki/study/Missing.md", "wiki/study", "wiki/study/", "", "wiki/study/A.txt"])
def test_O5_missing_rejected(tmp_path, rel):
    root = mk(tmp_path, [("요약", "S")])
    write(root / "wiki" / "study" / "A.txt", "type: concept\n")
    expect_quiz_error(lambda: quiz.card(root, rel), root)


def test_O4_v3_mine_drops_blank_and_placeholder_lines_and_strips(tmp_path):
    root = mk(tmp_path, [("내가 정리한 것", "  첫 줄  \n\n(사용자가 말하거나 자료에서 온 내용)\n\t둘째 줄\n   \n셋째 줄 (괄호)")])
    assert quiz.card(root, P)["mine"] == "첫 줄\n둘째 줄\n셋째 줄 (괄호)"


def test_O4_v3_mine_only_placeholder_is_empty(tmp_path):
    root = mk(tmp_path, [("내가 정리한 것", "(사용자가 말하거나 자료에서 온 내용)")])
    assert quiz.card(root, P)["mine"] == ""


def test_O4_v3_summary_lines_are_stripped(tmp_path):
    root = mk(tmp_path, [("요약", "  가  \n\n  나")])
    assert quiz.card(root, P)["summary"] == "가 나"


def test_O4_v3_links_cap_is_card_only_quoted_frontmatter_page(tmp_path):
    root = tmp_path / "r"
    bare_page(root, "wiki/study/A.md",
              '---\ntype: "concept"\nlevel: \'3\'\ncreated: "2026-11-01"\n---\n# Q\n\n## 연결\n'
              + "\n".join(f"- [[T{i:02d}]]" for i in range(1, 13)) + "\n")
    c = quiz.card(root, P)
    assert c["level"] == 3 and c["title"] == "Q"
    assert c["links"] == [f"T{i:02d}" for i in range(1, 11)]


def test_O5_non_utf8_wiki_file_is_not_a_card(tmp_path):
    root = mk(tmp_path, [("요약", "S")])
    write(root / "wiki" / "study" / "Bad.md", b"---\ntype: concept\n---\n# Bad\n\xff\xfe\n")
    expect_quiz_error(lambda: quiz.card(root, "wiki/study/Bad.md"), root)
