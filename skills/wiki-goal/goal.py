# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""표준 라이브러리와 같은 폴더의 index.py만 import한다. claude.ai 코드 실행에는 이 두 파일만 내려받는다."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index  # noqa: E402
from index import Embedder, IndexToolError  # noqa: E402

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KINDS = ("official", "subjective")
BASES = ("syllabus-order", "official", "inferred", "user")
LINK_FIELDS = ["goal", "concept", "page", "status", "score", "method", "date"]
STATUSES = ("none", "note-only", "weak", "ok", "unknown")
DEFICIENCY = {"none": 1.0, "note-only": 0.9, "unknown": 0.7, "weak": 0.6, "ok": 0.0}


class GoalError(Exception):
    pass


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_id(v, field: str) -> str:
    if not isinstance(v, str) or not ID_RE.match(v):
        raise GoalError(f"{field}: invalid id {v!r}")
    return v


def _check_str(v, field: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise GoalError(f"{field}: must be a non-empty string")
    return v


def load_goal(root: Path, goal_id: str) -> dict:
    path = Path(root) / "goals" / f"{goal_id}.toml"
    if not goal_id or "/" in goal_id or "\\" in goal_id or not path.is_file():
        raise GoalError(f"goal not found: {goal_id}")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise GoalError(f"{goal_id}.toml: invalid TOML: {e}") from None

    gid = _check_id(raw.get("id"), "id")
    if gid != goal_id:
        raise GoalError(f"id: {gid!r} does not match file name {goal_id!r}")
    title = _check_str(raw.get("title"), "title")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise GoalError(f"kind: {kind!r} not in {list(KINDS)}")
    source = raw.get("source", {})
    if not isinstance(source, dict):
        raise GoalError("source: must be a table")

    areas: list[dict] = []
    for i, a in enumerate(raw.get("areas", [])):
        aid = _check_id(a.get("id"), f"areas[{i}].id")
        if any(x["id"] == aid for x in areas):
            raise GoalError(f"areas[{i}].id: duplicate id {aid!r}")
        if not _is_num(a.get("weight")) or a["weight"] <= 0:
            raise GoalError(f"areas[{i}].weight: must be a number > 0 (area {aid!r})")
        areas.append({"id": aid, "name": _check_str(a.get("name"), f"areas[{i}].name"), "weight": a["weight"]})

    concepts: list[dict] = []
    for i, c in enumerate(raw.get("concepts", [])):
        cid = _check_id(c.get("id"), f"concepts[{i}].id")
        if any(x["id"] == cid for x in concepts):
            raise GoalError(f"concepts[{i}].id: duplicate id {cid!r}")
        if c.get("area") not in {a["id"] for a in areas}:
            raise GoalError(f"concepts[{i}].area: unknown area {c.get('area')!r} (concept {cid!r})")
        aliases = c.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            raise GoalError(f"concepts[{i}].aliases: must be a list of strings (concept {cid!r})")
        section = c.get("section", "")
        if not isinstance(section, str):
            raise GoalError(f"concepts[{i}].section: must be a string (concept {cid!r})")
        concepts.append(
            {
                "id": cid,
                "name": _check_str(c.get("name"), f"concepts[{i}].name"),
                "area": c["area"],
                "aliases": aliases,
                "section": section,
            }
        )
    for a in areas:
        if not any(c["area"] == a["id"] for c in concepts):
            raise GoalError(f"areas: area {a['id']!r} has no concepts")

    cids = {c["id"] for c in concepts}
    prereqs: list[dict] = []
    for i, p in enumerate(raw.get("prereqs", [])):
        frm, to, basis = p.get("from"), p.get("to"), p.get("basis")
        if frm not in cids:
            raise GoalError(f"prereqs[{i}].from: unknown concept {frm!r}")
        if to not in cids:
            raise GoalError(f"prereqs[{i}].to: unknown concept {to!r}")
        if frm == to:
            raise GoalError(f"prereqs[{i}]: concept {frm!r} depends on itself")
        if basis not in BASES:
            raise GoalError(f"prereqs[{i}].basis: {basis!r} not in {list(BASES)}")
        prereqs.append({"from": frm, "to": to, "basis": basis})
    _check_acyclic(cids, prereqs)

    return {"id": gid, "title": title, "kind": kind, "source": source, "areas": areas, "concepts": concepts, "prereqs": prereqs}


def _check_acyclic(cids: set[str], prereqs: list[dict]) -> None:
    out: dict[str, list[str]] = {c: [] for c in cids}
    for p in prereqs:
        out[p["from"]].append(p["to"])
    state: dict[str, int] = {}

    def visit(n: str) -> None:
        state[n] = 1
        for m in out[n]:
            if state.get(m) == 1:
                raise GoalError(f"prereqs: cycle through concept {m!r}")
            if m not in state:
                visit(m)
        state[n] = 2

    for c in sorted(cids):
        if c not in state:
            visit(c)


def _goal_files(root: Path) -> list[Path]:
    d = Path(root) / "goals"
    return sorted(d.glob("*.toml")) if d.is_dir() else []


def check(root: Path, goal_id: str) -> dict:
    goal = load_goal(Path(root), goal_id)
    return {
        "goal": goal["id"],
        "title": goal["title"],
        "kind": goal["kind"],
        "areas": [
            {
                "id": a["id"],
                "name": a["name"],
                "weight": a["weight"],
                "concepts": [{"id": c["id"], "name": c["name"]} for c in goal["concepts"] if c["area"] == a["id"]],
            }
            for a in goal["areas"]
        ],
        "prereqs": len(goal["prereqs"]),
    }


def list_goals(root: Path) -> dict:
    goals, errors = [], []
    for f in _goal_files(root):
        try:
            goal = load_goal(Path(root), f.stem)
        except GoalError as e:
            errors.append({"file": f.name, "error": str(e)})
            continue
        goals.append(
            {
                "goal": goal["id"],
                "title": goal["title"],
                "kind": goal["kind"],
                "areas": [a["name"] for a in goal["areas"]],
                "concepts": len(goal["concepts"]),
            }
        )
    return {"goals": goals, "errors": errors}


def _links_path(root: Path) -> Path:
    return Path(root) / "data" / "goal_links.csv"


def _read_links(root: Path) -> dict[tuple[str, str, str], dict]:
    path = _links_path(root)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != LINK_FIELDS:
            raise GoalError("bad goal_links.csv header")
        return {(r["goal"], r["concept"], r["page"]): r for r in reader}


def _write_links(root: Path, links: dict[tuple[str, str, str], dict]) -> None:
    index.write_csv(_links_path(root), LINK_FIELDS, [links[k] for k in sorted(links)])


def _read_reviews(root: Path) -> dict[str, tuple[str, int, str]]:
    path = Path(root) / "data" / "reviews.csv"
    latest: dict[str, tuple[str, int, str]] = {}
    if not path.exists():
        return latest
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not {"date", "page", "rating"} <= set(reader.fieldnames or []):
            raise GoalError("bad reviews.csv")
        for i, r in enumerate(reader):
            cur = latest.get(r["page"])
            if cur is None or (r["date"], i) >= (cur[0], cur[1]):
                latest[r["page"]] = (r["date"], i, r["rating"])
    return latest


def _today(date: str | None) -> str:
    if date is None:
        return dt.date.today().isoformat()
    try:
        return dt.date.fromisoformat(date).isoformat()
    except ValueError:
        raise GoalError(f"bad date: {date!r}") from None


def suggest(root: Path, goal_id: str, k: int = 3, embedder: Embedder | None = None, date: str | None = None) -> dict:
    root = Path(root)
    goal = load_goal(root, goal_id)
    links = _read_links(root)
    day = _today(date)
    added = 0
    out = []
    for c in goal["concepts"]:
        res = index.search(root, " ".join([c["name"], *c["aliases"]]), k=k, embedder=embedder, source="suggest")
        cands = []
        for r in res["results"]:
            key = (goal_id, c["id"], r["path"])
            if key not in links:
                links[key] = {
                    "goal": goal_id,
                    "concept": c["id"],
                    "page": r["path"],
                    "status": "candidate",
                    "score": str(r["score"]),
                    "method": res["mode"],
                    "date": day,
                }
                added += 1
            cands.append({"page": r["path"], "score": r["score"], "status": links[key]["status"]})
        out.append({"id": c["id"], "name": c["name"], "candidates": cands})
    if added:
        _write_links(root, links)
    return {"goal": goal_id, "added": added, "concepts": out}


def _check_page(root: Path, page: str) -> bool:
    p = PurePosixPath(page)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and len(p.parts) >= 2
        and p.parts[0] == "wiki"
        and p.suffix == ".md"
        and (root / page).is_file()
    )


