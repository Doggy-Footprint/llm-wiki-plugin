---
type: concept
created: 2026-01-06
updated: 2026-01-08
level: 1
tags: [sql, 분석]
aliases: [window function, 분석 함수]
sources: []
---
# 윈도우 함수

## 요약
행 집합을 줄이지 않고 각 행에 대해 순위나 누적 값을 계산하는 함수.

## 내가 정리한 것
OVER 절에 PARTITION BY와 ORDER BY를 쓴다. RANK, DENSE_RANK, ROW_NUMBER가 대표적이다.

## 보충 (LLM)
프레임 절(ROWS BETWEEN)로 계산 범위를 정한다.

## 오해와 교정
- GROUP BY처럼 행을 합치는 것이 아니다.
