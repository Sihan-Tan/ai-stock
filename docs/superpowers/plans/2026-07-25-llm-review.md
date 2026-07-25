# LLM 复盘 Implementation Plan

**Goal:** 复盘页 UI 优化 + LLM 生成（大盘/交易/归因）+ REVIEW_AUTO 15:45 + 手动生成

## Tasks
1. `desk_review/generate.py` 预取 + LLM + upsert；单测 mock LLM
2. Settings `review_auto` + store/patch/UI/.env.example
3. `POST /api/review/generate`；scheduler 15:45
4. Rewrite `Review.tsx`
