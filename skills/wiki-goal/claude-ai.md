# Setting learning goals in claude.ai chat

This is the procedure for claude.ai chat. The wiki lives in a GitHub repository; this chat reads only the `goals/` folder there and commits the goal map `goals/<id>.toml` directly. Follow sections (a), (c), and (d) of `skills/wiki-goal/SKILL.md` in this plugin for the decision criteria; the format example is `skills/wiki-goal/example.toml`. Do not follow that file's tool runs (`list`, `suggest`, etc.) or its sections (f) and (g). A `skills/<name>/...` path in this file is a file of this plugin's `<name>` skill; this skill's own files are next to this file, in `<this folder>`.

Talk with the user in Korean. Quoted messages below are said to the user as written.

## 0. Repository

Use the repository named in the user's prompt; if none, the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`).

## 1. Hear the goal and check existing goals

- Hear the goal, completion criterion, and deadline/priority as in section (a) of `skills/wiki-goal/SKILL.md`.
- Through the GitHub connection, look only at the file list of the repository's `goals/` folder. Open only files whose names (`<id>.toml`) look like they overlap the new goal, and check their title, areas, and concepts. Do not open wiki pages (`wiki/`). If the folder cannot be read, tell the user that existing goals are unknown and continue.

## 2. Merge or split, and draft

Decide and draft as in sections (c) and (d) of `skills/wiki-goal/SKILL.md`. Verify official sources on the web. Before writing, show the summary from section (d) and **get confirmation**. Do not create a file before confirmation. When editing an existing map, do not change the `id` of existing concepts.

## 3. Validate

**If code execution is on**, write the confirmed map to `<script dir>/root/goals/<id>.toml` and check it. `<script dir>` is `/tmp/llm-wiki`. Before the first run, copy the scripts there once: `mkdir -p /tmp/llm-wiki && cp "<this folder>/goal.py" "<this folder>/index.py" /tmp/llm-wiki/`.

```
python3 "<script dir>/goal.py" --root "<script dir>/root" check <id>
```

On exit code 2, fix what the stderr message says and check again. When it passes, also run `start <id>` to get the first concepts to study (`items`). This result does not reflect the wiki's existing notes (it treats every concept as not yet studied).

**If code execution is off or the scripts could not be copied**, check these rules yourself.
- `id` equals the file name, every id matches `^[a-z0-9]+(-[a-z0-9]+)*$`, and ids are unique among areas and among concepts.
- `title` is a non-empty string, and `[source]` is a table.
- `kind` is `official` or `subjective`. Every area and concept has a non-empty `name`. Each area's `weight` is a number greater than 0, and each area has at least one concept.
- A concept's `area` is an existing area id. `aliases` is a list of strings.
- A prerequisite's `from` and `to` are existing concept ids and differ from each other, `basis` is one of `official`, `syllabus-order`, `inferred`, `user`, and there are no cycles.

## 4. Commit

Commit `goals/<id>.toml` to the repository's **default branch** through the GitHub connection. The commit message is `goal: <날짜> <id>`. When editing an existing file, change only the confirmed parts of the content you opened.

If the commit fails (no permission, no connection, rejected), attach the file for download and tell the user: "저장소의 `goals/`에 이 파일을 넣어 주세요."

## 5. Report

Tell the user the goals created or edited (id, concept count) and the first concepts to study. Then tell them: "위키에 이미 있는 노트를 이 목표의 개념과 잇는 일은 Claude Code에서 `/wiki-goal <id> 노트 연결`로 합니다. 시작 개념은 `/wiki-add <개념 이름>`이나 `/wiki-learn`으로 공부하세요."
