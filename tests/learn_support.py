"""Expected values come from the spec only, never from the implementation."""
from __future__ import annotations

import csv
import datetime
import hashlib
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = PLUGIN_ROOT / "skills" / "wiki-add"
D = datetime.date(2026, 11, 5)
DS = "2026-11-05"
MARKER = "UNIQUE-MARKER-7f3a9c"
MANIFEST_HEADER = ["raw_path", "original_name", "sha256", "archived_at", "extracted_to"]
SOLO = {0: "전구조적", 1: "단일구조적", 2: "다중구조적", 3: "관계적", 4: "확장추상적"}

INDEX = (
    "# Index\n\n머리말\n\n"
    "## 개념 (concepts/)\n- [[Old]] — old\n\n"
    "## 공부 (study/)\n- [[Existing]] — exist\n- [[Existing2]] — exist two\n\n\n"
    "## 일기 (journal/)\n- [[J]] — j\n"
)
LOG = "# Log\n\n- 2026-11-01 [daily] 기존 로그\n"

TEMPLATE = """---
type: concept
created: {{date}}
updated: {{date}}
level:
tags: [review]
sources: []
---
# {{title}}

## 요약
(한두 문장)

## 내가 정리한 것
(사용자가 말하거나 자료에서 온 내용)

## 보충 (LLM)
(LLM 지식으로 덧붙인 내용 — 위와 구분한다. 이해 수준에 맞춰 쓴다)

## 이해 기록

## 오해와 교정

## 연결
- [[관련 개념]] — 어떤 관계인지

## 출처
- journal/YYYY/YYYY-MM-DD.md, raw/... 등
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, content) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def snapshot(base: Path) -> dict:
    return {
        p.relative_to(base).as_posix(): (None if p.is_dir() else p.read_bytes())
        for p in sorted(base.rglob("*"))
    }


def manifest_text(rows=()) -> str:
    out = [",".join(MANIFEST_HEADER)]
    for r in rows:
        out.append(",".join(r))
    return "\n".join(out) + "\n"


def make_root(tmp_path: Path, name="root", index=INDEX, log=LOG, rows=()) -> Path:
    root = tmp_path / name
    write(root / "wiki" / "index.md", index)
    write(root / "wiki" / "log.md", log)
    write(root / "raw" / "MANIFEST.csv", manifest_text(rows))
    return root


def read_manifest(root: Path):
    with open(root / "raw" / "MANIFEST.csv", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        return rdr.fieldnames, rows


def fm_lines(text: str) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    assert lines[0] == "---"
    end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    return lines[1:end]


def fm_parse(text: str) -> dict:
    meta, last = {}, None
    for line in fm_lines(text):
        s = line.strip()
        if not s:
            continue
        if s.startswith("- ") and last is not None:
            if not isinstance(meta[last], list):
                meta[last] = []
            meta[last].append(s[2:].strip())
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = v
        last = k.strip()
    return meta


def has_section(text: str, heading: str) -> bool:
    return any(ln == f"## {heading}" for ln in text.replace("\r\n", "\n").split("\n"))


def section_lines(text: str, heading: str) -> list:
    out, inside = [], False
    for ln in text.replace("\r\n", "\n").split("\n"):
        if ln.startswith("## "):
            if inside:
                break
            inside = ln[3:].strip() == heading
            continue
        if inside and ln.strip():
            out.append(ln.rstrip())
    return out


def strip_added(text: str, added) -> str:
    lines = text.split("\n")
    for a in added:
        lines.remove(a)
    return "\n".join(lines)


def collapse(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def ev_line(level: int, ev: str, date: str = DS) -> str:
    return f"- {date} L{level} {SOLO[level]}: {ev}"


def run_main(main, argv, environ=None, cwd=None) -> int:
    try:
        rc = main(argv, environ if environ is not None else {}, cwd)
    except SystemExit as e:
        rc = e.code
    return 0 if rc is None else rc


def expect_error(code, fn, base: Path, contains=()):
    import learn

    before = snapshot(base)
    with pytest.raises(learn.LearnError) as ei:
        fn()
    assert ei.value.code == code
    msg = str(ei.value)
    for c in contains:
        assert c in msg, (c, msg)
    assert snapshot(base) == before
    return msg


class PageServer:
    def __init__(self, base):
        self.base = base
        self.marker = "HTTP-MARKER-5d2e81"
        self.url = base + "/page.html"
        self.url2 = base + "/other.html"
        self.marker2 = "HTTP-MARKER-OTHER-91bc"
        self.url404 = base + "/missing.html"


@pytest.fixture
def http_server(monkeypatch):
    marker, marker2 = "HTTP-MARKER-5d2e81", "HTTP-MARKER-OTHER-91bc"
    pages = {
        "/page.html": f"<html><body><h1>Served</h1><p>{marker}</p></body></html>",
        "/other.html": f"<html><body><h1>Other</h1><p>{marker2}</p></body></html>",
    }

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path)
            if body is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    ps = PageServer(f"http://127.0.0.1:{srv.server_address[1]}")
    try:
        yield ps
    finally:
        srv.shutdown()
        srv.server_close()


def closed_port_url() -> str:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/x.html"


def long_doc(n: int) -> str:
    base = (
        "# Top\n\nintro text\n## Second  \n\n#hash\nplain\n### Third\n"
        f"{MARKER}\n"
    )
    return base + "x" * (n - len(base))


LONG_OUTLINE = [
    {"line": 1, "heading": "# Top"},
    {"line": 4, "heading": "## Second"},
    {"line": 6, "heading": "#hash"},
    {"line": 8, "heading": "### Third"},
]


def result_text(**over) -> str:
    """A learn-result file; pass key=None to drop a key."""
    kv = {
        "type": "learn-result",
        "version": "1",
        "title": "Imported",
        "date": DS,
        "level": "2",
        "summary": "결과 요약",
        "evidence": "결과 근거",
    }
    body = over.pop("body", None)
    for k, v in over.items():
        kv[k] = v
    lines = ["---"] + [f"{k}: {v}" for k, v in kv.items() if v is not None] + ["---"]
    if body is None:
        body = "## 내가 정리한 것\n내 정리 한 줄\n\n## 보충 (LLM)\n보충 한 줄\n\n## 연결\n- [[링크A]] — 관계A\n"
    return "\n".join(lines) + "\n" + body
