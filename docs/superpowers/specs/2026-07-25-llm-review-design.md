# 复盘页 UI + LLM 复盘设计

> 状态：已实现

## 目标

优化复盘页信息架构；支持大模型生成「大盘 + 交易日摘要 + 策略归因」复盘；Settings 开关自动；手动一键生成。

## 行为

1. **手动** `POST /api/review/generate?asof=YYYY-MM-DD`：预取事实 → 一次 LLM → upsert `reviews`
2. **自动** `REVIEW_AUTO`：交易日 15:45（北京）；无 Key / 非交易日 / **当日已有笔记则跳过**（不覆盖手改）
3. **内容**：大盘指数涨跌 + 情绪要点；纸成交/滑点；可选最近策略归因；`content` Markdown + `deviations_json`
4. **UI**：顶栏日期/生成/刷新；正文可编辑保存；执行质量与归因整理展示

## 非目标

Phase6 全量信号矩阵；不经投研 chat tools。
