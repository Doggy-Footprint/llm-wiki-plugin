# Keeping an insight in claude.ai chat

This is the procedure for claude.ai chat. The wiki lives in a GitHub repository; this chat reads only `chat/insights.md` there and uploads one result file to `chat/inbox/`. The wiki applies it later (`insight.py sync`). Read `skills/wiki-insight/SKILL.md` in this plugin for what an insight page is; do not follow its tool runs or its sections (a), (b), (d), and (f). A `skills/<name>/...` path in this file is a file of this plugin's `<name>` skill; this skill's own files are next to this file, in `<this folder>`.

Talk with the user in Korean and write the result file in Korean. Korean headings and quoted phrases below are literal strings that the import script uses; write them exactly as given.

## 0. Repository

Use the repository named in the user's prompt; if none, the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`).

## 1. Hear the realization

Follow (c) of `skills/wiki-insight/SKILL.md`: take the realization from the prompt or ask once, stop if it is only an event or a fact, and keep the user's sentence verbatim.

## 2. Find the same question

- Through the GitHub connection, read the repository's `chat/insights.md`. Each line is `- [[제목]] — confidence, updated: 지금 생각`, grouped by area (`life`, `career`). Do not open wiki pages (`wiki/`). If it cannot be read, tell the user that existing insights are unknown and continue as a new insight.
- If a title asks the same question, compare with its 지금 생각. If they differ, ask: "예전엔 ~라고 하셨는데 바뀐 건가요?" Only if the user says it changed, give a new 지금 생각 and, if their certainty changed, a new confidence. Use that title **exactly** as written in `chat/insights.md`.
- If none matches, draft a new insight: a title phrased as a question, area (`life` or `career`), 지금 생각 (one or two sentences in the user's words), and confidence (`hunch` by default, `likely` if the user is fairly sure). Never use `tested`.

## 3. Confirm

Show the title, area (new only), 지금 생각, the line `- 날짜: 사용자 말`, confidence, and links (`[[제목]] — 관계`). Get confirmation. Do not create the file before confirmation.

## 4. Create the result file

**If code execution is on**, create it with `<script dir>/insight.py`. `<script dir>` is `/tmp/llm-wiki`. Before the first run, copy the script there once: `mkdir -p /tmp/llm-wiki && cp "<this folder>/insight.py" /tmp/llm-wiki/`. Pass the content exactly as confirmed; omit `--area` for an existing title, and omit `--now` and `--confidence` when they did not change.

```
python3 "<script dir>/insight.py" result "<제목>" --said "<사용자 말>" --out /mnt/user-data/outputs \
  [--area life|career] [--now "<지금 생각>"] [--confidence hunch|likely] \
  [--supplement "<보충>"] [--link "[[제목]] — 관계"] --date YYYY-MM-DD
```

Repeat `--link` once per line. The `path` in the output JSON is the created file. For `--out`, use a downloadable folder (or the current folder if there is none). Use today's date.

**If code execution is off or the script could not be copied**, write the file yourself in exactly the format below. The first line must be `---`, and the frontmatter is one `key: value` per line (no line breaks inside values). Omit the `area`, `confidence`, and `now` lines when they do not apply.

```
---
type: insight-result
version: 1
title: <제목>
date: YYYY-MM-DD
area: <life|career>
confidence: <hunch|likely>
now: <지금 생각 한 줄>
said: <사용자 말 한 줄>
---

## 보충 (LLM)
<덧붙일 내용, 없으면 비움>

## 연결
- [[제목]] — 관계
```

The title must not contain `/`, `\`, `[`, `]`, `|`, or `#`, must not start with `.`, and must be at most 100 characters. A new title needs `area` and `now`.

## 5. Deliver the result file

Commit the file to the repository's **default branch** as `chat/inbox/<날짜>-<제목>.insight.md` through the GitHub connection. The commit message is `chat: <날짜> insight <제목>`.

If the commit fails (no permission, no connection, rejected), attach the file for download and tell the user: "저장소의 `chat/inbox/`에 이 파일을 넣어 주세요. 다음 `insight.py sync`가 가져갑니다."

Then tell the user: "위키에는 다음 `insight.py sync` 때 반영됩니다. Claude Code에서 바로 넣으려면 `/wiki-insight import <파일>`을 쓰세요."
