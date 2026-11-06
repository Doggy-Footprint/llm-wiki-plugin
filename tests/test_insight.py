import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

import insight

SKILL = Path(__file__).resolve().parent.parent / "skills" / "wiki-insight"
D1 = datetime.date(2026, 11, 7)
D2 = datetime.date(2026, 11, 8)
TITLE = "아침 커피와 집중"
PAGE = f"wiki/life/insights/{TITLE}.md"
INDEX = """# Index

## 공부 (study/)

## 생활 깨달음 (life/insights/)

## 커리어 깨달음 (career/insights/)

## 지난 생각
`status: obsolete`인 깨달음.
"""


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "wiki-root"
    (r / "wiki").mkdir(parents=True)
    (r / "wiki" / "index.md").write_text(INDEX, encoding="utf-8")
    (r / "chat" / "inbox").mkdir(parents=True)
    return r


def result(root, title=TITLE, date=D1, **kw):
    kw.setdefault("said", "아침에 커피 마시면 오전엔 집중이 잘 되더라")
    return Path(insight.make_result(title, date, out_dir=root / "chat" / "inbox", **kw)["path"])


def read(root, rel=PAGE):
    return (root / rel).read_text(encoding="utf-8")


def new_page(root):
    return insight.import_result(result(root, area="life", now="아침 커피가 오전 집중을 돕는 것 같다.",
                                        links=["[[카페인]] — 원인 후보"]), root)


def test_new_page_from_builtin_template_index_log(root):
    out = new_page(root)
    assert out == {"page": PAGE, "created": True, "changes": ["새 페이지 (life, hunch)"], "changed": True}
    text = read(root)
    meta = insight._parse_fm(text)
    assert meta["type"] == "insight" and meta["status"] == "active" and meta["confidence"] == "hunch"
    assert meta["created"] == meta["updated"] == "2026-11-07"
    assert "제목은 결론이 아니라" not in text and "{{" not in text
    assert "## 지금 생각\n\n아침 커피가 오전 집중을 돕는 것 같다.\n\n## 생각의 변화" in text
    assert "- 2026-11-07: 아침에 커피 마시면 오전엔 집중이 잘 되더라 (claude.ai 채팅)\n" in text
    assert "## 근거\n\n## 보충 (LLM)\n\n## 연결\n\n- [[카페인]] — 원인 후보\n\n## 출처\n\n- claude.ai 채팅 2026-11-07\n" in text
    idx = read(root, "wiki/index.md")
    assert f"## 생활 깨달음 (life/insights/)\n- [[{TITLE}]] — 아침 커피가 오전 집중을 돕는 것 같다.\n\n## 커리어" in idx
    assert read(root, "wiki/log.md").endswith(f"- 2026-11-07 [insight] {TITLE}: 새 페이지 (life, hunch)\n")


def test_update_rewrites_now_appends_change_and_is_idempotent(root):
    new_page(root)
    f = result(root, date=D2, said="잠을 잘 잔 날이 집중이 잘 되는 거였어", now="집중은 전날 수면에 더 좌우된다.",
               confidence="likely", supplement="수면과 카페인은 교란 변수일 수 있다.",
               links=["[[카페인]] — 원인 후보", "[[수면]] — 원인 후보"])
    copy = root / "again.insight.md"
    copy.write_bytes(f.read_bytes())
    out = insight.import_result(f, root)
    assert out["created"] is False
    assert out["changes"] == ["지금 생각 바뀜", "confidence hunch→likely", "생각 추가", "보충", "연결"]
    text = read(root)
    assert "## 지금 생각\n\n집중은 전날 수면에 더 좌우된다.\n\n" in text
    assert "(claude.ai 채팅)\n- 2026-11-08: 잠을 잘 잔 날이 집중이 잘 되는 거였어 (claude.ai 채팅)\n" in text
    assert "## 보충 (LLM)\n\n수면과 카페인은 교란 변수일 수 있다.\n\n## 연결" in text
    assert text.count("[[카페인]]") == 1 and "- [[수면]] — 원인 후보" in text
    assert "- claude.ai 채팅 2026-11-07\n- claude.ai 채팅 2026-11-08\n" in text
    assert insight._parse_fm(text)["updated"] == "2026-11-08"
    assert f"- [[{TITLE}]] — 집중은 전날 수면에 더 좌우된다.\n" in read(root, "wiki/index.md")
    before = {p: (root / p).read_bytes() for p in (PAGE, "wiki/index.md", "wiki/log.md")}
    assert insight.import_result(copy, root) == {"page": PAGE, "created": False, "changes": [], "changed": False}
    assert {p: (root / p).read_bytes() for p in before} == before


