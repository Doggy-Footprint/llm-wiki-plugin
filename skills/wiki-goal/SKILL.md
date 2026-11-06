---
name: wiki-goal
description: Set learning goals as goal maps (TOML files under goals/) with weighted areas, concepts, and prerequisites. Decide whether the stated goals become one map, several maps, or an addition to an existing map, then validate with goal.py, link existing wiki notes, and show where to start. Use for requests like "/wiki-goal", "set a study goal", "I want to prepare for an exam", "make a learning goal", or "plan what to study for X".
---

# wiki-goal: 학습 목표를 목표 지도로 설정

목표 지도는 위키 root의 `goals/<id>.toml`이다. 형식 검증은 `goal.py`의 `load_goal`이 한다. 도구는 `uv run "<skill 폴더>/goal.py" --root <root> <하위명령>`이다 (`<skill 폴더>`는 이 skill이 로드될 때 Claude Code가 알려 주는 "Base directory"). 출력은 JSON 한 줄, 실패하면 stderr 메시지와 종료 코드 2다. `root`는 `uv run "<skill 폴더>/../wiki-add/learn.py" env`의 `root`를 쓴다 (add skill이 없으면 git 최상위). `mode`가 `chat`이거나 claude.ai 채팅이면 이 파일을 따르지 말고 `claude-ai.md`만 따른다.

토큰 비용을 지킨다. 기존 목표는 `list`와 `check`의 출력으로만 보고, toml 파일은 고칠 때만 연다. 위키 페이지는 열지 않는다. 목표 지도는 `wiki/`를 바꾸지 않는다.

이미 있는 지도의 노트 연결만 요청받으면 (claude.ai 채팅에서 만든 지도 등) `check <id>`를 실행한 뒤 (f)부터 한다.

## (a) 목표 듣기

이미 말한 것은 다시 묻지 않는다. 판단에 필요한데 빠진 것만 한 번에 하나씩 묻는다.
- 하고 싶은 것 (하나든 여럿이든 사용자가 말한 그대로)
- 완료 판단 기준 (시험 합격, 만들 결과물, 설명할 수 있어야 하는 것 등)
- 기한과 우선순위 (있으면)

## (b) 기존 목표 확인

`list`를 실행한다. 제목이나 영역이 새 목표와 겹쳐 보이는 것만 `check <id>`로 개념 목록을 본다. `errors`가 있으면 그 파일과 사유를 알린다.

## (c) 합칠지 나눌지 판단

목표 지도 하나는 **완료 판정 하나**에 대응한다.
- 하나로 합친다: 같은 기준으로 끝난다 (같은 시험, 같은 결과물). 한 목표가 다른 목표의 일부이면 큰 쪽 지도의 영역으로 넣는다. 기존 목표와 이 조건이 맞으면 새 지도를 만들지 않고 기존 지도에 영역·개념을 더한다.
- 나눈다: 완료 판정이 따로 난다 (서로 다른 시험, 공식 시험과 주관적 목표), 기한이나 우선순위가 다르다, 개념이 거의 겹치지 않는다.
- 개념이 겹친다는 이유만으로 합치지 않는다. 겹치는 개념은 지도마다 같은 이름으로 두고, 비교는 `overlap`이 한다.

판단 결과를 목표마다 한 줄로 보여 준다. 예: `새 지도 <id>: <이유>`, `기존 <id>에 영역 추가: <이유>`. 사용자가 바꾸면 따른다.

## (d) 지도 초안

목표마다 아래를 정한다. 형식은 `<skill 폴더>/example.toml`과 같다.
- `id`: 소문자 영숫자와 하이픈 (`^[a-z0-9]+(-[a-z0-9]+)*$`), 파일 이름과 같다. 기존 id와 겹치지 않게 한다.
- `title`, `kind`: 공식 출제기준이나 커리큘럼이 있으면 `official`, 없으면 `subjective`.
- `[source]`:
  - official: 공식 출처 `url`, 확인 날짜 `checked`, `note`(시험 형식, 공식 근거가 없는 부분). 출처는 웹에서 확인한다. 확인하지 못했으면 그 사실을 `note`에 적고 사용자에게 알린다.
  - subjective: `note`에 사용자가 말한 목표, 완료 기준, 기한을 적는다.
- `[[areas]]`: `id`, `name`, `weight`(0보다 큰 수). official은 공식 배점이나 문항 수, subjective는 사용자가 말한 우선순위를 쓴다. 우선순위를 모르면 같은 값으로 두고 그렇다고 알린다.
- `[[concepts]]`: `id`, `name`, `area`, `section`(선택), `aliases`.
  - 개념 하나는 `/wiki-add` 한 번으로 공부할 크기다. 목표 하나에 10~40개를 기준으로 하고, 벗어나면 개념을 묶거나 쪼갠다.
  - `aliases`는 노트 검색(`suggest`)에 쓰인다. 원어, 약어, 흔한 다른 표기를 넣는다.
- `[[prereqs]]`: `from`(먼저 알아야 할 개념) → `to`, `basis`는 다음 중 하나다. 순환은 안 된다.
  - `official`: 공식 자료에 근거가 있다.
  - `syllabus-order`: 공식 자료의 나열 순서만 근거다.
  - `inferred`: LLM 추론이다.
  - `user`: 사용자가 말했다.

**쓰기 전에** 목표마다 아래를 보여 주고 확인을 받는다. 확인 전에는 파일을 쓰지 않는다.
- (c)의 판단, `id`, `title`, `kind`, 출처
- 영역(비중)별 개념 이름 목록
- 선수 관계 요약 (`A → B` 줄), basis별 개수

## (e) 쓰기와 검증

확인을 받으면 `goals/<id>.toml`을 쓰거나 고친 뒤 `check <id>`를 실행한다. 종료 코드 2이면 메시지대로 고치고 다시 `check`한다.
- 기존 지도를 고칠 때 기존 개념의 `id`는 바꾸지 않는다. `data/goal_links.csv`가 개념 id로 노트를 잇는다.

## (f) 노트 연결과 시작점

1. 위키에 개념 노트가 있으면 `suggest <id>`를 실행한다. 개념마다 후보 노트(`page`, `score`)가 나온다. `warnings`가 있으면 짧게 알린다 (`OPENAI_API_KEY`가 없으면 키워드 검색만 한다). 검색 색인은 `<root>/.cache/`에 생긴다.
   - 점수 하한이 없어 관련 없는 후보도 섞인다. 경로의 제목으로 보아 그 개념을 다루는 후보만 골라 보여 준다.
   - 사용자가 맞다고 한 것은 `confirm <id> <개념id>=<page> ...`, 아니라고 한 것은 `reject <id> <개념id>=<page> ...`로 기록한다.
2. `start <id>`를 실행해 지금 시작할 개념(`items`)을 보여 주고 `/wiki-add <개념 이름>`으로 시작하자고 권한다. `blocked`는 선수 개념이 아직 `ok`가 아니라서 미룬 개념 수다.

## (g) 커밋

저장소가 git이면 커밋한다. push는 하지 않는다.
1. `git add`는 이번에 쓰거나 고친 `goals/<id>.toml`과, `suggest`·`confirm`·`reject`가 바꿨으면 `data/goal_links.csv`만 대상으로 한다. `git add -A`는 쓰지 않는다.
2. `git commit -m "goal: <date> <id 목록>"`. 저장소 규칙이 `Request:`/`Intent:` 줄을 요구하면 붙인다.
3. 마지막에 보고한다. 만들거나 고친 목표(id, 개념 수), 연결한 노트 수, 시작 추천 개념.
