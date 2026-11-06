---
name: wiki-goal
description: Set learning goals as goal maps (TOML files under goals/) with weighted areas, concepts, and prerequisites. Decide whether the stated goals become one map, several maps, or an addition to an existing map, then validate with goal.py, link existing wiki notes, and show where to start. Use for requests like "/wiki-goal", "set a study goal", "I want to prepare for an exam", "make a learning goal", or "plan what to study for X".
---

# wiki-goal: turn learning goals into goal maps

A goal map is `goals/<id>.toml` under the wiki root. `load_goal` in `goal.py` validates its format. The tool is `uv run "<skill dir>/goal.py" --root <root> <subcommand>` (`<skill dir>` is the "Base directory" Claude Code reports when this skill loads). Output is one line of JSON; on failure it prints a message to stderr and exits with code 2. For `root`, use the `root` from `uv run "<skill dir>/../wiki-add/learn.py" env` (the git top level if the add skill is absent). If `mode` is `chat` or this is a claude.ai chat, do not follow this file; follow only `claude-ai.md`.

Talk with the user in Korean, and write names and notes inside the goal map in Korean (see `example.toml`).

Keep token cost down. See existing goals only through the output of `list` and `check`, and open a toml file only when editing it. Do not open wiki pages. A goal map never changes `wiki/`.

If the only request is to link notes to an existing map (for example, a map made in claude.ai chat), run `check <id>` and then start from (f).

## (a) Hear the goal

Do not re-ask what the user already said. Ask only for what the decision needs and is missing, one question at a time.
- What they want to do (one thing or several, exactly as the user said it)
- How completion is judged (passing an exam, a deliverable to build, something they must be able to explain, etc.)
- Deadline and priority (if any)

## (b) Check existing goals

Run `list`. Only for goals whose title or areas look like they overlap the new goal, look at the concept list with `check <id>`. If `errors` is non-empty, tell the user each file and its reason.

## (c) Decide whether to merge or split

One goal map corresponds to **one completion judgment**.
- Merge: the goals finish by the same criterion (the same exam, the same deliverable). If one goal is part of another, put it in as an area of the larger map. If an existing goal meets this condition, do not create a new map; add areas and concepts to the existing one.
- Split: completion is judged separately (different exams, an official exam vs. a subjective goal), the deadlines or priorities differ, or the concepts barely overlap.
- Do not merge just because concepts overlap. Keep an overlapping concept under the same name in each map; `overlap` does the comparison.

Show the decision as one line per goal, e.g. `새 지도 <id>: <이유>`, `기존 <id>에 영역 추가: <이유>`. If the user changes it, follow them.

## (d) Draft the map

Decide the following for each goal. The format is the same as `<skill dir>/example.toml`.
- `id`: lowercase alphanumerics and hyphens (`^[a-z0-9]+(-[a-z0-9]+)*$`), equal to the file name. It must not collide with an existing id.
- `title`, `kind`: `official` if an official exam outline or curriculum exists, otherwise `subjective`.
- `[source]`:
  - official: the official source `url`, the check date `checked`, and `note` (exam format, parts with no official basis). Verify the source on the web. If it could not be verified, write that in `note` and tell the user.
  - subjective: in `note`, write the goal, completion criterion, and deadline the user stated.
- `[[areas]]`: `id`, `name`, `weight` (a number greater than 0). For official, use the official point allocation or question count; for subjective, the priority the user stated. If the priority is unknown, give all areas the same value and say so.
- `[[concepts]]`: `id`, `name`, `area`, `section` (optional), `aliases`.
  - One concept is the size studied in one `/wiki-add` run. Aim for 10-40 per goal; outside that range, group or split concepts.
  - `aliases` are used for note search (`suggest`). Include the original-language term, abbreviations, and common alternative spellings.
- `[[prereqs]]`: `from` (the concept to know first) → `to`, with `basis` set to one of the following. No cycles.
  - `official`: an official document supports it.
  - `syllabus-order`: the only support is the listing order in an official document.
  - `inferred`: LLM inference.
  - `user`: the user said so.

**Before writing**, show the following for each goal and get confirmation. Do not write any file before confirmation.
- The decision from (c), `id`, `title`, `kind`, source
- Concept names grouped by area (with weight)
- A summary of prerequisites (`A → B` lines) and the count per basis

## (e) Write and validate

After confirmation, write or edit `goals/<id>.toml`, then run `check <id>`. On exit code 2, fix what the message says and `check` again.
- When editing an existing map, do not change the `id` of existing concepts. `data/goal_links.csv` links notes by concept id.

## (f) Link notes and pick a starting point

1. If the wiki has concept notes, run `suggest <id>`. It lists candidate notes (`page`, `score`) for each concept and records new candidates in `data/goal_links.csv`. If `warnings` is non-empty, mention it briefly (without `OPENAI_API_KEY` it does keyword search only). The search index is created in `<root>/.cache/`.
   - There is no score floor, so unrelated candidates get mixed in. Judging by the title in the path, show only candidates that cover the concept.
   - Record the ones the user accepts with `confirm <id> <concept-id>=<page> ...` and the ones they reject with `reject <id> <concept-id>=<page> ...`.
2. Run `start <id>`, show the concepts to start now (`items`), and suggest starting with `/wiki-add <concept name>`. `blocked` is the number of concepts deferred because their prerequisites are not yet `ok`.

## (g) Commit

If the repository uses git, commit. Do not push.
1. `git add` only the `goals/<id>.toml` files written or edited this time, plus `data/goal_links.csv` if `suggest`, `confirm`, or `reject` changed it. Do not use `git add -A`.
2. `git commit -m "goal: <date> <id 목록>"`. If the repository's rules require `Request:`/`Intent:` lines, add them.
3. Finally report: goals created or edited (id, concept count), the number of linked notes, and the recommended starting concepts.
