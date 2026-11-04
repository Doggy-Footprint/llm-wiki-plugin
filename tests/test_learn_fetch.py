import json
import markitdown

import pytest

import learn
from learn_support import (
    D, DS, LONG_OUTLINE, MANIFEST_HEADER, MARKER, expect_error, http_server,  # noqa: F401
    long_doc, closed_port_url, make_root, read_manifest, run_main, sha, snapshot, write,
)

HTML = f"<html><body><h1>Title</h1><p>{MARKER}</p></body></html>".encode()
RAWDIR = "raw/2026/11/"


def src_file(tmp_path, name, data):
    return str(write(tmp_path / "src" / name, data))


def assert_only_under_raw_or_wiki(tmp_path, before):
    after = snapshot(tmp_path)
    for rel in set(after) - set(before):
        assert rel.startswith("root/raw") or rel.startswith("root/wiki"), rel


def test_O1_P1_html_file(tmp_path):
    root = make_root(tmp_path)
    src = src_file(tmp_path, "Page.HTML", HTML)
    before = snapshot(tmp_path)
    res = learn.fetch(src, D, "note", root)
    assert res["raw"] == RAWDIR + "2026-11-05-note.html"
    assert res["md"] == RAWDIR + "2026-11-05-note.md"
    assert res["duplicate_of"] is None
    assert res["outline"] is None
    assert (tmp_path / "src" / "Page.HTML").read_bytes() == HTML
    assert (root / res["raw"]).read_bytes() == HTML
    md = (root / res["md"]).read_text(encoding="utf-8")
    assert MARKER in md
    assert res["chars"] == len(md)
    header, rows = read_manifest(root)
    assert header == MANIFEST_HEADER
    assert len(rows) == 1
    r = rows[0]
    assert r["raw_path"] == res["raw"]
    assert r["original_name"] == "Page.HTML"
    assert r["sha256"] == sha(HTML)
    assert r["archived_at"] != ""
    assert r["extracted_to"] == ""
    assert_only_under_raw_or_wiki(tmp_path, before)


def test_O1_P2_md_file_raw_equals_md(tmp_path):
    root = make_root(tmp_path)
    data = "# 제목\n\n본문 한국어\n".encode("utf-8")
    src = src_file(tmp_path, "n.md", data)
    res = learn.fetch(src, D, "note", root)
    assert res["raw"] == res["md"] == RAWDIR + "2026-11-05-note.md"
    assert (root / res["raw"]).read_bytes() == data
    assert res["chars"] == len(data.decode("utf-8"))
    _, rows = read_manifest(root)
    assert len(rows) == 1 and rows[0]["sha256"] == sha(data)
    assert rows[0]["original_name"] == "n.md" and rows[0]["raw_path"] == res["raw"]
    assert (tmp_path / "src" / "n.md").read_bytes() == data


def test_O1_P3_url(tmp_path, http_server):
    root = make_root(tmp_path)
    before = snapshot(tmp_path)
    res = learn.fetch(http_server.url, D, "web", root)
    assert res["raw"] == res["md"] == RAWDIR + "2026-11-05-web.md"
    assert res["duplicate_of"] is None
    md_bytes = (root / res["md"]).read_bytes()
    assert http_server.marker in md_bytes.decode("utf-8")
    assert res["chars"] == len(md_bytes.decode("utf-8"))
    _, rows = read_manifest(root)
    assert len(rows) == 1
    assert rows[0]["original_name"] == http_server.url
    assert rows[0]["sha256"] == sha(md_bytes)
    assert rows[0]["raw_path"] == res["raw"]
    new_files = {k for k in set(snapshot(tmp_path)) - set(before) if snapshot(tmp_path)[k] is not None}
    assert new_files == {"root/" + res["md"]}


def test_O1_P4_duplicate_file(tmp_path):
    root = make_root(tmp_path)
    first = learn.fetch(src_file(tmp_path, "a.html", HTML), D, "first", root)
    other = src_file(tmp_path, "copy-of-a.html", HTML)
    before = snapshot(tmp_path)
    res = learn.fetch(other, D, "second", root)
    assert res["duplicate_of"] == first["raw"]
    assert res["raw"] == first["raw"]
    assert res["md"] == first["md"]
    assert res["chars"] == first["chars"]
    assert res["outline"] is None
    assert snapshot(tmp_path) == before


def test_O1_P4_duplicate_without_converted_md(tmp_path):
    data = b"%PDF-fake-bytes"
    raw = "raw/2026/11/2026-11-03-x.pdf"
    root = make_root(tmp_path, rows=[(raw, "x.pdf", sha(data), "2026-11-03T00:00:00", "")])
    src = src_file(tmp_path, "y.pdf", data)
    before = snapshot(tmp_path)
    res = learn.fetch(src, D, "again", root)
    assert res["duplicate_of"] == raw
    assert res["raw"] == raw
    assert res["md"] is None
    assert res["chars"] == 0
    assert res["outline"] is None
    assert snapshot(tmp_path) == before


