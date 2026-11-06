---
name: wiki-add
description: Study a keyword, file, or URL, or take in a short piece of knowledge the user just learned (a sentence or two from a lecture or article), through dialogue. Ask diagnostic questions to gauge understanding on the SOLO scale (0-4), teach at that level, then record the level, evidence, and misconceptions on the wiki concept page. Use for requests like "/wiki-add keyword", "/wiki-add file path or URL", "/wiki-add followed by a sentence the user learned", "let's study this", "I learned this today, put it in the wiki", "explain this and record my understanding level", or "/wiki-add import result file" (importing a result file made in claude.ai chat).
disable-model-invocation: true
---

# wiki-add: check what the user knows through dialogue and record it in the wiki with an understanding level

This skill records **how well** the user knows a concept on its concept page. The input is one of three kinds.
- Keyword: the name of a topic to study.
- Material: a file path or an `http(s)://` URL.
- Fragment: a sentence or two the user has already learned. It may mix facts they heard with their own inferences from those facts.

The flow is the same for every input: find the starting point → diagnose → judge the level → level-matched dialogue → confirm → record. The input kind changes only where the diagnosis starts. Treat a fragment as the user's first answer, and ask only about what that sentence does not show.

Talk with the user in Korean and write page content in Korean. Korean headings, markers, and quoted phrases below are literal strings that the scripts and existing pages use; write them exactly as given.

The tool is `uv run "<skill dir>/learn.py" <subcommand> ...`. `<skill dir>` is the "Base directory" Claude Code reports when this skill loads. Output is one line of JSON; on failure it prints a message to stderr and exits with code 2 (bad input) or 3 (conversion or download failure).

Keep token cost down. Read a material once, as its converted copy, and open only the top 3 `related` wiki pages. Never save the full conversation anywhere.

## (a) Check the environment

First run `uv run "<skill dir>/learn.py" env` (returns `mode`, `root`, `has_wiki`, `cloud_push`).
- If `uv` is missing, run `python3 "<skill dir>/learn.py" env` instead (`env` uses only the standard library).
- If `mode` is `chat`, if no command can run at all, or if this is a claude.ai chat, do not follow this file; follow only `claude-ai.md`.
- If `has_wiki` is false, ask the user whether a new wiki may be created at `root`, and run `init` if they agree. If they decline, hold the dialogue without recording.
- Add `--root <root>` to every later command.

## (j) `/wiki-add import <file>`

If the argument is `import <file>`, run only `import <file>` with no dialogue and report the result (`page`, `created`, `previous_level`, `level`, `sections_added`, `changed`). Then go to (k).

## (b) Read the input

- **Material** (file path, URL): run `fetch <material> --date today --slug <short-name>`.
  - The return value has no body text. Read the `md` file **once**. If `outline` is not null (the file is long), look at the outline only and read just the needed ranges with `offset`/`limit`. Do not reread.
  - If `duplicate_of` is set, the material was already fetched. Nothing new was created; read the returned `md`. If the user says they uploaded a new version, tell them it matched an already-fetched copy, so it was not fetched again. If `md` is null (the converted copy is missing), tell the user and ask them to paste the text.
  - Code 2 is a path or address error, code 3 is a conversion failure. Relay the message as is and stop.
  - If `mode` is `cloud` and a URL fails with code 3, tell the user: "환경 네트워크를 Full 또는 Custom으로 바꾸거나, 본문을 붙여 넣어 주세요." Use pasted text as the material, but do not put it in `sources`.
- **Keyword**: there is nothing to read. Go to (c).
- **Fragment**: do not `fetch`. Split the sentence into claims and mark each one as one of two kinds.
  - 들은 것 (heard): a fact the lecture or article stated. Note its source with it. If the user did not give one, ask once; if they do not know, leave it blank.
  - 내 추론 (my inference): a conclusion, prediction, or extension to another area that the user drew from that fact.

  Show the split one line per claim and have the user confirm it. Use this split as is for the judgment in (e) and the page body in (h).