def set_status(root: Path, goal_id: str, pairs: list[tuple[str, str]], status: str, date: str | None = None) -> dict:
    root = Path(root)
    if status not in ("confirmed", "rejected"):
        raise GoalError(f"bad status: {status!r}")
    goal = load_goal(root, goal_id)
    links = _read_links(root)
    day = _today(date)
    cids = {c["id"] for c in goal["concepts"]}
    for concept, page in pairs:
        if concept not in cids:
            raise GoalError(f"unknown concept in pair {concept}={page}")
        if not _check_page(root, page):
            raise GoalError(f"page not found under wiki/ in pair {concept}={page}")
    updated = added = 0
    for concept, page in pairs:
        key = (goal_id, concept, page)
        if key in links:
            links[key]["status"] = status
            links[key]["date"] = day
            updated += 1
        else:
            links[key] = {
                "goal": goal_id, "concept": concept, "page": page,
                "status": status, "score": "", "method": "manual", "date": day,
            }
            added += 1
    _write_links(root, links)
    return {"goal": goal_id, "updated": updated, "added": added}


def _concept_status(pages: list[str], levels: dict[str, int | None], reviews: dict) -> tuple[str, int | None, str | None]:
    if not pages:
        return "none", None, None
    known = [levels[p] for p in pages if levels.get(p) is not None]
    level = max(known) if known else None
    latest = max((reviews[p] for p in pages if p in reviews), default=None, key=lambda r: (r[0], r[1]))
    rating = latest[2] if latest else None
    if level is None and rating is None:
        status = "note-only"
    elif (level is not None and level <= 2) or rating == "again":
        status = "weak"
    elif level is not None and level >= 3:
        status = "ok"
    else:
        status = "unknown"
    return status, level, rating


