# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""표준 라이브러리만 쓴다. claude.ai 코드 실행에는 goal.py와 이 파일 두 개만 내려받으므로 다른 모듈을 import하지 않는다."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shlex
import sqlite3
import struct
import subprocess
import sys
import tomllib
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
from typing import Protocol

EMBED_URL = "https://api.openai.com/v1/embeddings"
TEXT_LIMIT = 8000
BATCH = 64
TOP = 50
RRF_K = 60
SKIP_PAGES = {"wiki/index.md", "wiki/log.md"}
TOKEN_RE = re.compile(r"[0-9a-z_]+|[가-힣]+")
HANGUL_RE = re.compile(r"[가-힣]+")


class IndexToolError(Exception):
    pass


def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def frontmatter(path: Path) -> dict:
    """`key: value`, `key: [a, b]`, 블록 리스트(`- a`)만 지원한다. 중첩 YAML은 읽지 못한다."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict = {}
    last_key = None
    for line in text[4:end].splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") and last_key is not None:
            if not isinstance(meta[last_key], list):
                meta[last_key] = []
            meta[last_key].append(_scalar(s[2:]))
            continue
        if ":" not in line or line[0].isspace():
            continue
        k, v = line.split(":", 1)
        v = v.split(" #", 1)[0].strip()
        if v.startswith("[") and not v.startswith("[[") and v.endswith("]"):
            meta[k.strip()] = [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = _scalar(v)
        last_key = k.strip()
    return meta


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def resolve_root(root_arg: str | None, environ: Mapping[str, str], cwd: Path) -> Path:
    cwd = Path(cwd)
    if root_arg:
        root = Path(root_arg)
    elif environ.get("LLM_WIKI_ROOT"):
        root = Path(environ["LLM_WIKI_ROOT"])
    else:
        top = next((d for d in [cwd, *cwd.parents] if (d / ".git").exists()), None)
        return Path(os.path.abspath(top or cwd))
    return Path(os.path.abspath(root if root.is_absolute() else cwd / root))


class Embedder(Protocol):
    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, model: str, dim: int, api_key: str):
        self.model = model
        self.dim = dim
        self._api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts, "dimensions": self.dim}).encode("utf-8")
        req = urllib.request.Request(
            EMBED_URL,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        # 오류 메시지에는 상태 코드·사유만 쓴다(요청 헤더의 키가 새지 않게).
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            try:
                raw = resp.read()
            finally:
                close = getattr(resp, "close", None)
                if close:
                    close()
        except urllib.error.HTTPError as e:
            raise IndexToolError(f"OpenAI HTTP error {e.code} {e.reason}") from None
        except OSError as e:
            reason = getattr(e, "reason", None) or type(e).__name__
            raise IndexToolError(f"OpenAI network error: {reason}") from None
        try:
            data = json.loads(raw)["data"]
            return [item["embedding"] for item in data]
        except (ValueError, KeyError, TypeError):
            raise IndexToolError("OpenAI response malformed") from None


def api_key(root: Path, environ: Mapping[str, str]) -> str | None:
    value = environ.get("OPENAI_API_KEY")
    if value:
        return value
    env = Path(root) / ".env"
    if not env.is_file():
        return None
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("OPENAI_API_KEY="):
            continue
        v = line.split("=", 1)[1].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].strip()
        if v:
            return v
    return None


def embedding_config(root: Path) -> dict:
    cfg = {"model": "text-embedding-3-small", "dim": 768, "min_free_mb": 0}
    path = Path(root) / "config.toml"
    if not path.is_file():
        return cfg
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8")).get("embedding", {})
    except tomllib.TOMLDecodeError as e:
        raise IndexToolError(f"config.toml: {e}") from None
    if isinstance(table, dict):
        for key in cfg:
            if key in table:
                cfg[key] = table[key]
    return cfg


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for word in TOKEN_RE.findall(unicodedata.normalize("NFKC", text).lower()):
        if HANGUL_RE.fullmatch(word) and len(word) >= 2:
            # trigram은 2글자 개념어("조인")를 찾지 못해 bigram을 쓴다.
            out.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            out.append(word)
    return out


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v:
        return [v]
    return []


def _split_body(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    nl = text.find("\n", end + 1)
    return "" if nl == -1 else text[nl + 1 :]


def load_pages(root: Path) -> tuple[list[dict], list[str]]:
    root = Path(root)
    pages: list[dict] = []
    warnings: list[str] = []
    wiki = root / "wiki"
    if not wiki.is_dir():
        return pages, warnings
    entries = sorted(((p.relative_to(root).as_posix(), p) for p in wiki.rglob("*.md") if p.is_file()))
    for rel, p in entries:
        if rel in SKIP_PAGES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            warnings.append(f"{rel}: not utf-8")
            continue
        meta = frontmatter(p)
        body = _split_body(text)
        title = p.stem
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        aliases = _as_list(meta.get("aliases"))
        tags = _as_list(meta.get("tags"))
        ptype = meta.get("type")
        lv = meta.get("level")
        level = int(lv) if isinstance(lv, str) and re.fullmatch(r"[0-4]", lv) else None
        full = (title + "\n" + ", ".join(aliases) + "\n" + ", ".join(tags) + "\n" + body)[:TEXT_LIMIT]
        pages.append(
            {
                "path": rel,
                "title": title,
                "aliases": aliases,
                "tags": tags,
                "type": ptype if isinstance(ptype, str) else "",
                "level": level,
                "body": body,
                "text": full,
                "text_hash": hashlib.sha256(full.encode("utf-8")).hexdigest(),
            }
        )
    return pages, warnings


def _connect(root: Path) -> sqlite3.Connection:
    cache = Path(root) / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cache / "wiki-index.sqlite", isolation_level=None)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vectors(path TEXT PRIMARY KEY, model TEXT NOT NULL,"
        " dim INTEGER NOT NULL, text_hash TEXT NOT NULL, vec BLOB NOT NULL)"
    )
    return conn


def _build(conn: sqlite3.Connection, pages: list[dict]) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute("DROP TABLE IF EXISTS fts")
        conn.execute("DROP TABLE IF EXISTS pages")
        conn.execute("CREATE TABLE pages(id INTEGER PRIMARY KEY, path TEXT NOT NULL)")
        conn.execute("CREATE VIRTUAL TABLE fts USING fts5(title, aliases, tags, body, tokenize='unicode61')")
        conn.executemany("INSERT INTO pages(id, path) VALUES (?, ?)", [(i, p["path"]) for i, p in enumerate(pages)])
        conn.executemany(
            "INSERT INTO fts(rowid, title, aliases, tags, body) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    i,
                    " ".join(tokenize(p["title"])),
                    " ".join(tokenize(" ".join(p["aliases"]))),
                    " ".join(tokenize(" ".join(p["tags"]))),
                    " ".join(tokenize(p["body"])),
                )
                for i, p in enumerate(pages)
            ],
        )
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def build(root: Path) -> dict:
    pages, warnings = load_pages(root)
    with closing(_connect(root)) as conn:
        _build(conn, pages)
    return {"pages": len(pages), "warnings": warnings}


def free_memory_mb() -> float | None:
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10, check=True).stdout
        size = re.search(r"page size of (\d+) bytes", out)
        counts = [re.search(rf"Pages {name}:\s+(\d+)", out) for name in ("free", "inactive", "speculative")]
        if not size or not all(counts):
            return None
        return (sum(int(c.group(1)) for c in counts) * int(size.group(1))) / 1048576
    except (OSError, subprocess.SubprocessError):
        return None


def _ts() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _log(root: Path, name: str, record: dict) -> None:
    cache = Path(root) / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    with open(cache / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_embed_error(root: Path, message: str) -> None:
    _log(root, "embed-log.jsonl", {"ts": _ts(), "error": message})


def _call_embedder(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    try:
        return embedder.embed(texts)
    except IndexToolError:
        raise
    except Exception as e:  # 메시지에 키가 섞일 수 있어 타입 이름만 남긴다.
        raise IndexToolError(f"embedder failed: {type(e).__name__}") from None


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _embed(root: Path, embedder: Embedder, min_free_mb: float, free_mb) -> dict:
    model, dim = embedder.model, embedder.dim
    free = None
    if min_free_mb > 0:
        free = (free_mb or free_memory_mb)()
        if free is not None and free < min_free_mb:
            return {"embedded": 0, "unchanged": 0, "removed": 0, "skipped": "memory", "model": model, "dim": dim, "free_mb": free}
    pages, _ = load_pages(root)
    with closing(_connect(root)) as conn:
        conn.execute("BEGIN")
        try:
            rows = conn.execute("SELECT path, model, dim, text_hash FROM vectors").fetchall()
            current = {p["path"] for p in pages}
            stale = [r[0] for r in rows if r[0] not in current or r[1] != model or r[2] != dim]
            conn.executemany("DELETE FROM vectors WHERE path = ?", [(x,) for x in stale])
            have = {r[0]: r[3] for r in rows if r[0] in current and r[1] == model and r[2] == dim}
            todo = [p for p in pages if have.get(p["path"]) != p["text_hash"]]
            for i in range(0, len(todo), BATCH):
                batch = todo[i : i + BATCH]
                vectors = _call_embedder(embedder, [p["text"] for p in batch])
                if len(vectors) != len(batch):
                    raise IndexToolError(f"embedder returned {len(vectors)} vectors for {len(batch)} texts")
                if any(len(v) != dim for v in vectors):
                    raise IndexToolError(f"embedder returned vectors of wrong length (expected {dim})")
                conn.executemany(
                    "INSERT OR REPLACE INTO vectors(path, model, dim, text_hash, vec) VALUES (?, ?, ?, ?, ?)",
                    [(p["path"], model, dim, p["text_hash"], _pack(v)) for p, v in zip(batch, vectors)],
                )
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    return {
        "embedded": len(todo),
        "unchanged": len(pages) - len(todo),
        "removed": len(stale),
        "skipped": None,
        "model": model,
        "dim": dim,
        "free_mb": free,
    }


def embed(
    root: Path,
    embedder: Embedder,
    min_free_mb: float = 0,
    free_mb: Callable[[], float | None] | None = None,
) -> dict:
    try:
        result = _embed(Path(root), embedder, min_free_mb, free_mb)
    except IndexToolError as e:
        log_embed_error(root, str(e))
        raise
    _log(root, "embed-log.jsonl", {"ts": _ts(), **result})
    return result


def _fts_query(query: str) -> str | None:
    tokens = list(dict.fromkeys(tokenize(query)))
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else None


def _cosine(a: list[float], b: list[float], na: float) -> float:
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def search(root: Path, query: str, k: int = 10, embedder: Embedder | None = None, source: str = "search") -> dict:
    root = Path(root)
    if not query.strip():
        raise IndexToolError("empty query")
    pages, warnings = load_pages(root)
    titles = {p["path"]: p["title"] for p in pages}
    hashes = {p["path"]: p["text_hash"] for p in pages}
    if embedder is not None:
        model, dim = embedder.model, embedder.dim
    else:
        cfg = embedding_config(root)
        model, dim = cfg["model"], cfg["dim"]

    keyword: list[str] = []
    with closing(_connect(root)) as conn:
        _build(conn, pages)
        match = _fts_query(query)
        if match:
            keyword = [
                r[0]
                for r in conn.execute(
                    "SELECT p.path FROM fts JOIN pages p ON p.id = fts.rowid WHERE fts MATCH ?"
                    " ORDER BY bm25(fts, 10.0, 8.0, 4.0, 1.0), p.path LIMIT ?",
                    (match, TOP),
                )
            ]
        stored = conn.execute("SELECT path, model, dim, text_hash, vec FROM vectors").fetchall()
    usable = {r[0]: r[4] for r in stored if r[1] == model and r[2] == dim and hashes.get(r[0]) == r[3]}
    stale_vectors = sum(1 for path in hashes if path not in usable)

    vector: list[str] = []
    mode = "keyword"
    if embedder is not None:
        try:
            qvs = embedder.embed([query])
            if len(qvs) != 1 or len(qvs[0]) != dim:
                raise ValueError("malformed query vector")
            qv = qvs[0]
            qn = sum(x * x for x in qv) ** 0.5
            sims = sorted(((-_cosine(qv, _unpack(blob), qn), path) for path, blob in usable.items()))
            vector = [path for _, path in sims[:TOP]]
            mode = "hybrid"
        except Exception as e:  # 원 메시지에 키가 섞일 수 있어 클래스 이름만 남긴다.
            warnings.append(f"vector search failed: {type(e).__name__}")

    krank = {p: i for i, p in enumerate(keyword, 1)}
    vrank = {p: i for i, p in enumerate(vector, 1)}
    scores = {p: sum(1 / (RRF_K + r[p]) for r in (krank, vrank) if p in r) for p in krank.keys() | vrank.keys()}
    ranked = sorted(scores, key=lambda p: (-scores[p], p))[:k]
    results = [
        {
            "path": p,
            "title": titles.get(p, p),
            "score": round(scores[p], 6),
            "keyword_rank": krank.get(p),
            "vector_rank": vrank.get(p),
        }
        for p in ranked
    ]
    _log(
        root,
        "search-log.jsonl",
        {"ts": _ts(), "query": query, "mode": mode, "k": k, "source": source, "results": [r["path"] for r in results]},
    )
    return {"mode": mode, "results": results, "stale_vectors": stale_vectors, "warnings": warnings}


def plist(root: Path, python: str) -> str:
    r, py = shlex.quote(str(root)), shlex.quote(python)
    script = shlex.quote(str(Path(__file__).resolve()))
    log = f"{root}/.cache/launchd.log"
    command = f"cd {r} && {py} {script} --root {r} build && {py} {script} --root {r} embed"
    data = {
        "Label": "io.github.doggyfootprint.wiki-embed",
        "ProgramArguments": ["/bin/sh", "-c", command],
        "StartCalendarInterval": {"Hour": 4, "Minute": 0},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    return plistlib.dumps(data).decode("utf-8")


def resolve_embedder(
    root: Path, embedder: Embedder | None, environ: Mapping[str, str]
) -> tuple[Embedder | None, list[str]]:
    if embedder is not None:
        return embedder, []
    key = api_key(root, environ)
    if key is None:
        return None, ["vector search disabled: OPENAI_API_KEY not set"]
    cfg = embedding_config(root)
    return OpenAIEmbedder(cfg["model"], cfg["dim"], key), []


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise IndexToolError(f"usage error: {message}")


def _emit(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False))


def main(
    argv: list[str] | None = None,
    embedder: Embedder | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    ap = QuietParser(prog="index.py")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    p_embed = sub.add_parser("embed")
    p_embed.add_argument("--min-free-mb", type=float, default=None)
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--k", type=int, default=10)
    p_plist = sub.add_parser("plist")
    p_plist.add_argument("--python", default=sys.executable)
    try:
        args = ap.parse_args(argv)
        root = resolve_root(args.root, environ, Path.cwd() if cwd is None else cwd)
        if args.command == "build":
            _emit(build(root))
        elif args.command == "embed":
            emb, _ = resolve_embedder(root, embedder, environ)
            if emb is None:
                log_embed_error(root, "OPENAI_API_KEY not set")
                raise IndexToolError("OPENAI_API_KEY not set")
            min_free = args.min_free_mb if args.min_free_mb is not None else embedding_config(root)["min_free_mb"]
            _emit(embed(root, emb, min_free))
        elif args.command == "search":
            emb, notes = resolve_embedder(root, embedder, environ)
            result = search(root, args.query, k=args.k, embedder=emb)
            result["warnings"] += notes
            _emit(result)
        else:
            sys.stdout.write(plist(root, args.python))
    except IndexToolError as e:
        print(str(e).replace("\n", " "), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
