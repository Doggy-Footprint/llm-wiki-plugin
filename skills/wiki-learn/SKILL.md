---
name: wiki-learn
description: Learn concepts from a newsletter, article, or quiz question. List the concepts in the text, mark which ones the wiki already knows, pick one, then run the wiki-add skill's diagnose and teach flow plus a final test with new questions, and record the result on the wiki concept page. Use for requests like "/wiki-learn", "learn from this newsletter", "study the concepts in this text", or "test me on this quiz question".
disable-model-invocation: true
---

# wiki-learn: pick a concept from a newsletter or quiz, study it, and record it

This is a thin front end for `/wiki-add`. Only concept selection and the final test happen here; diagnosis, level judgment, teaching, and recording use `../wiki-add/SKILL.md` and `../wiki-add/learn.py` unchanged. The tool is `uv run "<skill dir>/../wiki-add/learn.py" <subcommand> ...` (`<skill dir>` is the "Base directory" Claude Code reports when this skill loads). To keep token cost down, do not open whole wiki pages; look only at `related` results.

Talk with the user in Korean. Korean list formats below are literal output shown to the user.

## (a) Check the environment

Run `uv run "<skill dir>/../wiki-add/learn.py" env` and use its `root`. Add `--root <root>` to every later command.
- If `mode` is `chat`, if commands cannot run, or if this is a claude.ai chat, do not follow this file; follow only `claude-ai.md`.
- Handle `has_wiki` = false the same way as (a) of `../wiki-add/SKILL.md`.

## (b) Take the input

The input is a newsletter or quiz text already in the conversation or pasted by the user. If it is a file path or an `http(s)://` URL, fetch it with `learn.py fetch` as in (b) of `../wiki-add/SKILL.md` and read the converted copy once.

If the input is a **quiz question**, have the user answer first, before listing concepts. Give neither hints nor the answer. After receiving the answer, go to (c), and count that answer as one diagnostic question in (d).

## (c) List and pick concepts

Extract **at most 7** concepts worth learning from the input. For each, run `uv run "<skill dir>/../wiki-add/learn.py" --root <root> related "<concept>" --limit 1`, and show one line per concept. `related` ranks by keyword matches in the body too, so treat the concept as known only when the returned title is that concept.
- If the wiki has it: `- 개념 — 아는 개념 (제목, level N)`
- If not: `- 개념 — 새 개념`

Let the user pick one. Do not explain anything before they pick. Work on one concept at a time, and when it is done, ask whether to continue with the rest of the list.

## (d) From diagnosis to teaching

Follow (c)-(f) of `../wiki-add/SKILL.md`: finding the starting point, diagnostic questions in Bloom order, SOLO level judgment by answer structure, and level-matched dialogue. But judge the level more strictly than (e) of `../wiki-add/SKILL.md`, because judging content the user does not know as known, just because the terms sound familiar, keeps the user from managing their knowledge accurately.
- When the user brings up another concept (a term, technique, or name) in an answer, check that they know it by having them explain it in their own words or give an example. Do not use an answer that leans on an unconfirmed concept as evidence for a level; treat that concept as a missing prerequisite. Leave prerequisites not filled in this session under `## 다음 학습` as 덜 이해함.
- Do not raise the level just because a term was used correctly. Raise it only when signals of the next level show in the user's own words, and choose the lower level when the judgment is split.
- Use the wiki's existing `level` and claims of "I know it" only as a starting point, never as evidence.
- Address misconceptions as soon as they appear, and remember them.

## (e) Final test

When teaching is done, test with **2-3 new questions**.
- Use only questions that do not overlap the earlier diagnostic questions or the examples used while teaching.
- Pitch them at the apply and analyze levels of revised Bloom (use in a new situation, comparison or cause analysis, counterexamples).
- Ask one at a time and give no hints. Even when the user is wrong, give the correct answers only after the test ends.
- **Re-judge** the level from these answers by the strict criteria of (d). For the evidence, quote one thing the user said.
- If a point where the user got stuck in the test is due to another concept, add that concept to the `## 다음 학습` candidates (덜 이해함).

## (f) Record and wrap up

Continue with (g), (h), (i), and (k) of `../wiki-add/SKILL.md`: get confirmation before writing (do not run `record` before confirmation), fill the body, record with `record`, and commit. Before the commit in (k), do one more thing.

1. Run `uv run "<skill dir>/../wiki-quiz/quiz.py" --root <root> deck` to refresh `chat/deck.md` (only when the `wiki-quiz` skill is installed alongside; otherwise skip).
2. Add `chat/deck.md` to `git add`. The commit message keeps the `add:` prefix.

When `/wiki-add import <file>` is needed (a `.learn.md` made in claude.ai), follow (j) of `../wiki-add/SKILL.md`.
