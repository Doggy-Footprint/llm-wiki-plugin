---
name: quiz
description: Quiz the user on their wiki. Review mode asks about concept pages that are due under spaced repetition and records the graded answers; explore mode asks a pretest question about a missing or random concept and offers wiki-learn; cram mode practices without recording. Use for requests like "/quiz", "quiz me", "review what I studied", "quiz me on something new", or "explore a random concept".
---

# quiz: 복습 퀴즈와 새 개념 탐색

도구는 `uv run "<skill 폴더>/quiz.py" --root <root> <하위명령> ...`이다 (`<skill 폴더>`는 이 skill이 로드될 때 Claude Code가 알려 주는 "Base directory"). 출력은 JSON 한 줄이고 실패하면 stderr 메시지와 종료 코드 2를 준다. `root`는 `uv run "<skill 폴더>/../add/learn.py" env`의 `root`를 쓴다 (add skill이 없으면 git 최상위). `mode`가 `chat`이거나 claude.ai 채팅이면 이 파일을 따르지 말고 `claude-ai.md`만 따른다.

토큰 비용을 지킨다. 페이지를 **열지 않는다**. 질문에 필요한 내용은 `card`가 주는 요약·내가 정리한 것·오해·연결뿐이다. 복습 일정은 `data/reviews.csv`가 정하고 페이지에는 아무것도 쓰지 않는다.

## 0. 시작

먼저 `quiz.py --root <root> sync`를 실행한다. claude.ai 채팅이 `chat/inbox/`에 올린 결과 파일을 `data/reviews.csv`로 가져온다. 출력의 `failed`가 비어 있지 않으면 사유를 알린다 (종료 코드 1). 계속 진행해도 된다.

모드는 사용자가 말한 대로 정한다. 말이 없으면 `review`.

## 1. review (기본)

1. `due --limit 5`를 실행한다. 사용자가 더 원하면 10까지 올릴 수 있다. `items`가 비었으면 오늘 복습할 것이 없다고 알리고 explore를 제안한다. `warnings`가 있으면 짧게 알린다.
2. 항목마다 `card <path>`를 실행한다. 페이지 파일은 열지 않는다.
3. **질문 하나**를 낸다. 대상은 `level`보다 Bloom 한 단계 위다.
   - L0~1(또는 level 없음): 자기 말로 설명하기
   - L2: 왜 그런지, 다른 개념과 어떻게 이어지는지
   - L3: 새 사례에 적용하기
   - L4: 반례, 한계, 트레이드오프
4. `misconceptions`에 기록된 오해가 있으면 그 오해를 건드리는 질문을 **먼저** 한다.
5. **추가 질문은 틀린 뒤에만** 한다. 맞혔으면 바로 채점한다. 힌트는 사용자가 요청하거나 한 번 틀린 뒤에만 준다.
6. 채점 기준:
   - `again`: 틀렸거나 비웠거나 기록된 오해를 되풀이함
   - `hard`: 힌트가 있어야 맞히거나 부분적으로만 맞음
   - `good`: 자기 말로 맞게 설명함
   - `easy`: 맞고 거기서 확장하거나 다른 영역으로 옮김
7. 모든 항목이 끝나면 `제목 → rating` 표를 보여 주고 **확인을 받는다**. 확인 전에는 `record`를 실행하지 않는다. 사용자가 고치면 반영한다.
8. 확인을 받으면 `record [--date D] <page>=<rating> ...`을 실행한다 (페이지는 `due`가 준 `path`). 이 명령이 `data/reviews.csv`에 줄을 더하고 `chat/deck.md`를 다시 만든다.
9. `again`을 받은 개념은 `/wiki-learn`이나 `/add`로 그 개념을 공부해 보라고 권한다. 퀴즈는 페이지를 고치지 않는다.

## 2. explore

1. 기본은 `frontier`를 실행해 위키가 링크만 걸고 아직 페이지가 없는 개념 중 하나를 고른다. 어느 것이 좋은지 사용자가 정하게 해도 된다.
2. 사용자가 **랜덤**이라고 말했을 때만 무작위로 고른다. 이때는 `## Known` 목록(`chat/deck.md`)이나 `wiki/index.md`에 없는 개념을 아무거나 고른다.
3. **사전 질문 하나**를 낸다. 답을 받으면 짧게 설명한다.
4. `/wiki-learn`으로 이어서 공부할지 권한다. explore는 기록하지 않는다 (`record`도 `data/reviews.csv`도 쓰지 않는다).

## 3. cram

사용자가 고른 페이지나 `due` 목록으로 연습한다. 질문과 채점은 review와 같지만 기록하지 않는다 (`record`를 실행하지 않는다).

## 4. 커밋

`root`가 git 저장소이고 `data/reviews.csv`나 `chat/`이 바뀌었을 때만 한다 (`git status --porcelain data/reviews.csv chat`로 확인).

1. `git add data/reviews.csv chat/`만 한다. `git add -A`는 쓰지 않는다.
2. `git commit -m "quiz: <date> <개수>개 복습"`. 저장소 규칙이 `Request:`/`Intent:` 줄을 요구하면 붙인다.
3. push는 하지 않는다. 클라우드 세션이면 `../add/SKILL.md`의 (k)를 따른다.

바뀐 것이 없으면 커밋하지 않는다. 마지막에 제목별 rating을 간단히 보고한다.
