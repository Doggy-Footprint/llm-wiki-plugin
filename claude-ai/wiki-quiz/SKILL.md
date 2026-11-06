---
name: wiki-quiz
description: Quiz the user on their personal LLM wiki in claude.ai chat. Review mode asks about concept pages that are due under spaced repetition, explore mode asks a pretest question about a missing or random concept, and cram mode practices without recording. Instructions are read from GitHub at run time. Use for requests like "/wiki-quiz", "quiz me", "review what I studied", "quiz me on something new", or "explore a random concept".
---

# wiki-quiz loader

This skill holds no instructions. The instructions live on the `main` branch of the public repository `Doggy-Footprint/llm-wiki-plugin` and are read from there on every use, so this zip does not need to be re-uploaded when the instructions change.

- Instruction file: `skills/wiki-quiz/claude-ai.md`
- Scripts: `skills/wiki-quiz/quiz.py`

Talk with the user in Korean.

## 1. Read the instructions

Read the instruction file and follow only its instructions. Read other files it points to (for example `skills/wiki-add/SKILL.md`) from the same repository. All paths are relative to the repository root.

Read files in this order:
- Through the GitHub connection, read the file from repository `Doggy-Footprint/llm-wiki-plugin`, branch `main`.
- If that fails, open `https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<path>` on the web.
- If both fail, tell the user the instructions cannot be read and stop. Do not proceed from memory or guesses.

Do not reread a file already read in the same conversation.

## 2. Scripts

When the instruction file says to use a script in `<script dir>`, download the scripts above in code execution, once only. `<script dir>` is `/tmp/llm-wiki`.

```
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/quiz.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-quiz/quiz.py
```

If code execution is off or the download fails, follow the instruction file's "If code execution is off ..." procedure.

## 3. Wiki repository

This public repository holds only instructions. The user's wiki (`chat/deck.md`, `chat/inbox/`) is the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`). The "repository" the instruction file refers to is that repository; use another one only when the user names it in the prompt.
