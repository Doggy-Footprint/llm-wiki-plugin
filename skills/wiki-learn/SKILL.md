---
name: wiki-learn
description: Learn concepts from a newsletter, article, or quiz question. List the concepts in the text, mark which ones the wiki already knows, pick one, then run the wiki-add skill's diagnose and teach flow plus a final test with new questions, and record the result on the wiki concept page. Use for requests like "/wiki-learn", "learn from this newsletter", "study the concepts in this text", or "test me on this quiz question".
---

# wiki-learn: 뉴스레터·퀴즈에서 개념을 골라 공부하고 기록

`/wiki-add`의 얇은 앞단이다. 개념 고르기와 마지막 테스트만 여기서 하고, 진단·수준 판정·교육·기록은 `../wiki-add/SKILL.md`와 `../wiki-add/learn.py`를 그대로 쓴다. 도구는 `uv run "<skill 폴더>/../wiki-add/learn.py" <하위명령> ...`이다 (`<skill 폴더>`는 이 skill이 로드될 때 Claude Code가 알려 주는 "Base directory"). 토큰 비용을 지키기 위해 위키 페이지를 통째로 열지 않고 `related`의 결과만 본다.

## (a) 환경 확인

`uv run "<skill 폴더>/../wiki-add/learn.py" env`를 실행하고 그 `root`를 쓴다. 이후 모든 명령에 `--root <root>`를 붙인다.
- `mode`가 `chat`이거나 명령을 실행할 수 없거나 claude.ai 채팅이면 이 파일을 따르지 말고 `claude-ai.md`만 따른다.
- `has_wiki`가 false일 때의 처리는 `../wiki-add/SKILL.md`의 (a)와 같다.

## (b) 입력 받기

입력은 이미 대화에 있거나 사용자가 붙여 넣은 뉴스레터·퀴즈 글이다. 파일 경로나 `http(s)://` URL이면 `../wiki-add/SKILL.md`의 (b)대로 `learn.py fetch`로 가져와 변환본을 한 번만 읽는다.

입력이 **퀴즈 문제**이면 개념을 나열하기 전에 사용자가 먼저 답하게 한다. 힌트도 정답도 주지 않는다. 답을 받은 뒤에 (c)로 가고, 그 답은 (d)의 진단 질문 하나로 쳐 준다.

## (c) 개념 나열하고 고르기

입력에서 배울 만한 개념을 **최대 7개** 뽑는다. 개념마다 `uv run "<skill 폴더>/../wiki-add/learn.py" --root <root> related "<개념>" --limit 1`을 실행하고, 한 줄씩 보여 준다.
- 위키에 있으면: `- 개념 — 아는 개념 (제목, level N)`
- 없으면: `- 개념 — 새 개념`

사용자가 하나를 고르게 한다. 고르기 전에는 설명하지 않는다. 한 번에 한 개념만 진행하고, 끝나면 남은 목록에서 이어 갈지 묻는다.

## (d) 진단부터 교육까지

`../wiki-add/SKILL.md`의 (c)~(f)를 그대로 따른다. 곧 시작점 찾기, Bloom 순서의 진단 질문, 답변 구조로 하는 SOLO 수준 판정, 수준별 대화다. 오개념은 발견 즉시 짚고 기억해 둔다.

## (e) 마지막 테스트

교육이 끝나면 **새 질문 2~3개**로 시험한다.
- 앞서 던진 진단 질문이나 교육 중 설명한 예시와 겹치지 않는 질문만 쓴다.
- 개정 Bloom의 적용·분석 수준으로 낸다 (새 상황에서 쓰기, 비교·원인 분석, 반례).
- 한 번에 하나씩 묻고, 힌트를 주지 않는다. 틀려도 정답은 테스트가 끝난 뒤에 알려 준다.
- 이 답변들로 수준을 **다시 판정**한다. 근거는 사용자가 한 말 중 하나를 인용해 적는다.

## (f) 기록과 마무리

`../wiki-add/SKILL.md`의 (g)(h)(i)(k)를 이어서 따른다. 쓰기 전 확인을 받고(`record`는 확인 전에 실행하지 않는다), 본문을 채우고, `record`로 기록하고, 커밋한다. 단 (k)의 커밋 전에 한 가지를 더 한다.

1. `uv run "<skill 폴더>/../wiki-quiz/quiz.py" --root <root> deck`을 실행해 `chat/deck.md`를 갱신한다 (`wiki-quiz` skill이 함께 설치되어 있을 때. 없으면 건너뛴다).
2. `git add`에 `chat/deck.md`를 더한다. 커밋 메시지는 `add:` 접두어 그대로다.

`/wiki-add import <파일>`이 필요한 경우(claude.ai에서 만든 `.learn.md`)는 `../wiki-add/SKILL.md`의 (j)를 따른다.