def _coverage(goal: dict, links: dict, levels: dict, reviews: dict) -> dict:
    confirmed: dict[str, list[str]] = {}
    for (g, concept, page), row in links.items():
        if g == goal["id"] and row["status"] == "confirmed":
            confirmed.setdefault(concept, []).append(page)
    areas = []
    weighted = 0.0
    total_weight = 0.0
    for a in goal["areas"]:
        counts = dict.fromkeys(STATUSES, 0)
        items = []
        for c in (c for c in goal["concepts"] if c["area"] == a["id"]):
            pages = sorted(confirmed.get(c["id"], []))
            status, level, rating = _concept_status(pages, levels, reviews)
            counts[status] += 1
            items.append({"id": c["id"], "name": c["name"], "status": status, "pages": pages, "level": level, "last_rating": rating})
        weighted += a["weight"] * counts["ok"] / len(items)
        total_weight += a["weight"]
        areas.append({"id": a["id"], "name": a["name"], "weight": a["weight"], "counts": counts, "concepts": items})
    return {
        "goal": goal["id"],
        "title": goal["title"],
        "kind": goal["kind"],
        "areas": areas,
        "weighted_ok": round(weighted / total_weight, 4) if total_weight else 0.0,
    }


def _context(root: Path):
    links = _read_links(root)
    reviews = _read_reviews(root)
    pages, _ = index.load_pages(root)
    return links, reviews, pages, {p["path"]: p["level"] for p in pages}


def coverage(root: Path, goal_id: str) -> dict:
    root = Path(root)
    goal = load_goal(root, goal_id)
    links, reviews, _, levels = _context(root)
    return _coverage(goal, links, levels, reviews)