## (c) Find the starting point

Run `related <keyword or title> --limit 3`. Open only those (at most 3) pages, read their existing `level`, `## 이해 기록`, and `## 오해와 교정`, and use them as the starting point. If a page for the same concept exists, pass its title unchanged to `record`. Otherwise it is a new page.

For a fragment, search by the name of the sentence's core concept. A page title is a concept name, not a sentence. A fragment is usually one piece of a concept that already exists, so if a page for the same concept exists, merge into it instead of creating a new one. If one sentence spans two concepts, record it on the main concept and put the other under `## 연결` in (h).

## (d) Diagnostic questions

Before explaining anything, ask questions **one at a time**, climbing the revised Bloom order: remember → understand → apply → analyze.
- Remember: "X가 뭔지 아는 대로 말해 줘."
- Understand: "X를 처음 듣는 친구에게 자기 말로 설명해 본다면?"
- Apply: "이런 상황이면 X를 어떻게 쓰겠어?"
- Analyze: "X와 Y는 어디가 같고 어디가 달라? 어떤 경우에 깨져?"

Have the user explain in their own words first, and do not give the answer right away even when they are wrong. If an answer stalls, stop climbing. If a page already exists, skip questions below the level it already confirms.

The number of questions depends on the input.
- Keyword or material: 2-4.
- Fragment: 1-2. Count the fragment itself as the first answer and do not re-ask a step it already shows. If it states a single fact, ask "왜 그렇지?" (understand). If it links cause and effect, ask for an application or a counterexample (analyze). In particular, ask where the "내 추론" part could break. If it looks copied verbatim from the lecture, first ask the user to explain it again in their own words.

## (e) Judge the level

Judge the level by the **structure of the answers**, not by a self-assessment like "I know it" (SOLO). A fragment is also an answer and is judged on the same table. Words copied verbatim from a lecture count only as evidence for remember (L1); raise the level above that only when there is an answer that re-explains or applies the idea in the user's own words.

| level | SOLO name | signals in the answer |
|---|---|---|
| 0 | 전구조적 | Says they do not know, or says something unrelated. Uses the term with a different meaning |
| 1 | 단일구조적 | States only one definition or fact. Cannot give an example or a reason |
| 2 | 다중구조적 | Lists several facts but no relations or reasons between them |
| 3 | 관계적 | Connects them by cause and effect, comparison, or reason, and applies them to a new case |
| 4 | 확장추상적 | Generalizes to other areas and raises counterexamples, limits, or trade-offs unprompted |

Take the evidence as one line from what the user actually said. When the judgment is split, choose the lower level and ask one more confirming question.

If a "들은 것" claim is factually wrong or a "내 추론" claim overgeneralizes, keep it as a misconception candidate and address it in (f). Do not assume a fragment is correct because it is short.

## (f) Level-matched dialogue

- L0-1: start from intuition and concrete examples. Point out one or two missing prerequisite concepts and explain them one at a time.
- L2: questions and explanations that connect the pieces the user already knows. Ask "왜 그렇지?".
- L3: pose application problems. Let the user solve them and give hints only when they are stuck.
- L4: discuss comparisons, counterexamples, limits, and correspondences with other fields.
- Address a misconception as soon as it appears: ask why they might have thought so, then correct it. Remember it for (g).
- When the user answers well at the current level during the dialogue, move up to the next step. One thing at a time.
- Remember next-study candidates: concepts that came up but the user could not explain in their own words (덜 이해함, not yet understood), and concepts worth studying after this one (이어서, next). Do not explain concepts outside the current one at length; just keep them as candidates.
- For a fragment, the user usually wants to record it quickly. Talk only as much as misconception correction and level confirmation need, then ask the user whether to study further. If not, move what is left into the next-study candidates.

## (g) Re-judge and confirm

