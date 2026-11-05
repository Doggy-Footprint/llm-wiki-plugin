# claude.ai 도구 목록

claude.ai에 올린 로더 skill(`llm-wiki`)이 읽는 목록이다. 도구를 추가하면 여기에 한 줄을 더한다. 경로는 저장소 root 기준이다.

| 도구 | 언제 쓰나 | 지시 파일 | 스크립트 |
| --- | --- | --- | --- |
| add | 키워드·파일·URL을 대화로 공부하고 이해 수준을 기록한다 ("/add", "공부하자", "이거 설명해 줘") | skills/add/claude-ai.md | skills/add/learn.py |
| wiki-learn | 뉴스레터·기사·퀴즈 문제에서 개념을 골라 공부하고 마지막 테스트를 본다 ("/wiki-learn", "이 뉴스레터로 공부하자", "이 퀴즈 문제 풀어 볼게") | skills/wiki-learn/claude-ai.md | skills/add/learn.py |
| quiz | 위키 복습 퀴즈, 새 개념 탐색, 기록 없는 연습을 한다 ("/quiz", "복습하자", "퀴즈 내 줘", "랜덤 개념") | skills/quiz/claude-ai.md | skills/quiz/quiz.py |