def test_update_same_now_only_appends(root):
    new_page(root)
    out = insight.import_result(result(root, date=D2, said="역시 그렇더라", now="아침 커피가 오전 집중을 돕는 것 같다."), root)
    assert out["changes"] == ["생각 추가"]
    assert insight._parse_fm(read(root))["confidence"] == "hunch"


def test_update_supplement_appends_after_existing(root):
    new_page(root)
    insight.import_result(result(root, date=D2, said="a", supplement="첫 보충"), root)
    insight.import_result(result(root, date=D2, said="b", supplement="둘째 보충"), root)
    assert "## 보충 (LLM)\n\n첫 보충\n\n둘째 보충\n\n## 연결" in read(root)


def test_update_restores_missing_sections_in_order(root):
    p = root / "wiki" / "career" / "insights" / "회의 길이.md"
    p.parent.mkdir(parents=True)
    p.write_text("---\ntype: insight\nconfidence: hunch\n---\n# 회의 길이\n\n## 출처\n\n- journal/x.md\n", encoding="utf-8")
    insight.import_result(result(root, title="회의 길이", said="짧은 회의가 낫더라", now="짧은 회의가 낫다.",
                                 links=["[[집중]] — 관련"]), root)
    text = p.read_text(encoding="utf-8")
    assert text.index("## 지금 생각") < text.index("## 생각의 변화") < text.index("## 연결") < text.index("## 출처")
    assert "- journal/x.md\n- claude.ai 채팅 2026-11-07\n" in text
    assert "- [[회의 길이]]" not in read(root, "wiki/index.md")


def test_new_page_uses_root_template_and_creates_index_and_log(tmp_path):
    root = tmp_path / "r"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "insight.md").write_text("# {{title}}\n\n## 지금 생각\n(x)\n", encoding="utf-8")
    insight.import_result(result_in(tmp_path, area="career", now="회고는 짧게."), root)
    text = (root / "wiki" / "career" / "insights" / f"{TITLE}.md").read_text(encoding="utf-8")
    assert text.startswith("---\ntype: insight\nstatus: active\nconfidence: hunch\ncreated: 2026-11-07\nupdated: 2026-11-07\n---\n")
    assert "## 지금 생각\n\n회고는 짧게.\n\n## 생각의 변화" in text and "## 출처\n\n- claude.ai 채팅 2026-11-07\n" in text
    assert (root / "wiki" / "index.md").read_text(encoding="utf-8") == (
        f"# Index\n\n## 커리어 깨달음 (career/insights/)\n- [[{TITLE}]] — 회고는 짧게.\n")
    assert (root / "wiki" / "log.md").read_text(encoding="utf-8").startswith("# Log\n")


def result_in(tmp_path, **kw):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return Path(insight.make_result(TITLE, D1, "말", out, **kw)["path"])


def test_index_heading_added_before_old_section(root):
    (root / "wiki" / "index.md").write_text("# Index\n\n## 지난 생각\n- old\n", encoding="utf-8")
    new_page(root)
    assert read(root, "wiki/index.md") == f"# Index\n\n## 생활 깨달음 (life/insights/)\n- [[{TITLE}]] — 아침 커피가 오전 집중을 돕는 것 같다.\n\n## 지난 생각\n- old\n"


def test_existing_index_line_is_kept_for_new_page(root):
    (root / "wiki" / "index.md").write_text(f"# Index\n- [[{TITLE}]] — 예전 요약\n", encoding="utf-8")
    new_page(root)
    assert read(root, "wiki/index.md") == f"# Index\n- [[{TITLE}]] — 예전 요약\n"


@pytest.mark.parametrize("kw,msg", [({}, "area"), ({"area": "life"}, "now")])
def test_new_page_needs_area_and_now(root, kw, msg):
    with pytest.raises(insight.InsightError, match=msg):
        insight.import_result(result(root, **kw), root)


