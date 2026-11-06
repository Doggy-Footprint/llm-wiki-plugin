---
name: wiki-goal
description: Set learning goals for the personal LLM wiki in claude.ai chat. Turn the stated goals into goal maps (weighted areas, concepts, prerequisites), decide whether they become one map, several maps, or an addition to an existing map, validate them, and commit each map as a TOML file under goals/ in the wiki repository. Instructions are read from GitHub at run time. Use for requests like "/wiki-goal", "set a study goal", "I want to prepare for an exam", or "plan what to study for X".
---

# wiki-goal 로더

이 skill에는 지시가 없다. 지시는 공개 저장소 `Doggy-Footprint/llm-wiki-plugin`의 `main` 브랜치에 있고, 쓸 때마다 거기서 읽는다. 그래서 지시가 바뀌어도 이 zip은 다시 올리지 않아도 된다.

- 지시 파일: `skills/wiki-goal/claude-ai.md`
- 스크립트: `skills/wiki-goal/goal.py`, `skills/wiki-goal/index.py` (`goal.py`가 `index.py`를 import한다)

## 1. 지시 읽기

지시 파일을 읽고 그 지시만 따른다. 지시 파일이 가리키는 다른 파일(예: `skills/wiki-goal/SKILL.md`)도 같은 저장소에서 읽는다. 경로는 모두 저장소 root 기준이다.

파일은 이 순서로 읽는다.
- GitHub 연결로 저장소 `Doggy-Footprint/llm-wiki-plugin`, 브랜치 `main`의 파일을 읽는다.
- 안 되면 `https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<경로>`를 웹에서 연다.
- 둘 다 안 되면 지시를 읽을 수 없다고 알리고 멈춘다. 기억이나 추측으로 진행하지 않는다.

같은 대화에서 이미 읽은 파일은 다시 읽지 않는다.

## 2. 스크립트

지시 파일이 `<스크립트 폴더>`의 스크립트를 쓰라고 하면, 코드 실행에서 위의 스크립트를 처음 한 번만 내려받는다. `<스크립트 폴더>`는 `/tmp/llm-wiki`다.

```
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/goal.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-goal/goal.py \
  && curl -fsSL -o /tmp/llm-wiki/index.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-goal/index.py
```

코드 실행이 꺼져 있거나 내려받지 못하면 지시 파일의 "코드 실행이 꺼져 있거나" 절차를 따른다.

## 3. 위키 저장소

이 공개 저장소는 지시만 담는다. 사용자의 위키(`goals/`)는 GitHub 저장소 `Doggy-Footprint/LLM-wiki`(기본 브랜치 `master`)다. 지시 파일이 말하는 "저장소"는 이 저장소이고, 사용자가 프롬프트에 다른 저장소를 적었을 때만 그것을 쓴다.
