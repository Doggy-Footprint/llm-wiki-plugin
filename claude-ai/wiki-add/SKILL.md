---
name: wiki-add
description: Study a keyword, file, or URL through dialogue in claude.ai chat. Ask diagnostic questions to gauge understanding on the SOLO scale (0-4), teach at that level, then produce a result file for the personal LLM wiki. Instructions are read from GitHub at run time. Use for requests like "/wiki-add keyword", "let's study this", or "explain this and record my understanding level".
---

# wiki-add 로더

이 skill에는 지시가 없다. 지시는 공개 저장소 `Doggy-Footprint/llm-wiki-plugin`의 `main` 브랜치에 있고, 쓸 때마다 거기서 읽는다. 그래서 지시가 바뀌어도 이 zip은 다시 올리지 않아도 된다.

- 지시 파일: `skills/wiki-add/claude-ai.md`
- 스크립트: `skills/wiki-add/learn.py`

## 1. 지시 읽기

지시 파일을 읽고 그 지시만 따른다. 지시 파일이 가리키는 다른 파일(예: `skills/wiki-add/SKILL.md`)도 같은 저장소에서 읽는다. 경로는 모두 저장소 root 기준이다.

파일은 이 순서로 읽는다.
- GitHub 연결로 저장소 `Doggy-Footprint/llm-wiki-plugin`, 브랜치 `main`의 파일을 읽는다.
- 안 되면 `https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<경로>`를 웹에서 연다.
- 둘 다 안 되면 지시를 읽을 수 없다고 알리고 멈춘다. 기억이나 추측으로 진행하지 않는다.

같은 대화에서 이미 읽은 파일은 다시 읽지 않는다.

## 2. 스크립트

지시 파일이 `<스크립트 폴더>`의 스크립트를 쓰라고 하면, 코드 실행에서 위의 스크립트를 처음 한 번만 내려받는다. `<스크립트 폴더>`는 `/tmp/llm-wiki`다.

```
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/learn.py \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/skills/wiki-add/learn.py
```

코드 실행이 꺼져 있거나 내려받지 못하면 지시 파일의 "코드 실행이 꺼져 있으면" 절차를 따른다.

## 3. 위키 저장소

이 공개 저장소는 지시만 담는다. 사용자의 위키(`chat/deck.md`, `chat/inbox/`)는 다른 저장소이고, 지시 파일대로 사용자의 프롬프트에 적힌 저장소를 쓴다.
