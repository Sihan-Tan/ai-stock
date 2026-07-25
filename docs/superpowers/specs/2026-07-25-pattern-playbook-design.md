# 投研形态手册（知识库预检索）设计

> 状态：已实现

## 目标

把知识库中的形态/走势类笔记与书籍，接入投研对话：在启用 `pattern-playbook` skill 时自动预检索并注入上下文，再结合已有只读工具提高形态对照质量。不保证胜率；禁止编造书中没有的规则。

## 非目标

- 不新做 TA-Lib / K 线自动形态识别工具
- 不改投研精选打分路径
- 未启用该 skill 时不做预检索
- 不默认对所有对话塞知识库

## 行为

1. **新 skill** `pattern-playbook`：检索知识 → 引用原文 → 有代码时用已有只读工具 → 形态判断与失效条件。
2. **路由**：`investment-research` 增加形态/走势/K线 → `pattern-playbook`。
3. **预检索**：当 `skill_hint == pattern-playbook` 或该 skill 在启用列表中（`enabled_skills is None` 视为全部启用）时，用用户最新一条消息 `search(top_k=5)`，将命中摘要写入 system「知识库预检索」区块。
4. 检索模式遵循全局 `knowledge_retrieval`；失败/无命中不阻断对话。

## 验收

- 未启用 skill → system 无预检索区块
- 启用后提问 → system 含知识片段；回答可引用笔记