def test_O1_P4_duplicate_long_doc_outline(tmp_path):
    root = make_root(tmp_path)
    data = long_doc(20001).encode()
    first = learn.fetch(src_file(tmp_path, "l.md", data), D, "long", root)
    src2 = src_file(tmp_path, "l2.md", data)
    before = snapshot(tmp_path)
    res = learn.fetch(src2, D, "long2", root)
    assert res["duplicate_of"] == first["raw"]
    assert res["chars"] == 20001
    assert res["outline"] == LONG_OUTLINE
    assert snapshot(tmp_path) == before


def test_O1_P5_duplicate_url(tmp_path, http_server):
    root = make_root(tmp_path)
    first = learn.fetch(http_server.url, D, "web", root)
    before = snapshot(tmp_path)
    res = learn.fetch(http_server.url, D, "another", root)
    assert res["duplicate_of"] == first["raw"]
    assert res["raw"] == first["raw"] and res["md"] == first["md"]
    assert res["chars"] == first["chars"]
    assert snapshot(tmp_path) == before


def test_O1_P6_name_collision_files(tmp_path):
    root = make_root(tmp_path)
    r1 = learn.fetch(src_file(tmp_path, "1.html", HTML), D, "note", root)
    r2 = learn.fetch(src_file(tmp_path, "2.html", HTML.replace(b"</body>", b"<p>two</p></body>")), D, "note", root)
    r3 = learn.fetch(src_file(tmp_path, "3.html", HTML.replace(b"</body>", b"<p>three</p></body>")), D, "note", root)
    assert r1["raw"] == RAWDIR + "2026-11-05-note.html"
    assert r2["raw"] == RAWDIR + "2026-11-05-note-2.html"
    assert r2["md"] == RAWDIR + "2026-11-05-note-2.md"
    assert r3["raw"] == RAWDIR + "2026-11-05-note-3.html"
    assert r3["md"] == RAWDIR + "2026-11-05-note-3.md"
    for r in (r1, r2, r3):
        assert (root / r["raw"]).exists() and (root / r["md"]).exists()
    assert (root / r1["raw"]).read_bytes() == HTML
    assert "two" in (root / r2["md"]).read_text(encoding="utf-8")
    _, rows = read_manifest(root)
    assert [r["raw_path"] for r in rows] == [r1["raw"], r2["raw"], r3["raw"]]


def test_O1_P6_collision_with_existing_md_target(tmp_path):
    root = make_root(tmp_path)
    r1 = learn.fetch(src_file(tmp_path, "a.md", b"# first\n"), D, "note", root)
    r2 = learn.fetch(src_file(tmp_path, "b.html", HTML), D, "note", root)
    assert r1["raw"] == RAWDIR + "2026-11-05-note.md"
    assert r2["raw"] == RAWDIR + "2026-11-05-note-2.html"
    assert r2["md"] == RAWDIR + "2026-11-05-note-2.md"
    assert (root / r1["raw"]).read_bytes() == b"# first\n"


def test_O1_P6_name_collision_urls(tmp_path, http_server):
    root = make_root(tmp_path)
    r1 = learn.fetch(http_server.url, D, "web", root)
    r2 = learn.fetch(http_server.url2, D, "web", root)
    assert r1["raw"] == RAWDIR + "2026-11-05-web.md"
    assert r2["raw"] == r2["md"] == RAWDIR + "2026-11-05-web-2.md"
    assert http_server.marker2 in (root / r2["md"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("a/b c", "a-b-c"),
        ("///", "item"),
        ("--x--", "x"),
        ("한글 노트", "한글-노트"),
        ("../../evil", "evil"),
        ("a  b", "a-b"),
        ("a_b.c", "a_b-c"),
        ("", "item"),
    ],
)
def test_O1_P7_slug(tmp_path, slug, expected):
    root = make_root(tmp_path)
    src = src_file(tmp_path, "s.md", b"# s\n")
    before = snapshot(tmp_path)
    res = learn.fetch(src, D, slug, root)
    assert res["raw"] == f"{RAWDIR}2026-11-05-{expected}.md"
    assert (root / res["raw"]).exists()
    assert_only_under_raw_or_wiki(tmp_path, before)


def test_O1_P8_missing_path(tmp_path):
    root = make_root(tmp_path)
    missing = str(tmp_path / "src" / "nope.md")
    msg = expect_error(2, lambda: learn.fetch(missing, D, "n", root), tmp_path, [missing])
    assert msg


@pytest.mark.parametrize("source", ["ftp://example.invalid/x", "notaurl-and-not-a-file"])
def test_O1_P9_scheme(tmp_path, source):
    root = make_root(tmp_path)
    expect_error(2, lambda: learn.fetch(source, D, "n", root), tmp_path, [source])


@pytest.mark.parametrize("name,data", [("empty.md", b""), ("empty.txt", b"")])
def test_O1_P10_empty_or_failed_conversion(tmp_path, name, data):
    root = make_root(tmp_path)
    src = src_file(tmp_path, name, data)
    expect_error(3, lambda: learn.fetch(src, D, "n", root), tmp_path, [src])


