---
name: llm-wiki
description: Personal LLM wiki study tools whose instructions are read from GitHub at run time. Covers studying a keyword, file, or URL with SOLO-level diagnosis (add), learning concepts from a newsletter, article, or quiz question (wiki-learn), spaced-repetition review and exploration quizzes over the wiki (quiz), and any other tool listed in the repository's claude-ai/skills.md. Use for requests like "/add", "/wiki-learn", "/quiz", "let's study this", "learn from this newsletter", "test me on this quiz question", "quiz me", "review what I studied", or "explore a random concept".
---

# llm-wiki 로더

이 skill에는 도구별 지시가 없다. 지시는 공개 저장소 `Doggy-Footprint/llm-wiki-plugin`의 `main` 브랜치에 있고, 쓸 때마다 거기서 읽는다. 그래서 이 zip은 다시 올리지 않아도 최신 지시를 따른다.

## 1. 지시 읽기

1. `claude-ai/skills.md`를 읽고 요청에 맞는 도구 하나를 고른다. 맞는 도구가 없거나 둘 이상이면 목록을 보여 주고 묻는다.
2. 그 도구의 지시 파일을 읽고 그 지시만 따른다. 지시 파일이 가리키는 다른 파일(예: `skills/add/SKILL.md`)도 같은 저장소에서 읽는다. 경로는 모두 저장소 root 기준이다.

파일은 이 순서로 읽는다.
- GitHub 연결로 저장소 `Doggy-Footprint/llm-wiki-plugin`, 브랜치 `main`의 파일을 읽는다.
- 안 되면 `https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<경로>`를 웹에서 연다.
- 둘 다 안 되면 지시를 읽을 수 없다고 알리고 멈춘다. 기억이나 추측으로 진행하지 않는다.

같은 대화에서 이미 읽은 파일은 다시 읽지 않는다.

## 2. 스크립트

지시 파일이 `<스크립트 폴더>`의 스크립트를 쓰라고 하면, 코드 실행에서 그 도구의 스크립트를 처음 한 번만 내려받는다. `<스크립트 폴더>`는 `/tmp/llm-wiki`다.

```
mkdir -p /tmp/llm-wiki && curl -fsSL -o /tmp/llm-wiki/<파일 이름> \
  https://raw.githubusercontent.com/Doggy-Footprint/llm-wiki-plugin/main/<스크립트 경로>
```

코드 실행이 꺼져 있거나 내려받지 못하면 지시 파일의 "코드 실행이 꺼져 있으면" 절차를 따른다.

## 3. 위키 저장소

이 공개 저장소는 지시만 담는다. 사용자의 위키(`chat/deck.md`, `chat/inbox/`)는 다른 저장소이고, 지시 파일대로 사용자의 프롬프트에 적힌 저장소를 쓴다.
