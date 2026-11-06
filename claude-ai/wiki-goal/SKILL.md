---
name: wiki-goal
description: Set learning goals for the personal LLM wiki in claude.ai chat. Turn the stated goals into goal maps (weighted areas, concepts, prerequisites), decide whether they become one map, several maps, or an addition to an existing map, validate them, and commit each map as a TOML file under goals/ in the wiki repository. Instructions are read from GitHub at run time. Use for requests like "/wiki-goal", "set a study goal", "I want to prepare for an exam", or "plan what to study for X".
---

# wiki-goal loader

This skill holds no instructions. The instructions live on the `main` branch of the public repository `Doggy-Footprint/llm-wiki-plugin` and are read from there on every use, so this zip does not need to be re-uploaded when the instructions change.

- Instruction file: `skills/wiki-goal/claude-ai.md`
- Scripts: `skills/wiki-goal/goal.py`, `skills/wiki-goal/index.py` (`goal.py` imports `index.py`)

Talk with the user in Korean.

## 1. Read the instructions

Read the instruction file and follow only its instructions. Read other files it points to (for example `skills/wiki-goal/SKILL.md`) from the same repository. All paths are relative to the repository root.

Read files in this order:
- Through the GitHub connection, read the file from repository `Doggy-Footprint/llm-wiki-plugin`, branch `main`.
- If that fails, open `https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<path>` on the web.
- If both fail, tell the user the instructions cannot be read and stop. Do not proceed from memory or guesses.

Do not reread a file already read in the same conversation.

## 2. Scripts

When the instruction file says to use a script in `<script dir>`, download the scripts above in code execution, once only. `<script dir>` is `/tmp/llm-wiki`.

```
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/goal.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-goal/goal.py \
  && curl -fsSL -o /tmp/llm-wiki/index.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-goal/index.py
```

If code execution is off or the download fails, follow the instruction file's "If code execution is off ..." procedure.

## 3. Wiki repository

This public repository holds only instructions. The user's wiki (`goals/`) is the GitHub repository `Doggy-Footprint/LLM-wiki` (default branch `master`). The "repository" the instruction file refers to is that repository; use another one only when the user names it in the prompt.