At the end, judge the level again. Then, **before writing**, show the following and get confirmation. Do not run `record` before confirmation.
- Page title (merging into an existing page or a new page), previous level → new level (SOLO name)
- One line of evidence, misconceptions and corrections (if any), a one-sentence summary (for a new page)
- The gist of "내가 정리한 것" and "보충 (LLM)" for the page, and the new links to add
- Next-study items (덜 이해함 / 이어서, each with a short reason)

If the user corrects anything, apply it and show it again.

## (h) Page body rules

Open the `page` that `record` returned and fill it by these rules. Do not edit `level`, `## 이해 기록`, or `## 오해와 교정` directly (only `learn.py` writes them).
- `## 내가 정리한 것`: only what the user said or what the material contains. Do not mix in your own knowledge. For a fragment, keep the split from (b) and append `(내 추론)` to the end of each "내 추론" sentence. When merging into an existing page, do not just append sentences at the end: merge duplicate statements into one and reorganize the section so it reads continuously with the existing content. If something contradicts the existing content, do not delete it; mark it and tell the user.
- `## 보충 (LLM)`: your own knowledge, written with vocabulary and depth matched to the judged level.
- For a prerequisite concept that has no page, write only a link under `## 연결` as `[[개념]] — 관계`. Create that concept's page only if the user agrees (with the same procedure, via `record`).
- `## 다음 학습`: one item per line, either `- [[개념]] — 덜 이해함: <막힌 지점>` or `- [[개념]] — 이어서: <다음에 볼 이유>`. Keep it to 5 lines or fewer, and remove existing items that this dialogue resolved. Items without a page become candidates for `/wiki-quiz explore`.
- `## 출처`: write a source that has no `raw/` file (lecture name and session, article title) as one line, `- <출처> (사용자 말, YYYY-MM-DD)`.
- Replace template placeholder lines (lines in parentheses) with content.

## (i) Record

After confirmation, run:

```
uv run "<skill dir>/learn.py" --root <root> record "<제목>" --level N --evidence "<근거>" \
  [--summary "<한 문장>"] [--misconception "<오개념과 교정>"] [--source <raw/... 경로> ...] [--date D]
```

- `--summary` is required for a new page. If a material was fetched, pass the `raw` (or `md`) that `fetch` returned as `--source`. Do not pass `--source` for a fragment or a keyword; write the source in the body as (h) says.
- If `changed` is false, the same content is already there. Tell the user so.
- Then fill the body as (h) says. Do not save the full conversation.

## (k) Commit and push

Do this only when `root` is a git repository (`git -C <root> rev-parse --show-toplevel`).

1. `git add` only the files that `record`/`import`/`fetch` reported this time and the page whose body you filled: the `page` from `record`, `wiki/index.md`, `wiki/log.md`, `raw/MANIFEST.csv`, and the archived `raw/...` files. Leave out paths for which `git check-ignore -q <path>` succeeds (ignored paths), and do not use `git add -A`.
2. `git commit -m "add: <date> <제목>"`. If the repository's rules require `Request:`/`Intent:` lines, add them.
3. The rest depends on `mode`.
   - `local`: commit only. Do not push.
   - `cloud` with `cloud_push` = `session-branch`: `git push -u origin HEAD` to the current session branch.
   - `cloud` with `cloud_push` = `default-branch`: get the default branch name `<B>` from `git symbolic-ref --short refs/remotes/origin/HEAD` (strip `origin/`). Then
     ```
     git fetch origin <B>
     git rebase origin/<B>
     git push origin HEAD:<B>
     ```
     If `rebase` conflicts, save the list of conflicting files from `git status` and run `git rebase --abort`. Then push to the session branch with `git push -u origin HEAD`, and tell the user that the default branch was not updated, along with the conflicting files. If the push is rejected (`non-fast-forward`), repeat `fetch`/`rebase` once only.
4. Finally report: title, level change, files created or changed, and where it was pushed.
