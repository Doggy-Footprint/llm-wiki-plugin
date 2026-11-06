# Review and exploration quizzes in claude.ai chat

This is the procedure for claude.ai chat. The wiki lives in a GitHub repository; this chat reads only `chat/deck.md` there. Do not open pages. Upload the result as one file under `chat/inbox/`. Use the repository named in the user's prompt; if none, the one named in the loader skill. Ask first only when neither names one.

Talk with the user in Korean. Quoted messages below are said to the user as written.

## 1. Read

- Read `chat/deck.md` through the GitHub connection. Then look only at the file list of the `chat/inbox/` folder.
- If there is a `chat/inbox/*.quiz.md` dated on or after the deck's top `generated:` date, open it and drop the pages it lists from this review (they were already answered and are not yet reflected in the wiki).
- If the deck is missing or `generated:` is more than 3 days older than today, tell the user and continue. Add that an old deck may have an out-of-date schedule.

## 2. Mode

Let the user choose. The default is `review`.

- **review**: from the deck's `## Due`, after the exclusion above, ask about the top 5 items (up to 10 if the user wants).
- **explore**: by default, pick one from `## Frontier`. If the user says "아무거나" or "랜덤", pick any concept not among the deck's `## Known` titles. A topic the user picks also works.
- **cram**: practice with pages the user picks or with the due list. Do not create a result file.

## 3. Questions and grading

For review, use only the `level`, `summary`, `mine`, `misconceptions`, and `links` written in the deck for each item.

- Ask one question at a time, only one, one Bloom step above the level. L0-1: explain it; L2: reasons and relations; L3: apply to a new case; L4: counterexamples and trade-offs.
- If there is a recorded misconception, ask a question that touches it first.
- Ask follow-up questions only after a wrong answer.
- Grade by these criteria:
  - again: wrong, or repeats a recorded misconception
  - hard: right only with a hint, or only partly right
  - good: explained correctly in their own words
  - easy: right and extends it or carries it into another area
  - not graded: the user does not reply, or replies without attempting an answer to the question (for example, says they do not know, skips it, or changes the subject). Leave the item out of the result.
- Give hints only when the user asks.

For explore, ask one pretest question, explain briefly, and offer to study the concept in depth with `wiki-learn`. Nothing is recorded.

## 4. Create the result

Collect the grades of the graded items, show them, and get confirmation. Do not create the file before confirmation. If no item was graded, create no file and commit nothing. For concepts graded again in review, suggest studying them with `/wiki-learn` or `/wiki-add`.

**If code execution is on**, create it with `<script dir>/quiz.py`. `<script dir>` is the folder where the loader skill downloaded this script.

```
python3 "<script dir>/quiz.py" result --out /mnt/user-data/outputs --date YYYY-MM-DD \
  wiki/study/예시.md=good wiki/study/다른예시.md=again
```

The `path` in the output JSON is the created file.

**If code execution is off or the script could not be downloaded**, write it yourself in exactly the format below. The file name is `<날짜>-<HHMMSS>.quiz.md`. The first line must be `---`.

```
---
type: quiz-result
version: 1
id: chat-<날짜>T<HHMMSS>
date: YYYY-MM-DD
mode: review
source: chat
---
- wiki/study/예시.md | good
- wiki/study/다른예시.md | again
```

Use the page path exactly as the deck's `path:` value. The rating is one of again, hard, good, easy.

## 5. Deliver

Commit the file to the repository's **default branch** as `chat/inbox/<file name>` through the GitHub connection. The commit message is `quiz: <날짜> <개수>개`.

If the commit fails, attach the file for download and tell the user: "저장소의 `chat/inbox/`에 이 파일을 넣어 주세요. 다음 `/daily`나 `quiz.py sync`가 가져갑니다."
