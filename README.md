# llm-wiki

키워드·파일·URL을 주면 LLM이 진단 질문으로 이해 수준을 가늠하고, 그 수준에 맞게 대화하며 가르친다. 끝나면 개념 페이지에 이해 수준(SOLO 0~4)과 근거, 오개념을 기록한다. 위키는 Obsidian 형식(`[[링크]]`, 평평한 frontmatter)이고, 자료 변환은 [markitdown](https://github.com/microsoft/markitdown)이 한다.

## 설치 (Claude Code)

```
/plugin marketplace add Doggy-Footprint/claude-plugins
/plugin install llm-wiki@doggy-footprint
```

[uv](https://docs.astral.sh/uv/)가 필요하다. skill이 `uv run learn.py ...`로 도구를 실행하며, markitdown은 처음 실행할 때 자동으로 설치된다.

## 사용

```
/llm-wiki:wiki-add 트랜잭션 격리 수준
/llm-wiki:wiki-add ~/Downloads/paper.pdf
/llm-wiki:wiki-add https://example.com/article
/llm-wiki:wiki-add import 2026-11-07-인덱스.learn.md
```

- 위키가 없는 폴더에서는 만들어도 되는지 묻고 `wiki/`, `raw/`를 만든다. 위키 위치는 `--root`, 환경 변수 `LLM_WIKI_ROOT`, git 최상위 순으로 정한다.
- 원본은 `raw/YYYY/MM/`에 복사하고 변환본(`.md`)과 `raw/MANIFEST.csv`를 남긴다. 같은 자료를 다시 주면 새로 만들지 않는다.
- 페이지는 `wiki/study/<제목>.md`에 만든다. 대화 전문은 저장하지 않는다.
- 페이지의 `## 다음 학습`에는 공부 중에 나왔지만 덜 이해한 개념과 이어서 볼 개념을 `- [[개념]] — 덜 이해함: 이유` / `- [[개념]] — 이어서: 이유`로 남긴다. 아직 페이지가 없는 항목은 `wiki-quiz explore`의 후보가 된다.
- 이 저장소의 템플릿을 쓰려면 위키 root에 `templates/concept.md`를 둔다. 없으면 내장 템플릿을 쓴다.

## wiki-learn: 뉴스레터·퀴즈에서 개념 공부

```
/llm-wiki:wiki-learn            # 대화에 있는(또는 붙여 넣은) 뉴스레터·퀴즈 글
/llm-wiki:wiki-learn ~/Downloads/newsletter.pdf
```

글에서 개념을 최대 7개 뽑아 위키에 있는 개념(제목, level)과 새 개념으로 나눠 보여 준다. 하나를 고르면 `/wiki-add`와 같은 진단·교육을 하고, 끝에 처음 묻지 않은 문제 2~3개로 마지막 테스트를 한 뒤 수준을 다시 판정해 기록한다. 퀴즈 문제가 입력이면 힌트 없이 먼저 답하게 한다. `skills/wiki-add/`도 함께 있어야 한다.

## quiz: 복습과 탐색 퀴즈

```
/llm-wiki:wiki-quiz                  # review: 복습 시점이 된 개념 5개
/llm-wiki:wiki-quiz explore          # 위키가 링크만 걸어 둔 개념(연결, 다음 학습) 중에서
/llm-wiki:wiki-quiz explore random   # 위키에 없는 개념 아무거나
/llm-wiki:wiki-quiz cram             # 기록하지 않는 연습
```

복습 일정은 [FSRS](https://github.com/open-spaced-repetition/py-fsrs)(`fsrs==6.3.2`, 목표 기억률 0.9)로 `data/reviews.csv`를 재생해 계산한다. 페이지에는 복습 필드를 쓰지 않는다. 답은 again/hard/good/easy로 채점해 확인을 받은 뒤 `quiz.py record`가 `data/reviews.csv`에 줄을 더한다. 한 번도 퀴즈를 보지 않은 페이지는 `created` 날짜에 good으로 한 번 공부한 것으로 친다. 시작할 때 `quiz.py sync`를 실행한다.

### chat/ 교환

claude.ai 채팅은 위키 저장소에 접근할 수 있을 때 아래 두 경로로 주고받는다.

- `chat/deck.md`: `quiz.py deck`(`record`·`sync`도 갱신)이 만드는 요약 카드 모음. 채팅은 위키 상태를 이 파일로만 읽는다. 구간마다 개수가 제한된다 (due 10, frontier 10).
- `chat/insights.md`: `insight.py deck`(`sync`도 갱신)이 만드는 insight 목록 (`status: obsolete` 제외). wiki-insight 채팅은 이 파일만 읽는다.
- `chat/inbox/`: 채팅이 결과 파일(`*.quiz.md`, `*.learn.md`, `*.insight.md`)을 커밋하는 곳. `quiz.py sync`가 `.quiz.md`·`.learn.md`를, `insight.py sync`가 `.insight.md`를 가져와 반영하고 지운다. 가져오기에 실패한 파일은 남는다. 이 폴더는 git에 추적되어야 한다 (`.gitkeep`).

## wiki-goal: 학습 목표를 목표 지도로

```
/llm-wiki:wiki-goal SQLD 합격
/llm-wiki:wiki-goal 조인과 집계 쿼리를 혼자 짤 수 있게
```

목표를 듣고 기존 목표와 합칠지 나눌지 정한 뒤, 영역(비중)·개념·선수 관계가 있는 목표 지도 `goals/<id>.toml`을 만든다 (형식은 `skills/wiki-goal/example.toml`). 쓰기 전에 확인을 받고 `goal.py check`로 검증한다. 위키에 노트가 있으면 `suggest`가 개념마다 후보 노트를 찾고, 사용자가 맞다고 한 것만 `data/goal_links.csv`에 기록한다. 끝에 `start`가 지금 공부할 개념을 추천한다.

- 노트 검색은 SQLite 키워드 색인(`<root>/.cache/`)이다. `OPENAI_API_KEY`(환경 변수나 위키 root의 `.env`)가 있으면 임베딩 검색을 더한다. 모델과 차원은 위키 root `config.toml`의 `[embedding]`(`model`, `dim`)으로 바꾼다. 로컬 모델을 쓰려면 `[embedding]`에 `command`(문자열 배열, 첫 원소가 `/`를 포함한 상대 경로면 위키 root 기준)를 둔다. 그러면 OpenAI 대신 이 명령을 위키 root에서 실행해 stdin으로 `{"model", "dim", "texts"}` JSON을 주고 stdout의 `{"vectors": [[...], ...]}` JSON을 받는다(0이 아닌 종료 코드는 실패, stderr 마지막 줄이 오류 메시지가 된다).
- `[embedding] skip_types`(기본 `["insight"]`)의 type 페이지는 임베딩하지 않아 외부 API로 보내지 않고 키워드로만 찾는다. 로컬 임베더를 쓰면 `skip_types = []`로 모든 페이지를 임베딩할 수 있다. `search --type <type>`(반복 가능)은 결과를 그 type으로 거르고, 요청한 type이 모두 `skip_types`에 들면 검색어도 임베딩하지 않는다. 결과에는 페이지의 `type`, `status`가 붙고 `status: obsolete`는 뒤로 밀린다. `suggest`는 `type: concept` 페이지만 후보로 넣는다.
- `goal.py`의 하위명령: `list`, `check`, `suggest`, `confirm`, `reject`, `coverage`, `start`, `overlap`. `index.py`는 `build`, `embed`, `search`, `plist`(macOS launchd로 매일 색인·임베딩, 출력에 이 파일의 절대 경로가 들어가므로 플러그인을 업데이트하면 다시 만든다).

## wiki-insight: 깨달음을 질문 제목의 페이지로

```
/llm-wiki:wiki-insight 아침에 커피 마시면 오전엔 집중이 잘 되더라
/llm-wiki:wiki-insight import 2026-11-07-아침-커피와-집중.insight.md
```

삶의 패턴·일하는 방식·커리어에 대한 깨달음을 결론이 아닌 질문 제목(`type: insight`)의 페이지로 `wiki/life/insights/`나 `wiki/career/insights/`에 남긴다. 같은 질문의 페이지가 있으면 "지금 생각"과 비교해 생각이 바뀌었는지 묻고, 바뀌었으면 "지금 생각"을 고쳐 쓰고 `confidence`(hunch·likely)를 바꾼다. "생각의 변화"에는 날짜와 사용자 말을 덧붙이기만 한다. `status: obsolete` 페이지는 고치지 않는다. 템플릿은 위키 root의 `templates/insight.md`, 없으면 내장 `skills/wiki-insight/insight.md`.

- `insight.py`의 하위명령: `result`(결과 파일 `*.insight.md` 생성), `import <파일>`(페이지·`wiki/index.md`·`wiki/log.md` 반영, 같은 파일을 다시 넣어도 바뀌지 않음), `sync`(`chat/inbox/*.insight.md`를 가져오고 성공한 파일을 지운 뒤 `deck`), `deck`(`chat/insights.md` 생성). 표준 라이브러리만 쓴다.
- index 줄은 `(life/insights/)`나 `(career/insights/)`가 들어간 제목 아래에 넣는다. 그런 제목이 없으면 `## 생활 깨달음 (life/insights/)`·`## 커리어 깨달음 (career/insights/)`를 `## 지난 생각` 앞(없으면 끝)에 만든다.
- 결과 파일은 `confidence: tested`를 받지 않는다. tested는 "근거"에 스크립트·실험 결과가 있을 때 직접 고친다.

## Claude 앱 Code 탭 (클라우드 세션)

클라우드 세션은 플러그인을 설치하지 않고 저장소의 `.claude/skills/`만 읽는다. 위키 저장소에 이 플러그인의 `skills/wiki-add/`, `skills/wiki-learn/`, `skills/wiki-quiz/`, `skills/wiki-goal/`, `skills/wiki-insight/`을 `.claude/skills/` 아래로 복사해 커밋해 두면 `/wiki-add`, `/wiki-learn`, `/wiki-quiz`, `/wiki-goal`, `/wiki-insight`가 동작한다.

모든 wiki- skill은 `disable-model-invocation: true`라서 사용자가 `/wiki-…`로 부를 때만 실행되고, 에이전트에게는 보이지 않는다. claude.ai 로더는 업로드 검증이 이 키를 받지 않아 넣지 않는다.

- 결과를 기본 브랜치에 바로 올리려면 저장소 root에 `llm-wiki.toml`을 둔다. 없으면 세션 브랜치에 push한다.
  ```toml
  [add]
  cloud_push = "default-branch"   # 또는 "session-branch"
  ```
  기본 브랜치에 rebase 충돌이 나면 `git rebase --abort` 후 세션 브랜치에 올리고 충돌 파일을 알려 준다.
- URL 자료는 환경 네트워크가 제한되어 있으면 내려받지 못한다. 환경 설정에서 네트워크를 Full 또는 Custom으로 바꾸거나, 본문을 붙여 넣는다.

## claude.ai 채팅 (웹·모바일)

claude.ai에는 도구마다 로더 skill을 하나씩 올린다: `wiki-add`, `wiki-goal`, `wiki-insight`, `wiki-learn`, `wiki-quiz`. 로더에는 지시가 없고, 쓸 때마다 이 저장소 `main`의 `skills/<도구>/claude-ai.md`를 읽어 그대로 따른다. 그래서 지시를 고쳐도 이 저장소에 반영되면 다시 올릴 필요가 없다.

1. [Releases](https://github.com/Doggy-Footprint/llm-wiki-plugin/releases)에서 `wiki-add.zip`, `wiki-goal.zip`, `wiki-insight.zip`, `wiki-learn.zip`, `wiki-quiz.zip`을 받는다 (직접 만들려면 `python scripts/build_zip.py`, 출력은 `dist/<도구>.zip`).
2. PC 웹 claude.ai의 Settings → Capabilities(또는 Skills)에서 zip 다섯 개를 하나씩 업로드한다. 예전에 올린 `llm-wiki` 로더는 지운다 (같은 요청에 둘 다 반응한다). 업로드한 skill은 모바일 앱에서도 쓸 수 있다.
3. 채팅에서 "/wiki-add 주제", "/wiki-learn", "이 뉴스레터로 공부하자", "/wiki-quiz", "/wiki-goal SQLD 준비", "/wiki-insight 회의는 짧을수록 낫더라"처럼 말한다. 로더에 적힌 위키 저장소(`Doggy-Footprint/LLM-wiki`)의 `chat/deck.md`를 읽고 `chat/inbox/`에 커밋한다. wiki-goal은 `goals/` 목록만 읽고 검증한 `goals/<id>.toml`을 기본 브랜치에 바로 커밋한다. 노트 연결(`suggest`)은 채팅에서 하지 않으므로 Claude Code에서 `/wiki-goal <id> 노트 연결`로 한다. wiki-insight는 `chat/insights.md`만 읽고 `chat/inbox/`에 `.insight.md`를 커밋한다. 다른 위키 저장소를 쓰려면 프롬프트에 적거나 로더의 3절을 고친다.
4. 결과 파일은 `chat/inbox/`에 커밋되거나, 커밋할 수 없으면 내려받게 한다. Claude Code에서 `/wiki-add import <파일>`, `/wiki-insight import <파일>`, `quiz.py sync`, `insight.py sync`로 가져온다.

- 지시 파일은 GitHub 연결로 읽고, 안 되면 `raw.githubusercontent.com`에서 읽는다. 둘 다 안 되면 멈춘다.
- 코드 실행이 켜져 있으면 로더가 그 도구의 스크립트(`learn.py`, `quiz.py`, `goal.py`와 `index.py`, `insight.py`)를 `raw.githubusercontent.com`에서 내려받아 결과 파일을 만든다. 코드 실행이 꺼져 있거나 네트워크가 막혀 내려받지 못하면 같은 형식의 텍스트를 직접 쓴다.
- 새 도구를 추가할 때: `skills/<도구>/claude-ai.md`와 로더 `claude-ai/<도구>/SKILL.md`를 쓴다. 테스트가 두 목록이 맞는지 확인한다. 새 도구의 zip은 한 번 올려야 한다.
- 로더(`claude-ai/<도구>/SKILL.md`)나 그 description을 바꿨을 때만 그 도구의 zip을 다시 올린다.

## 개발

```
PYTHONPATH=skills/wiki-add:skills/wiki-quiz:skills/wiki-goal:skills/wiki-insight:scripts uv run --no-project --with pytest --with pytest-cov \
  --with 'markitdown[pdf,docx,pptx]==0.1.9' --with fsrs==6.3.2 \
  python -m pytest tests --cov=learn --cov=quiz --cov=build_zip --cov=goal --cov=index --cov=insight --cov-branch --cov-fail-under=90
```

main에 push하면 GitHub Actions가 테스트를 돌리고, `plugin.json`의 `version`에 해당하는 `v<version>` 태그가 없을 때만 로더 zip(`wiki-add.zip`, `wiki-goal.zip`, `wiki-insight.zip`, `wiki-learn.zip`, `wiki-quiz.zip`)을 Release로 올린다. claude.ai는 지시를 `main`에서 바로 읽으므로 지시만 바뀐 변경은 버전을 올리지 않아도 반영된다.

## 라이선스

MIT
