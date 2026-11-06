import csv
import hashlib
import io
import json
import math
import shutil
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "wiki-goal"))

import index  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "goal_poc"
LINK_HEADER = ["goal", "concept", "page", "status", "score", "method", "date"]
REVIEW_HEADER = ["date", "page", "rating", "mode", "source", "result_id"]

JOIN = "wiki/concepts/join.md"
WINDOW = "wiki/concepts/window-function.md"
NORMALIZATION = "wiki/concepts/normalization.md"
SUBQUERY = "wiki/concepts/subquery.md"
GROUP_BY = "wiki/concepts/group-by.md"
TRANSACTION = "wiki/concepts/sql/transaction.md"
ENTITY = "wiki/concepts/modeling/entity.md"
CLIMBING = "wiki/hobby/climbing.md"
FIXTURE_PAGES = sorted(
    [JOIN, WINDOW, NORMALIZATION, SUBQUERY, GROUP_BY, TRANSACTION, ENTITY, CLIMBING]
)
CONCEPT_PAGES = sorted(p for p in FIXTURE_PAGES if p != CLIMBING)


def make_root(tmp_path, name="root"):
    root = (Path(tmp_path) / name).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("wiki", "goals", "data"):
        shutil.copytree(FIXTURE / sub, root / sub)
    return root


def add_extra_goal(root, which):
    src = FIXTURE / ("goals_extra" if which == "extra" else "goals_broken")
    for f in src.glob("*.toml"):
        shutil.copy(f, root / "goals" / f.name)


def write_page(root, rel, title, body="", **front):
    lines = ["---"]
    for k, v in front.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    if title is not None:
        lines.append(f"# {title}")
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" + body + "\n", encoding="utf-8")
    return path


def write_goal(root, goal_id, text):
    path = Path(root) / "goals" / f"{goal_id}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def goal_toml(goal_id, areas, concepts, prereqs=(), kind="official", title=None):
    out = [f'id = "{goal_id}"', f'title = "{title or goal_id}"', f'kind = "{kind}"', ""]
    for aid, weight in areas:
        out += ["[[areas]]", f'id = "{aid}"', f'name = "{aid}"', f"weight = {weight}", ""]
    for c in concepts:
        cid, area = c[0], c[1]
        name = c[2] if len(c) > 2 else cid
        out += ["[[concepts]]", f'id = "{cid}"', f'name = "{name}"', f'area = "{area}"', ""]
    for frm, to, basis in prereqs:
        out += ["[[prereqs]]", f'from = "{frm}"', f'to = "{to}"', f'basis = "{basis}"', ""]
    return "\n".join(out)


def write_links(root, rows, header=None):
    path = Path(root) / "data" / "goal_links.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header or LINK_HEADER)
        for r in rows:
            w.writerow(r)
    return path


def link(goal, concept, page, status="confirmed", score="", method="manual", date="2026-01-01"):
    return [goal, concept, page, status, score, method, date]


def read_links(root):
    path = Path(root) / "data" / "goal_links.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_reviews(root, rows, header=None):
    path = Path(root) / "data" / "reviews.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header or REVIEW_HEADER)
        for r in rows:
            w.writerow(r)
    return path


