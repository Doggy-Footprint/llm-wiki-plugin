---
name: wiki-quiz
description: Quiz the user on their wiki. Review mode asks about concept pages that are due under spaced repetition and records the graded answers; explore mode asks a pretest question about a missing or random concept and offers wiki-learn; cram mode practices without recording. Use for requests like "/wiki-quiz", "quiz me", "review what I studied", "quiz me on something new", or "explore a random concept".
disable-model-invocation: true
---

# wiki-quiz: review quizzes and new-concept exploration

The tool is `uv run "<skill dir>/quiz.py" --root <root> <subcommand> ...` (`<skill dir>` is the "Base directory" Claude Code reports when this skill loads). Output is one line of JSON; on failure it prints a message to stderr and exits with code 2. For `root`, use the `root` from `uv run "<skill dir>/../wiki-add/learn.py" env` (the git top level if the add skill is absent). If `mode` is `chat` or this is a claude.ai chat, do not follow this file; follow only `claude-ai.md`.

Talk with the user in Korean.

Keep token cost down. **Do not open** pages. The only content a question may use is the summary, 내가 정리한 것, misconceptions, and links that `card` returns. `data/reviews.csv` decides the review schedule. Reviewing and grading write nothing to pages; only `sync` imports `.learn.md` results into pages.

## 0. Start

First run `quiz.py --root <root> sync`. It imports the result files that claude.ai chat uploaded to `chat/inbox/`: `.quiz.md` files go into `data/reviews.csv`, `.learn.md` files are imported into wiki pages through `wiki-add`'s `learn.py` (the `learn` list in the output holds those pages), imported files are deleted from `chat/inbox/`, and `chat/deck.md` is rebuilt. If `failed` in the output is non-empty (exit code 1), tell the user the reasons. It is fine to continue.

Pick the mode from what the user said. If they said nothing, use `review`.

## 1. review (default)

1. Run `due --limit 5`. If the user wants more, raise it up to 10. If `items` is empty, tell the user there is nothing to review today and suggest explore. If `warnings` is non-empty, mention it briefly.
2. For each item, run `card <path>`. Do not open the page file.
3. Ask **one question**, one Bloom step above the `level`.
   - L0-1 (or no level): explain it in their own words
   - L2: why it is so, how it connects to other concepts
   - L3: apply it to a new case
   - L4: counterexamples, limits, trade-offs
4. If `misconceptions` holds a recorded misconception, ask a question that touches it **first**.
5. Ask **follow-up questions only after a wrong answer**. If the answer is right, grade it right away. Give hints only when the user asks.
6. Grading criteria:
   - `again`: wrong, or repeats a recorded misconception
   - `hard`: right only with a hint, or only partly right
   - `good`: explained correctly in their own words
   - `easy`: right and extends it or carries it into another area
   - Not graded: the user does not reply, or replies without attempting an answer to the question (for example, says they do not know, skips it, or changes the subject). Leave the item out of `record`.
7. When all items are done, show a `제목 → rating` table of the graded items and **get confirmation**. If no item was graded, skip steps 7-8: nothing is recorded. Do not run `record` before confirmation. If the user corrects anything, apply it.
8. After confirmation, run `record [--date D] <page>=<rating> ...` (the page is the `path` from `due`). This command appends rows to `data/reviews.csv` and rebuilds `chat/deck.md`.
9. For concepts graded `again`, suggest studying them with `/wiki-learn` or `/wiki-add`. Grading does not edit pages.

## 2. explore

1. By default, run `frontier` and pick one of the concepts the wiki only links to from `## 연결` or `## 다음 학습` and that has no page yet. You may let the user choose which.
2. Pick at random only when the user says **random**. Then pick any concept that is not in the `## Known` list (`chat/deck.md`) or in `wiki/index.md`.
3. Ask **one pretest question**. After the answer, explain briefly.
4. Suggest continuing with `/wiki-learn`. explore records nothing (neither `record` nor `data/reviews.csv`).

## 3. cram

Practice with pages the user picks or with the `due` list. Questions and grading are the same as review, but nothing is recorded (do not run `record`).

## 4. Commit

Do this only when `root` is a git repository and `record` ran in this session, that is, the user answered at least one quiz question (right or wrong). Do not commit when the user received questions but did not answer them or did not attempt an answer, nor for explore or cram; changes left by `sync` alone are committed later by `/daily`.

1. `git add data/reviews.csv chat/`, plus, if `sync` imported `.learn.md` files, the pages in its `learn` list and `wiki/index.md` and `wiki/log.md`. Do not use `git add -A`.
2. `git commit -m "quiz: <date> <개수>개 복습"`. If the repository's rules require `Request:`/`Intent:` lines, add them.
3. Do not push. In a cloud session, follow (k) of `../wiki-add/SKILL.md`.

Finally, briefly report the rating for each graded title.
