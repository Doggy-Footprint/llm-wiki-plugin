# Studying from a newsletter or quiz in claude.ai chat

This is the procedure for claude.ai chat. The wiki lives in a GitHub repository; this chat reads only `chat/deck.md` there and uploads one result file to `chat/inbox/`. Read `skills/wiki-add/claude-ai.md` (dialogue and result-file rules) and `skills/wiki-add/SKILL.md` (diagnosis and level criteria) in this plugin as well. A `skills/<name>/...` path in this file is a file of this plugin's `<name>` skill; this skill's own files are next to this file, in `<this folder>`. wiki-add's files are in the `wiki-add` folder next to `<this folder>`. If it is not there, find it with `find / -path '*/wiki-add/learn.py' -not -path '/proc/*' 2>/dev/null`; if it cannot be found, tell the user that this plugin's wiki-add skill is missing and stop.

Talk with the user in Korean. Korean list formats and quoted messages below are shown to the user as written.

## 0. Repository

Use the repository named in the user's prompt; if none, the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`).

## 1. Input and concept selection

- The input is a newsletter or quiz text that appeared earlier in this chat, or text the user pasted.
- If the input is a quiz question, have the user answer first, before listing concepts. Give neither hints nor the answer.
- To tell whether a concept is already known, read only the `## Known` list in the repository's `chat/deck.md` (through the GitHub connection). Do not open other pages. If it cannot be read, ask the user whether they studied the concept before and at what level.
- Extract **at most 7** concepts from the input and show one line each: `- 개념 — 아는 개념 (제목, L수준)` or `- 개념 — 새 개념`. The user picks one. Do not explain anything before they pick.

## 2. Dialogue and final test

Follow sections 1-3 of `skills/wiki-add/claude-ai.md`: diagnostic questions, SOLO judgment by answer structure, level-matched dialogue, confirmation, and creating the result file. But judge the level **more strictly** than there (judging content the user does not know as known, just because the terms sound familiar, keeps the user from managing their knowledge accurately), and add a **final test** before confirmation.

- When the user brings up another concept (a term, technique, or name) in an answer, check that they know it by having them explain it in their own words or give an example. Do not use an answer that leans on an unconfirmed concept as evidence for a level; treat that concept as a missing prerequisite. Leave prerequisites not filled in this session under the result file's `## 다음 학습` as 덜 이해함.
- Do not raise the level just because a term was used correctly. Raise it only when signals of the next level show in the user's own words, and choose the lower level when the judgment is split. Use the existing level in `chat/deck.md` and claims of "I know it" only as a starting point.
- When teaching is done, test with 2-3 new questions. Make them not overlap earlier questions or the examples used, and pitch them at the apply and analyze levels of revised Bloom. Ask one at a time and give no hints. Give the correct answers only after the test ends.
- Re-judge the level from these answers by the same strict criteria, quoting one thing the user said as evidence. If a point where the user got stuck in the test is due to another concept, add that concept to 다음 학습 (덜 이해함). Run the confirmation step (section 2 of `skills/wiki-add/claude-ai.md`) with that judgment.

## 3. Deliver the result file

After confirmation, create the `.learn.md` (section 3 of `skills/wiki-add/claude-ai.md`) and commit it to the repository's **default branch** as `chat/inbox/<file name>` through the GitHub connection. The commit message is `chat: <날짜> <제목>`.

If the commit fails (no permission, no connection, rejected), attach the file for download and tell the user: "저장소의 `chat/inbox/`에 이 파일을 넣어 주세요. 다음 `/daily`나 `quiz.py sync`가 가져갑니다."

To import it directly in Claude Code, `/wiki-add import <file>` also works.