def test_rejects_obsolete_non_insight_and_duplicate_pages(root):
    p = root / "wiki" / "life" / "insights" / f"{TITLE}.md"
    p.parent.mkdir(parents=True)
    p.write_text("---\ntype: insight\nstatus: obsolete\n---\n# x\n", encoding="utf-8")
    with pytest.raises(insight.InsightError, match="obsolete"):
        insight.import_result(result(root), root)
    p.write_text("---\ntype: concept\n---\n# x\n", encoding="utf-8")
    with pytest.raises(insight.InsightError, match="insight가 아닌"):
        insight.import_result(result(root), root)
    (root / "wiki" / "study").mkdir()
    (root / "wiki" / "study" / f"{TITLE}.md").write_text("x", encoding="utf-8")
    with pytest.raises(insight.InsightError, match="둘 이상"):
        insight.import_result(result(root), root)


@pytest.mark.parametrize("text,msg", [
    ("---\ntype: learn-result\n---\n", "type"),
    ("---\ntype: insight-result\nversion: 2\n---\n", "version"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 2026-11-07\n---\n", "said"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 2026-11-07\nsaid: s\narea: home\n---\n", "area"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 2026-11-07\nsaid: s\nconfidence: tested\n---\n", "confidence"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 2026-11-07\nsaid: s\nnow: [a, b]\n---\n", "now"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 11/07\nsaid: s\n---\n", "날짜"),
    ("---\ntype: insight-result\nversion: 1\ntitle: a/b\ndate: 2026-11-07\nsaid: s\n---\n", "제목"),
    ("---\ntype: insight-result\nversion: 1\ntitle: [[a]]\ndate: 2026-11-07\nsaid: s\n---\n", "제목"),
    ("---\ntype: insight-result\nversion: 1\ntitle: t\ndate: 2026-11-07\nsaid: s\n---\n\n## 연결\n관계 없음\n", "연결"),
    ("no frontmatter", "type"),
    ("---\nunterminated", "type"),
])
def test_parse_result_rejects(text, msg):
    with pytest.raises(insight.InsightError, match=msg):
        insight.parse_result(text)


def test_parse_result_hand_written_crlf_and_extra_sections():
    text = ("---\r\ntype: insight-result\r\nversion: 1\r\ntitle: '질문'\r\ndate: 2026-11-07\r\n# c\r\n said: x\r\n"
            "said: 말  두칸\r\n---\r\n\r\n## 기타\r\n무시\r\n## 연결\r\n- [[a]] — b\r\n")
    r = insight.parse_result(text)
    assert r["title"] == "질문" and r["said"] == "말 두칸" and r["links"] == ["- [[a]] — b"]
    assert r["area"] is r["confidence"] is r["now"] is None and r["supplement"] == []


def test_make_result_format_names_and_errors(tmp_path):
    p = Path(insight.make_result(TITLE, D1, "말\n둘", tmp_path, area="life", now="생각", confidence="likely",
                                 supplement="\n보충\n\n", links=["[[a]] — b", "- [[c]] — d"])["path"])
    assert p.name == "2026-11-07-아침-커피와-집중.insight.md"
    assert p.read_text(encoding="utf-8") == (
        "---\ntype: insight-result\nversion: 1\ntitle: 아침 커피와 집중\ndate: 2026-11-07\narea: life\n"
        "confidence: likely\nnow: 생각\nsaid: 말 둘\n---\n\n## 보충 (LLM)\n보충\n\n## 연결\n- [[a]] — b\n- [[c]] — d\n")
    assert Path(insight.make_result(TITLE, D1, "x", tmp_path)["path"]).name.endswith("집중-2.insight.md")
    with pytest.raises(insight.InsightError, match="출력 폴더"):
        insight.make_result(TITLE, D1, "x", tmp_path / "none")
    with pytest.raises(insight.InsightError, match="said"):
        insight.make_result(TITLE, D1, "  ", tmp_path)


def test_sync_imports_deletes_keeps_failures_and_writes_deck(root):
    result(root, area="life", now="커피가 돕는다.")
    (root / "chat" / "inbox" / "bad.insight.md").write_text("x", encoding="utf-8")
    (root / "chat" / "inbox" / "other.quiz.md").write_text("q", encoding="utf-8")
    (root / "chat" / "inbox" / ".gitkeep").write_bytes(b"")
    obs = root / "wiki" / "life" / "insights" / "옛 생각.md"
    obs.parent.mkdir(parents=True)
    obs.write_text("---\ntype: insight\nstatus: obsolete\n---\n# 옛 생각\n", encoding="utf-8")
    (root / "wiki" / "life" / "insights" / "깨진.md").write_bytes(b"\xff")
    (root / "wiki" / "tops.md").write_text("---\ntype: insight\n---\n# tops\n", encoding="utf-8")
    out = insight.sync(root, D2)
    assert out["insight"] == [PAGE] and out["deck"] == "chat/insights.md"
    assert [f["file"] for f in out["failed"]] == ["chat/inbox/bad.insight.md"]
    assert sorted(p.name for p in (root / "chat" / "inbox").iterdir()) == [".gitkeep", "bad.insight.md", "other.quiz.md"]
    assert read(root, "chat/insights.md") == (
        "---\ntype: insight-deck\nversion: 1\ngenerated: 2026-11-08\n---\n# Insights\n\n"
        f"## life (1)\n- [[{TITLE}]] — hunch, 2026-11-07: 커피가 돕는다.\n\n## career (0)\n\n"
        "## other (1)\n- [[tops]] — -, -: -\n")


def test_sync_and_deck_without_inbox_or_wiki(tmp_path):
    assert insight.sync(tmp_path, D1) == {"insight": [], "failed": [], "deck": "chat/insights.md"}
    assert insight.deck(tmp_path, D1)["count"] == 0


def test_write_all_rolls_back(tmp_path, monkeypatch):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_bytes(b"old")
    real = Path.write_bytes

    def boom(self, data):
        if self == b:
            raise OSError("disk")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", boom)
    with pytest.raises(OSError):
        insight._write_all([(a, b"new"), (tmp_path / "c.md", b"c"), (b, b"b")])
    assert a.read_bytes() == b"old" and not (tmp_path / "c.md").exists()


def test_parse_date():
    assert insight.parse_date("today", datetime.datetime(2026, 11, 8, 4)) == D1
    assert insight.parse_date("yesterday", datetime.datetime(2026, 11, 8, 6)) == D1
    assert insight.parse_date("2026-11-07") == D1


def test_cli_result_import_sync_deck(root, tmp_path, capsys):
    env = {}
    assert insight.main(["result", TITLE, "--said", "말", "--area", "life", "--now", "생각", "--out", "chat/inbox",
                         "--link", "[[a]] — b", "--date", "2026-11-07"], env, root) == 0
    path = json.loads(capsys.readouterr().out)["path"]
    assert insight.main(["--root", str(root), "import", path], env, tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["created"] is True
    assert insight.main(["import", "missing.insight.md"], {"LLM_WIKI_ROOT": str(root)}, root) == 2
    assert "import 파일이 없음" in capsys.readouterr().err
    (root / "chat" / "inbox" / "bad.insight.md").write_text("x", encoding="utf-8")
    assert insight.main(["sync", "--date", "2026-11-08"], {"LLM_WIKI_ROOT": "wiki-root"}, root.parent) == 1
    assert json.loads(capsys.readouterr().out)["failed"]
    (root / ".git").mkdir()
    assert insight.main(["deck"], env, root / "wiki") == 0
    assert json.loads(capsys.readouterr().out) == {"path": "chat/insights.md", "count": 1}
    assert insight.main(["deck", "--date", "11/08"], env, root) == 2
    assert insight.main(["--help"], env, root) == 0


def test_script_runs_standalone_without_repo(tmp_path):
    r = subprocess.run([sys.executable, "-I", str(SKILL / "insight.py"), "result", TITLE, "--said", "말",
                        "--out", str(tmp_path), "--date", "2026-11-07"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert Path(json.loads(r.stdout)["path"]).is_file()


def test_builtin_template_equals_wiki_template():
    repo_template = SKILL.parents[3] / "templates" / "insight.md"
    if not repo_template.is_file():
        pytest.skip("공개 저장소에는 위키 templates/가 없다")
    assert (SKILL / "insight.md").read_bytes() == repo_template.read_bytes()