def test_O1_P11_http_404(tmp_path, http_server):
    root = make_root(tmp_path)
    expect_error(3, lambda: learn.fetch(http_server.url404, D, "n", root), tmp_path, [http_server.url404])


def test_O1_P11_connection_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    root = make_root(tmp_path)
    url = closed_port_url()
    expect_error(3, lambda: learn.fetch(url, D, "n", root), tmp_path, [url])


def test_O1_P12_manifest_absent_header_created(tmp_path):
    root = tmp_path / "root"
    (root / "wiki").mkdir(parents=True)
    res = learn.fetch(src_file(tmp_path, "n.md", b"# n\n"), D, "n", root)
    text = (root / "raw" / "MANIFEST.csv").read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(MANIFEST_HEADER)
    header, rows = read_manifest(root)
    assert header == MANIFEST_HEADER and len(rows) == 1
    assert rows[0]["raw_path"] == res["raw"]


def test_O1_P12_existing_manifest_rows_preserved(tmp_path):
    old = ("raw/2026/10/2026-10-01-old.md", "old.md", "0" * 64, "2026-10-01T00:00:00", "wiki/x.md")
    root = make_root(tmp_path, rows=[old])
    before = (root / "raw" / "MANIFEST.csv").read_bytes()
    learn.fetch(src_file(tmp_path, "n.md", b"# n\n"), D, "n", root)
    after = (root / "raw" / "MANIFEST.csv").read_bytes()
    assert after.startswith(before)
    _, rows = read_manifest(root)
    assert len(rows) == 2 and rows[0]["extracted_to"] == "wiki/x.md"


@pytest.mark.parametrize("n,outline", [(20000, None), (20001, LONG_OUTLINE)], ids=["B1_20000", "B2_20001"])
def test_O2_B1_B2_threshold(tmp_path, n, outline):
    root = make_root(tmp_path)
    res = learn.fetch(src_file(tmp_path, "l.md", long_doc(n).encode()), D, "long", root)
    assert res["chars"] == n
    assert res["outline"] == outline


def test_O2_B3_body_not_in_return_or_cli(tmp_path, capsys):
    root = make_root(tmp_path)
    src = src_file(tmp_path, "l.md", long_doc(20001).encode())
    res = learn.fetch(src, D, "long", root)
    dumped = json.dumps(res, ensure_ascii=False)
    assert MARKER not in dumped
    assert len(dumped) < 3000
    src2 = src_file(tmp_path, "l2.md", (long_doc(20001) + "y").encode())
    rc = run_main(
        learn.main,
        ["fetch", src2, "--date", DS, "--slug", "cli"],
        {"LLM_WIKI_ROOT": str(root)},
        tmp_path,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert MARKER not in out
    assert json.loads(out)["outline"] == LONG_OUTLINE


def test_O2_B3_short_doc_not_in_return(tmp_path):
    root = make_root(tmp_path)
    res = learn.fetch(src_file(tmp_path, "s.md", f"# t\n{MARKER}\n".encode()), D, "s", root)
    assert MARKER not in json.dumps(res, ensure_ascii=False)


@pytest.fixture
def convert_raises(monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(markitdown.MarkItDown, "convert", boom)


@pytest.mark.parametrize("manifest", [True, False], ids=["manifest_present", "manifest_absent"])
def test_O1_P13_convert_exception_local_html(tmp_path, convert_raises, manifest):
    if manifest:
        root = make_root(tmp_path)
    else:
        root = tmp_path / "root"
        (root / "wiki").mkdir(parents=True)
    src = src_file(tmp_path, "Page.html", HTML)
    expect_error(3, lambda: learn.fetch(src, D, "note", root), tmp_path, [src])
    assert manifest or not (root / "raw").exists()


@pytest.mark.parametrize("manifest", [True, False], ids=["manifest_present", "manifest_absent"])
def test_O1_P13_convert_exception_url(tmp_path, http_server, convert_raises, manifest):
    if manifest:
        root = make_root(tmp_path)
    else:
        root = tmp_path / "root"
        (root / "wiki").mkdir(parents=True)
    expect_error(3, lambda: learn.fetch(http_server.url, D, "web", root), tmp_path, [http_server.url])
    assert manifest or not (root / "raw").exists()


def test_O1_single_digit_month_directory(tmp_path):
    import datetime

    root = make_root(tmp_path)
    res = learn.fetch(src_file(tmp_path, "m.md", b"# m\n"), datetime.date(2026, 3, 5), "note", root)
    assert res["raw"] == "raw/2026/03/2026-03-05-note.md"
    assert (root / res["raw"]).exists()


def test_O2_B4_korean_20000_chars_bytes_exceed(tmp_path):
    root = make_root(tmp_path)
    data = ("가" * 20000).encode("utf-8")
    assert len(data) > 20000
    res = learn.fetch(src_file(tmp_path, "k.md", data), D, "kr", root)
    assert res["chars"] == 20000
    assert res["outline"] is None
