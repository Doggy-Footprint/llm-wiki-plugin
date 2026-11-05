# claude.ai 채팅에서 복습·탐색 퀴즈

claude.ai 채팅에서 쓰는 방식이다. 위키는 GitHub 저장소에 있고, 이 채팅은 거기서 `chat/deck.md`만 읽는다. 페이지를 열지 않는다. 결과는 `chat/inbox/` 아래 파일 하나로 올린다. 저장소는 사용자의 프롬프트에 적힌 것을 쓰고, 없으면 로더 skill에 적힌 것을 쓴다. 둘 다 없을 때만 먼저 묻는다.

## 1. 읽기

- GitHub 연결로 `chat/deck.md`를 읽는다. 그리고 `chat/inbox/` 폴더의 파일 목록만 본다.
- deck 맨 위 `generated:` 날짜보다 같거나 늦은 날짜의 `chat/inbox/*.quiz.md`가 있으면 그 파일을 열어 적힌 페이지를 이번 복습 대상에서 뺀다 (이미 푼 것이고 아직 위키에 반영되지 않았다).
- deck이 없거나 `generated:`가 오늘보다 3일 넘게 오래됐으면 그 사실을 사용자에게 알리고 계속한다. 오래된 deck은 일정이 어긋나 있을 수 있다고 덧붙인다.

## 2. 모드

사용자가 정하게 한다. 기본은 `review`.

- **review**: deck의 `## Due`에서 위 제외를 거친 항목을 위에서부터 5개 (사용자가 원하면 최대 10개) 낸다.
- **explore**: 기본은 `## Frontier`에서 하나 고른다. 사용자가 "아무거나", "랜덤"이라고 하면 deck의 `## Known` 제목에 없는 개념을 아무거나 고른다. 사용자가 고른 주제여도 된다.
- **cram**: 사용자가 고른 페이지나 due 목록으로 연습한다. 결과 파일을 만들지 않는다.

## 3. 질문과 채점

review는 항목마다 deck에 적힌 `level`, `summary`, `mine`, `misconceptions`, `links`만 근거로 쓴다.

- 질문은 하나씩, 수준보다 Bloom 한 단계 위 하나만 낸다. L0~1은 설명하기, L2는 이유·관계, L3는 새 사례에 적용, L4는 반례·트레이드오프.
- 기록된 오해가 있으면 그것을 먼저 건드리는 질문을 한다.
- 추가 질문은 틀렸을 때만 한다.
- 채점은 아래 기준으로 한다.
  - again: 틀렸거나 비웠거나 기록된 오해를 되풀이함
  - hard: 힌트가 있어야 맞히거나 부분적으로만 맞음
  - good: 자기 말로 맞게 설명함
  - easy: 맞고 거기서 확장하거나 다른 영역으로 옮김
- 힌트는 사용자가 요청할 때만 준다.

explore는 사전 질문 하나를 던지고, 짧게 설명하고, 이 개념을 `wiki-learn`으로 깊게 공부할지 제안한다. 기록은 없다.

## 4. 결과 만들기

항목마다 매긴 점수를 모아 보여 주고 확인을 받는다. 확인 전에는 파일을 만들지 않는다. review에서 again이 나온 개념은 `/wiki-learn`이나 `/wiki-add`로 공부해 보라고 권한다.

**코드 실행이 켜져 있으면** `<스크립트 폴더>/quiz.py`로 만든다. `<스크립트 폴더>`는 로더 skill이 이 스크립트를 내려받은 폴더다.

```
python3 "<스크립트 폴더>/quiz.py" result --out /mnt/user-data/outputs --date YYYY-MM-DD \
  wiki/study/예시.md=good wiki/study/다른예시.md=again
```

출력 JSON의 `path`가 만들어진 파일이다.

**코드 실행이 꺼져 있거나 스크립트를 내려받지 못했으면** 아래 형식 그대로 직접 쓴다. 파일 이름은 `<날짜>-<HHMMSS>.quiz.md`. 첫 줄은 반드시 `---`이다.

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

페이지 경로는 deck의 `path:` 값 그대로 쓴다. rating은 again, hard, good, easy 중 하나다.

## 5. 전달

만든 파일을 저장소의 **기본 브랜치**에 `chat/inbox/<파일 이름>`으로 GitHub 연결을 통해 커밋한다. 커밋 메시지는 `quiz: <날짜> <개수>개`이다.

커밋이 실패하면 파일을 첨부해 내려받게 하고 이렇게 알린다. "저장소의 `chat/inbox/`에 이 파일을 넣어 주세요. 다음 `/daily`나 `quiz.py sync`가 가져갑니다."
