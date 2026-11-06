---
name: wiki-learn
description: Learn concepts from a newsletter, article, or quiz question in claude.ai chat. List the concepts in the text, mark which ones the personal LLM wiki already knows, pick one, diagnose and teach it, run a final test with new questions, then commit a result file to the wiki repository. Instructions are read from GitHub at run time. Use for requests like "/wiki-learn", "learn from this newsletter", "study the concepts in this text", or "test me on this quiz question".
---

# wiki-learn loader

This skill holds no instructions. The instructions live on the `main` branch of the public repository `Doggy-Footprint/llm-wiki-plugin` and are read from there on every use, so this zip does not need to be re-uploaded when the instructions change.

- Instruction file: `skills/wiki-learn/claude-ai.md`
- Scripts: `skills/wiki-add/learn.py`

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
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/learn.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-add/learn.py
```

If code execution is off or the download fails, follow the instruction file's "If code execution is off ..." procedure.

## 3. Wiki repository

This public repository holds only instructions. The user's wiki (`chat/deck.md`, `chat/inbox/`) is the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`). The "repository" the instruction file refers to is that repository; use another one only when the user names it in the prompt.
