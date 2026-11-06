---
name: wiki-add
description: Study a keyword, file, or URL through dialogue. Ask diagnostic questions to gauge understanding on the SOLO scale (0-4), teach at that level, then record the level, evidence, and misconceptions on the wiki concept page. Use for requests like "/wiki-add keyword", "/wiki-add file path or URL", "let's study this", "explain this and record my understanding level", or "/wiki-add import result file" (importing a result file made in claude.ai chat).
---

# wiki-add: 대화하며 공부하고 이해 수준을 위키에 기록

도구는 `uv run "<skill 폴더>/learn.py" <하위명령> ...`이다. `<skill 폴더>`는 이 skill이 로드될 때 Claude Code가 알려 주는 "Base directory"다. 출력은 JSON 한 줄이고, 실패하면 stderr 메시지와 종료 코드(2 잘못된 입력, 3 변환·내려받기 실패)를 준다.

토큰 비용을 지킨다. 자료는 변환본으로 한 번만 읽고, 위키는 `related` 상위 3개만 연다. 대화 전문은 어디에도 저장하지 않는다.

## (a) 환경 확인

먼저 `uv run "<skill 폴더>/learn.py" env`를 실행한다 (`mode`, `root`, `has_wiki`, `cloud_push`).
- `uv`가 없으면 `python3 "<skill 폴더>/learn.py" env`로 실행한다 (`env`는 표준 라이브러리만 쓴다).
- `mode`가 `chat`이거나, 명령을 아예 실행할 수 없거나, claude.ai 채팅이면 이 파일을 따르지 말고 `claude-ai.md`만 따른다.
- `has_wiki`가 false면 사용자에게 `root`에 위키를 새로 만들어도 되는지 묻고, 동의하면 `init`을 실행한다. 거절하면 기록 없이 대화만 한다.
- 이후 모든 명령에 `--root <root>`를 붙인다.

## (j) `/wiki-add import <파일>`

인자가 `import <파일>`이면 대화 없이 `import <파일>`만 실행하고 결과(`page`, `created`, `level`, `sections_added`, `changed`)를 보고한다. 그다음 (k)로 간다.

## (b) 자료 가져오기

인자가 파일 경로나 `http(s)://` URL이면 `fetch <자료> --date today --slug <짧은-이름>`을 실행한다. 키워드면 건너뛴다.
- 반환값에는 본문이 없다. `md` 파일을 **한 번만** 읽는다. `outline`이 null이 아니면(길다) 목차만 보고 필요한 구간만 `offset`/`limit`으로 읽는다. 다시 읽지 않는다.
- `duplicate_of`가 있으면 이미 가져온 자료다. 새로 만들지 않았으니 반환된 `md`를 읽는다. 사용자가 새 버전을 올렸다고 하면 그 사실을 알린다.
- 코드 2는 경로·주소 오류, 3은 변환 실패다. 메시지를 그대로 알리고 중단한다.
- `mode`가 `cloud`인데 URL이 코드 3으로 실패하면 이렇게 안내한다. "환경 네트워크를 Full 또는 Custom으로 바꾸거나, 본문을 붙여 넣어 주세요." 붙여 넣은 본문은 자료로 쓰되 `sources`에는 넣지 않는다.

## (c) 시작점 찾기

`related <키워드 또는 제목> [--limit 3]`을 실행한다. 상위 최대 3개만 열어 기존 `level`, `## 이해 기록`, `## 오해와 교정`을 읽고 그것을 시작점으로 삼는다. 같은 개념의 페이지가 있으면 그 제목을 `record`에 그대로 쓴다. 없으면 새 페이지다.

## (d) 진단 질문

설명하기 전에 질문 2~4개를 **하나씩** 던진다. 개정 Bloom 순서로 올라간다. 기억 → 이해 → 적용 → 분석.
- 기억: "X가 뭔지 아는 대로 말해 줘."
- 이해: "X를 처음 듣는 친구에게 자기 말로 설명해 본다면?"
- 적용: "이런 상황이면 X를 어떻게 쓰겠어?"
- 분석: "X와 Y는 어디가 같고 어디가 달라? 어떤 경우에 깨져?"

먼저 자기 말로 설명하게 하고, 틀려도 답을 바로 알려 주지 않는다. 앞 답이 막히면 더 올라가지 않고 멈춘다. 기존 페이지가 있으면 이미 확인된 수준 아래 질문은 건너뛴다.

## (e) 수준 판정

수준은 "나는 안다"는 자기평가가 아니라 **답변의 구조**로 판정한다 (SOLO).

| level | 이름 | 답변에서 보이는 신호 |
|---|---|---|
| 0 | 전구조적 | 모른다고 하거나 무관한 말. 용어를 다른 뜻으로 씀 |
| 1 | 단일구조적 | 정의나 사실 하나만 말함. 예를 들거나 이유를 대지 못함 |
| 2 | 다중구조적 | 사실을 여러 개 나열하지만 서로의 관계·이유는 없음 |
| 3 | 관계적 | 원인·결과, 비교, 이유로 연결하고 새 사례에 적용함 |
| 4 | 확장추상적 | 다른 영역으로 일반화하고 반례·한계·트레이드오프를 스스로 말함 |

근거는 사용자가 실제로 한 말에서 한 줄로 뽑는다. 판단이 갈리면 낮은 쪽을 택하고 확인 질문을 하나 더 한다.

## (f) 수준별 대화

