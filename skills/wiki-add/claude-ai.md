# Studying in claude.ai chat

A claude.ai chat has neither the wiki nor the repository. Diagnose and talk the same way, then produce the result as **one file** for the user to download. That file is brought into the wiki later (`/wiki-add import <file>`). A `skills/<name>/...` path in this file is a file of this plugin's `<name>` skill; this skill's own files are next to this file, in `<this folder>`.

Talk with the user in Korean and write the result file in Korean. Korean headings, markers, and quoted phrases below are literal strings that the import script and existing pages use; write them exactly as given.

## 1. Dialogue

Use the same criteria as (c)-(h) of `skills/wiki-add/SKILL.md`, except do not use `env`, `fetch`, `related`, `record`, or the git steps.
- Starting point: the wiki cannot be opened, so ask the user whether they studied this topic before and at what level. If they do not know, start at L0.
- Material: read a file the user uploaded or text they pasted once. If it is long, look at its outline first and read only the needed parts.
- Fragment (a sentence or two the user learned): split it into 들은 것 (heard) and 내 추론 (my inference) and have the user confirm, as in (b) of `skills/wiki-add/SKILL.md`. Name the title after the core concept, not the sentence.
- Ask diagnostic questions one at a time in revised Bloom order (remember → understand → apply → analyze): 2-4 for a keyword or material; for a fragment, count the fragment as the first answer and ask 1-2 (see (d) of `skills/wiki-add/SKILL.md`). Have the user explain in their own words first.
- Judge SOLO 0-4 by the structure of the answers, not by self-assessment (table in (e) of `skills/wiki-add/SKILL.md`). Follow (f) for level-matched dialogue as well. Address misconceptions right away.
- Do not save the full conversation. Put only the organized content in the result file.

## 2. Confirm

At the end, judge the level again, show the following, and get confirmation. Do not create the file before confirmation.
- Title (concept name), level (SOLO name), a one-sentence summary, one line of evidence, misconceptions and corrections (if any)
- 내가 정리한 것 (only what the user said; append `(내 추론)` to each "내 추론" sentence of a fragment and `(출처: <강의·글>)` to each "들은 것" sentence), 보충 (LLM) (matched to the level), and links (`[[개념]] — 관계` lines)
- 다음 학습 (lines of `[[개념]] — 덜 이해함: <막힌 지점>` or `[[개념]] — 이어서: <다음에 볼 이유>`, 5 lines or fewer). 덜 이해함 is a concept that came up in the dialogue but the user could not explain in their own words; 이어서 is a concept worth studying after this one.

## 3. Create the result file

**If code execution is on**, create it with `<script dir>/learn.py`. `<script dir>` is `/tmp/llm-wiki`. Before the first run, copy the script there once: `mkdir -p /tmp/llm-wiki && cp "<this folder>/learn.py" /tmp/llm-wiki/`. Pass the content arguments exactly as confirmed.

```
python3 "<script dir>/learn.py" result "<제목>" --level N --summary "<요약>" --evidence "<근거>" \
  --out /mnt/user-data/outputs [--misconception "<오개념>"] --mine "<내가 정리한 것>" \
  --supplement "<보충>" --link "[[개념]] — 관계" --next "[[개념]] — 덜 이해함: <막힌 지점>" --date YYYY-MM-DD
```

Repeat `--link` and `--next` once per line. The `path` in the output JSON is the created file. For `--out`, use a downloadable folder (or the current folder if there is none). Attach the file for download. Use today's date as `YYYY-MM-DD`.

**If code execution is off or the script could not be copied**, write the file yourself in exactly the format below, show it, and tell the user to save it as `<날짜>-<제목>.learn.md`. The first line must be `---`, and the frontmatter is one `key: value` per line (no line breaks inside values; omit the `misconception` line entirely if there is none).

```
---
type: learn-result
version: 1
title: <제목>
date: YYYY-MM-DD
level: <0~4>
summary: <요약 한 줄>
evidence: <근거 한 줄>
misconception: <오개념과 교정 한 줄>
---

## 내가 정리한 것
<사용자 말>

## 보충 (LLM)
<수준에 맞춘 보충>

## 연결
- [[관련 개념]] — 관계

## 다음 학습
- [[개념]] — 덜 이해함: <막힌 지점>
- [[개념]] — 이어서: <다음에 볼 이유>
```

The title must not contain `/` or `\`, must not start with `.`, and must be at most 100 characters. level is an integer from 0 to 4.

## 4. Explain how to bring it into the wiki

After creating the file, tell the user:
- If they save it in the Google Drive folder `LLM-wiki-inbox`, the next `/ingest` or `/daily` brings it into the wiki.
- Or they can run `/wiki-add import <file>` in Claude Code.
