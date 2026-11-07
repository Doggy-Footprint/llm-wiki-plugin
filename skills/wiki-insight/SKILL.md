---
name: wiki-insight
description: Record a realization about life patterns, ways of working, or career as an insight page titled as a question. Find an existing page on the same question, ask whether the thinking changed, then create the page or append the change to it. Use for requests like "/wiki-insight", "/wiki-insight followed by a realization", "keep this as an insight", or "/wiki-insight import result file" (importing a result file made in claude.ai chat).
disable-model-invocation: true
---

# wiki-insight: keep a realization as a question-titled insight page

Talk with the user and write page content in Korean. Korean headings and quoted phrases below are literal strings; write them exactly as given.

An insight page (`type: insight`) holds one question about the user and how their answer changes:
- a title phrased as a question, not a conclusion (e.g. "아침 커피와 집중", not "커피가 집중을 높인다");
- "지금 생각": the current thinking in one or two sentences, in the user's words; rewritten when the thinking changes;
- "생각의 변화": append-only dated lines of what the user said;
- `confidence`: `hunch` (감), `likely` (꽤 믿음), or `tested` (only when "근거" holds script or experiment results);
- `status: obsolete` pages are never updated by this skill.

Pages live in `<root>/wiki/life/insights/` or `<root>/wiki/career/insights/`; the template is `<root>/templates/insight.md`, or the built-in `insight.md` next to this file.

## (a) Settle the wiki root

1. Run `uv run "<skill dir>/../wiki-add/learn.py" env` (`python3` if `uv` is missing; `<skill dir>` is the "Base directory" Claude Code reports when this skill loads) and take `mode`, `root`, and `has_wiki`. If the wiki-add skill is not installed alongside, use `git rev-parse --show-toplevel` as `root`, `local` as `mode`, and whether `<root>/wiki/index.md` exists as `has_wiki`.
2. If `mode` is `chat`, this is a claude.ai chat, or commands cannot run, do not follow this file; follow only `claude-ai.md`.
3. If `has_wiki` is false, tell the user that `root` holds no wiki and stop. Do not look for a wiki elsewhere.

Every command below passes `--root <root>`. The tool is `uv run "<skill dir>/insight.py" --root <root> <subcommand> ...` (standard library only, so `python3` works too). It prints one line of JSON; on failure, a message on stderr and exit code 2.

## (b) `/wiki-insight import <file>`

If the argument is `import <file>`, run only `insight.py --root <root> import <file>` with no dialogue and report the result (`page`, `created`, `changes`). Then go to (f).

## (c) Hear the realization

- Take the realization from the argument or the conversation; if there is none, ask for it once.
- A realization is a pattern the user noticed about themselves ("~하더라", "이제 알겠다"). If it is only an event or a fact, say so and stop.
- Keep the user's sentence verbatim as `said`. Do not polish it.

## (d) Find the same question

- Search existing insights: `uv run "<skill dir>/../wiki-goal/index.py" --root <root> search "<핵심어>" --type insight --k 5`. If that fails, read `<root>/chat/insights.md` if it exists. Do not open `status: obsolete` pages unless the user asks.
- If a page asks the same question, open it and compare with its "지금 생각". If they differ, ask: "예전엔 ~라고 하셨는데 바뀐 건가요?" Only if the user says it changed, set a new `now` and, if their certainty changed, a new `confidence`.
- If none matches, draft a new page: a question title, `area` (`life` or `career`), `now`, and `confidence` (default `hunch`).

## (e) Confirm and write

Show the title, area (new pages), 지금 생각, the 생각의 변화 line (`- 날짜: 사용자 말`), confidence, and links (`[[제목]] — 관계`, only pages that exist or concepts worth a page). Write nothing before the user confirms. Then run:

```
uv run "<skill dir>/insight.py" --root <root> result "<제목>" --said "<사용자 말>" --out <임시 폴더> \
  [--area life|career] [--now "<지금 생각>"] [--confidence hunch|likely] \
  [--supplement "<보충 (LLM)>"] [--link "[[제목]] — 관계"] --date YYYY-MM-DD
uv run "<skill dir>/insight.py" --root <root> import <path from result>
uv run "<skill dir>/insight.py" --root <root> deck
```

`import` creates or updates the page, its line in `wiki/index.md` (under the heading containing `(life/insights/)` or `(career/insights/)`), and one line in `wiki/log.md`. `deck` refreshes `chat/insights.md`, which claude.ai chat reads. Set `confidence: tested` by hand only after "근거" holds script or experiment results.

If the claim can be checked with recorded metrics (for example caffeine and focus), suggest turning it into an experiment.

## (f) Commit

Follow (k) of `../wiki-add/SKILL.md` with the `root` and `mode` from (a), adding the files `import` and `deck` reported (`page`, `wiki/index.md`, `wiki/log.md`, `chat/insights.md`). The commit message is `insight: <date> <제목>`.