def review(date, page, rating):
    return [date, page, rating, "quiz", "quiz.py", "rid"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_tree(root, *subpaths):
    out = {}
    for sub in subpaths:
        base = Path(root) / sub
        if base.is_file():
            out[sub] = sha256_file(base)
        elif base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    out[str(p.relative_to(root))] = sha256_file(p)
    return out


def run_cli(module, argv, capsys, **kwargs):
    capsys.readouterr()
    try:
        code = module.main([str(a) for a in argv], **kwargs)
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# The spec fixes the vector table's columns but not its name, so the table is found by its columns.

VEC_COLS = ("path", "model", "dim", "text_hash", "vec")


def db_path(root):
    return Path(root) / ".cache" / "wiki-index.sqlite"


def vector_rows(root):
    path = db_path(root)
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
            if all(c in cols for c in VEC_COLS):
                return sorted(
                    con.execute(f'select path, model, dim, text_hash, vec from "{t}"').fetchall()
                )
        return []
    finally:
        con.close()


def unpack(blob, dim):
    assert len(blob) == dim * 4
    return list(struct.unpack(f"<{dim}f", blob))


def cosine(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def read_jsonl(root, name):
    path = Path(root) / ".cache" / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class MapEmbedder:

    def __init__(self, model="fake-a", dim=4, exact=None, prefixes=None, default=None,
                 fail_on_call=None, fail_on_text=None, count_delta=0, dim_delta=0,
                 fail_exc=None, query_vec=None, query_result=None):
        self.model = model
        self.dim = dim
        self.exact = exact or {}
        self.prefixes = prefixes or {}
        self.default = default or [0.0] * (dim - 1) + [1.0]
        self.fail_on_call = fail_on_call
        self.fail_on_text = fail_on_text
        self.count_delta = count_delta
        self.dim_delta = dim_delta
        self.fail_exc = fail_exc
        self.query_vec = query_vec
        self.query_result = query_result
        self.calls = []

    def vec_for(self, text):
        if text in self.exact:
            return list(self.exact[text])
        for prefix, vec in self.prefixes.items():
            if text.startswith(prefix + "\n"):
                return list(vec)
        return list(self.default)

    def embed(self, texts):
        self.calls.append(list(texts))
        failing = self.fail_on_call == len(self.calls) or (
            self.fail_on_text is not None and self.fail_on_text in texts)
        if failing:
            raise self.fail_exc or index.IndexToolError("boom-embed")
        if self.query_result is not None and len(texts) == 1 and texts[0] in self.exact:
            return [list(v) for v in self.query_result]
        if self.query_vec is not None and len(texts) == 1 and texts[0] in self.exact:
            return [list(self.query_vec)]
        vecs = [self.vec_for(t) for t in texts]
        if self.dim_delta:
            vecs = [(v + [0.5] * self.dim_delta)[: self.dim + self.dim_delta] for v in vecs]
        if self.count_delta < 0:
            vecs = vecs[: self.count_delta]
        elif self.count_delta > 0:
            vecs = vecs + [list(self.default)] * self.count_delta
        return vecs

    @property
    def all_texts(self):
        return [t for call in self.calls for t in call]


FIXTURE_PREFIXES = {
    "조인": [1, 0, 0, 0],
    "서브쿼리": [0.8, 0.6, 0, 0],
    "정규화": [0.6, 0.8, 0, 0],
    "GROUP BY": [1, 1, 0, 0],
    "윈도우 함수": [0, 1, 0, 0],
}


def fixture_embedder(**kw):
    exact = {"조인": [1, 0, 0, 0], "zzqvec": [1, 0, 0, 0]}
    exact.update(kw.pop("exact", {}))
    return MapEmbedder(exact=exact, prefixes=dict(FIXTURE_PREFIXES), **kw)


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self, *a):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


class FakeOpenAI:

    def __init__(self, error=None):
        self.error = error
        self.requests = []
        self.timeouts = []

    def __call__(self, req, *args, **kwargs):
        timeout = kwargs.get("timeout", args[1] if len(args) > 1 else None)
        self.timeouts.append(timeout)
        body = json.loads(req.data.decode("utf-8"))
        self.requests.append({
            "url": req.full_url,
            "method": req.get_method(),
            "auth": req.get_header("Authorization"),
            "body": body,
        })
        if self.error is not None:
            raise self.error
        dim = body["dimensions"]
        data = []
        for i, text in enumerate(body["input"]):
            v = [0.0] * dim
            v[len(text) % dim] = 1.0
            data.append({"object": "embedding", "index": i, "embedding": v})
        return FakeResponse({"data": data})


def http_error(code=401, body=b"{}"):
    import urllib.error
    return urllib.error.HTTPError(
        "https://api.openai.com/v1/embeddings", code, "Unauthorized", {}, io.BytesIO(body)
    )
