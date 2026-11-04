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
/llm-wiki:add 트랜잭션 격리 수준
/llm-wiki:add ~/Downloads/paper.pdf
/llm-wiki:add https://example.com/article
/llm-wiki:add import 2026-11-07-인덱스.learn.md
```

- 위키가 없는 폴더에서는 만들어도 되는지 묻고 `wiki/`, `raw/`를 만든다. 위키 위치는 `--root`, 환경 변수 `LLM_WIKI_ROOT`, git 최상위 순으로 정한다.
- 원본은 `raw/YYYY/MM/`에 복사하고 변환본(`.md`)과 `raw/MANIFEST.csv`를 남긴다. 같은 자료를 다시 주면 새로 만들지 않는다.
- 페이지는 `wiki/study/<제목>.md`에 만든다. 대화 전문은 저장하지 않는다.
- 이 저장소의 템플릿을 쓰려면 위키 root에 `templates/concept.md`를 둔다. 없으면 내장 템플릿을 쓴다.

## Claude 앱 Code 탭 (클라우드 세션)

클라우드 세션은 플러그인을 설치하지 않고 저장소의 `.claude/skills/`만 읽는다. 위키 저장소에 이 플러그인의 `skills/add/`를 `.claude/skills/add/`로 복사해 커밋해 두면 `/add`가 동작한다.

- 결과를 기본 브랜치에 바로 올리려면 저장소 root에 `llm-wiki.toml`을 둔다. 없으면 세션 브랜치에 push한다.
  ```toml
  [add]
  cloud_push = "default-branch"   # 또는 "session-branch"
  ```
  기본 브랜치에 rebase 충돌이 나면 `git rebase --abort` 후 세션 브랜치에 올리고 충돌 파일을 알려 준다.
- URL 자료는 환경 네트워크가 제한되어 있으면 내려받지 못한다. 환경 설정에서 네트워크를 Full 또는 Custom으로 바꾸거나, 본문을 붙여 넣는다.

## claude.ai 채팅 (웹·모바일)

채팅에는 위키가 없으므로 zip skill로 대화하고 결과 파일을 가져온다.

1. [Releases](https://github.com/Doggy-Footprint/llm-wiki-plugin/releases)에서 `llm-wiki-add.zip`을 받는다 (직접 만들려면 `python scripts/build_zip.py`).
2. PC 웹 claude.ai의 Settings → Capabilities(또는 Skills)에서 zip을 업로드한다. 업로드한 skill은 모바일 앱에서도 쓸 수 있다. 코드 실행을 켜 두면 결과 파일을 자동으로 만들고, 꺼져 있으면 같은 형식의 텍스트를 보여 준다.
3. 채팅에서 주제를 말하면 같은 방식으로 진단·대화한 뒤 `<날짜>-<제목>.learn.md` 결과 파일을 만든다.
4. 결과 파일을 위키로 가져온다. Claude Code에서 `/add import <파일>`을 실행하거나, 위키 저장소를 쓰는 환경이면 Google Drive의 `LLM-wiki-inbox`에 저장해 `/ingest`가 가져가게 한다.

zip skill은 자동으로 업데이트되지 않는다. 새 버전은 다시 업로드한다.

## 개발

```
PYTHONPATH=skills/add:scripts uv run --no-project --with pytest --with pytest-cov \
  --with 'markitdown[pdf,docx,pptx]==0.1.9' \
  python -m pytest tests --cov=learn --cov=build_zip --cov-branch --cov-fail-under=90
```

main에 push하면 GitHub Actions가 테스트를 돌리고, `plugin.json`의 `version`에 해당하는 `v<version>` 태그가 없을 때만 zip을 Release로 올린다.

## 라이선스

MIT