def start(root: Path, goal_id: str, n: int = 5) -> dict:
    root = Path(root)
    goal = load_goal(root, goal_id)
    links, reviews, _, levels = _context(root)
    cov = _coverage(goal, links, levels, reviews)
    status = {c["id"]: c["status"] for a in cov["areas"] for c in a["concepts"]}
    weight = {}
    for a in cov["areas"]:
        for c in a["concepts"]:
            weight[c["id"]] = a["weight"] / len(a["concepts"])
    incoming: dict[str, list[dict]] = {c["id"]: [] for c in goal["concepts"]}
    children: dict[str, set[str]] = {c["id"]: set() for c in goal["concepts"]}
    for p in goal["prereqs"]:
        incoming[p["to"]].append(p)
        children[p["from"]].add(p["to"])

    def descendants(cid: str) -> set[str]:
        seen: set[str] = set()
        stack = list(children[cid])
        while stack:
            m = stack.pop()
            if m not in seen:
                seen.add(m)
                stack.extend(children[m])
        return seen

    items = []
    blocked = 0
    for c in goal["concepts"]:
        cid = c["id"]
        if status[cid] == "ok":
            continue
        if not all(status[p["from"]] == "ok" for p in incoming[cid]):
            blocked += 1
            continue
        items.append(
            {
                "id": cid,
                "name": c["name"],
                "status": status[cid],
                "score": round(weight[cid] * DEFICIENCY[status[cid]], 4),
                "unlocks": len(descendants(cid)),
                "prereqs": [{"id": p["from"], "basis": p["basis"]} for p in incoming[cid]],
            }
        )
    items.sort(key=lambda i: (-i["score"], -i["unlocks"], i["id"]))
    return {"goal": goal_id, "items": items[:n], "blocked": blocked}


def overlap(root: Path) -> dict:
    root = Path(root)
    links, reviews, pages, levels = _context(root)
    goals, errors = [], []
    for f in _goal_files(root):
        try:
            goal = load_goal(root, f.stem)
        except GoalError as e:
            errors.append({"file": f.name, "error": str(e)})
            continue
        cov = _coverage(goal, links, levels, reviews)
        counts = dict.fromkeys(STATUSES, 0)
        for a in cov["areas"]:
            for s in STATUSES:
                counts[s] += a["counts"][s]
        candidates = {c for (g, c, _), row in links.items() if g == goal["id"] and row["status"] == "candidate"}
        goals.append(
            {
                "goal": goal["id"],
                "title": goal["title"],
                "kind": goal["kind"],
                "concepts": len(goal["concepts"]),
                "counts": counts,
                "weighted_ok": cov["weighted_ok"],
                "candidate_concepts": len(candidates & {c["id"] for c in goal["concepts"]}),
            }
        )
    goals.sort(key=lambda g: (-g["weighted_ok"], g["goal"]))
    linked = {page for (_, _, page), row in links.items() if row["status"] == "confirmed"}
    unlinked = sorted(p["path"] for p in pages if p["type"] == "concept" and p["path"] not in linked)
    return {"goals": goals, "errors": errors, "unlinked_pages": unlinked}


def _parse_pair(text: str) -> tuple[str, str]:
    concept, sep, page = text.partition("=")
    if not sep or not concept or not page:
        raise GoalError(f"bad pair {text!r}: expected CONCEPT=PAGE")
    return concept, page


def main(
    argv: list[str] | None = None,
    embedder: Embedder | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    ap = index.QuietParser(prog="goal.py")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("suggest")
    p.add_argument("goal")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--date")
    for name in ("confirm", "reject"):
        p = sub.add_parser(name)
        p.add_argument("goal")
        p.add_argument("pairs", nargs="+")
        p.add_argument("--date")
    sub.add_parser("check").add_argument("goal")
    sub.add_parser("list")
    sub.add_parser("coverage").add_argument("goal")
    p = sub.add_parser("start")
    p.add_argument("goal")
    p.add_argument("--n", type=int, default=5)
    sub.add_parser("overlap")
    try:
        args = ap.parse_args(argv)
        root = index.resolve_root(args.root, environ, Path.cwd() if cwd is None else cwd)
        if args.command == "suggest":
            emb, notes = index.resolve_embedder(root, embedder, environ)
            result = suggest(root, args.goal, k=args.k, embedder=emb, date=args.date)
            if notes:
                result["warnings"] = notes
        elif args.command in ("confirm", "reject"):
            pairs = [_parse_pair(t) for t in args.pairs]
            status = "confirmed" if args.command == "confirm" else "rejected"
            result = set_status(root, args.goal, pairs, status, args.date)
        elif args.command == "check":
            result = check(root, args.goal)
        elif args.command == "list":
            result = list_goals(root)
        elif args.command == "coverage":
            result = coverage(root, args.goal)
        elif args.command == "start":
            result = start(root, args.goal, args.n)
        else:
            result = overlap(root)
    except (GoalError, IndexToolError) as e:
        print(str(e).replace("\n", " "), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
