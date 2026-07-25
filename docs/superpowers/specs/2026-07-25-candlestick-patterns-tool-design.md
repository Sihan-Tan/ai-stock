# 投研 TA-Lib K 线形态工具

> 状态：已确认设计（用户选 1+2：全量命中 + 可筛选）

## 目标

投研只读工具 `get_candlestick_patterns`：对本地日线计算 TA-Lib 全部/筛选 CDL 形态，供 `pattern-playbook` 与知识库对照。

## 参数

- `symbol` 必填
- `lookback_bars` 默认 30，钳制 5–120
- `patterns` 可选：`CDL*` / 去前缀名 / 中文短名；空=全部 61
- `only_hits` 默认 true

## 返回

`{ symbol, engine, lookback_bars, patterns_used, hits: [{date, name, name_zh, value}], hit_count, note }`  
无 TA-Lib / 无日线 → `{error: ...}`

## Skill

`pattern-playbook`：有代码时先调本工具，再对照知识库。