- L0~1: 직관과 구체적 예시부터. 모자란 선수 개념을 한두 개 짚고 하나씩 설명한다.
- L2: 이미 아는 조각들을 서로 연결하는 질문과 설명. "왜 그렇지?"를 묻는다.
- L3: 적용 문제를 낸다. 사용자가 풀게 하고 막힐 때만 힌트.
- L4: 비교, 반례, 한계, 다른 분야와의 대응을 놓고 토론한다.
- 오개념은 발견 즉시 짚고, 왜 그렇게 생각했을지 묻고 바로잡는다. 기억해 두었다가 (g)에 쓴다.
- 대화 중에 사용자가 수준에 맞는 답을 하면 다음 단계로 올린다. 한 번에 한 가지씩.
- 다음 학습 후보를 기억해 둔다. 대화에 나왔지만 사용자가 자기 말로 설명하지 못한 개념(덜 이해함)과, 이 개념을 이해한 뒤 이어서 볼 만한 개념(이어서)이다. 지금 다루지 않는 개념은 길게 설명하지 않고 후보로만 남긴다.

## (g) 재판정과 확인

끝에 수준을 다시 판정한다. 그리고 **쓰기 전에** 아래를 보여 주고 확인을 받는다. 확인 전에는 `record`를 실행하지 않는다.
- 페이지 제목, 이전 level → 새 level (SOLO 이름)
- 근거 한 줄, 오개념과 교정 (있을 때), 요약 한 문장(새 페이지일 때)
- 페이지에 들어갈 "내가 정리한 것"과 "보충 (LLM)" 요지, 새로 만들 연결
- 다음 학습 항목 (덜 이해함 / 이어서, 각각 이유 한 구절)

사용자가 고치면 반영하고 다시 보여 준다.

## (h) 본문 작성 규칙

`record`가 알려 준 `page`를 열어 아래 규칙으로 채운다. `level`, `## 이해 기록`, `## 오해와 교정`은 직접 고치지 않는다 (`learn.py`만 쓴다).
- `## 내가 정리한 것`: 사용자가 말했거나 자료에 있는 내용만. 내 지식을 섞지 않는다.
- `## 보충 (LLM)`: 내 지식. 판정한 수준에 맞는 어휘와 깊이로 쓴다.
- 페이지가 없는 선수 개념은 `## 연결`에 `[[개념]] — 관계`로 링크만 적는다. 그 개념의 페이지는 사용자가 동의할 때만 만든다 (같은 절차로 `record`).
- `## 다음 학습`: 한 줄에 하나, `- [[개념]] — 덜 이해함: <막힌 지점>` 또는 `- [[개념]] — 이어서: <다음에 볼 이유>`. 5줄 이내로 쓰고, 이번 대화에서 해결된 기존 항목은 지운다. 페이지가 없는 항목은 `/wiki-quiz explore`의 후보가 된다.
- 템플릿 자리표시 줄(괄호 줄)은 내용으로 바꾼다.

## (i) 기록

확인을 받으면 실행한다.

```
uv run "<skill 폴더>/learn.py" --root <root> record "<제목>" --level N --evidence "<근거>" \
  [--summary "<한 문장>"] [--misconception "<오개념과 교정>"] [--source <raw/... 경로> ...] [--date D]
```

- 새 페이지에는 `--summary`가 필수다. 자료를 가져왔으면 `fetch`가 알려 준 `raw`(또는 `md`)를 `--source`로 준다.
- `changed`가 false면 이미 같은 내용이 있다는 뜻이다. 그대로 알린다.
- 이후 (h)대로 본문을 채운다. 대화 전문은 저장하지 않는다.

## (k) 커밋과 push

`root`가 git 저장소일 때만 한다 (`git -C <root> rev-parse --show-toplevel`).

1. `git add`는 이번에 `record`/`import`/`fetch`가 알려 준 파일과 본문을 채운 페이지만 대상으로 한다. 곧 `record`가 알려 준 `page`, `wiki/index.md`, `wiki/log.md`, `raw/MANIFEST.csv`, 보관한 `raw/...` 파일이다. `git check-ignore -q <경로>`가 성공하는(무시되는) 경로는 빼고, `git add -A`는 쓰지 않는다.
2. `git commit -m "add: <date> <제목>"`. 저장소 규칙이 `Request:`/`Intent:` 줄을 요구하면 붙인다.
3. 이후는 `mode`에 따른다.
   - `local`: 커밋만 한다. push하지 않는다.
   - `cloud`이고 `cloud_push`가 `session-branch`: 현재 세션 브랜치에 `git push -u origin HEAD`.
   - `cloud`이고 `cloud_push`가 `default-branch`: 기본 브랜치 이름 `<B>`를 `git symbolic-ref --short refs/remotes/origin/HEAD`(`origin/` 제거)로 얻는다. 그다음
     ```
     git fetch origin <B>
     git rebase origin/<B>
     git push origin HEAD:<B>
     ```
     `rebase`가 충돌하면 `git status`로 충돌 파일 목록을 얻어 두고 `git rebase --abort`를 실행한다. 그다음 `git push -u origin HEAD`로 세션 브랜치에 올리고, 기본 브랜치에는 반영되지 않았다는 사실과 충돌 파일을 사용자에게 알린다. push가 거절되면(`non-fast-forward`) 한 번만 `fetch`/`rebase`를 반복한다.
4. 마지막에 보고한다. 제목, level 변화, 만들거나 바꾼 파일, push한 곳.
