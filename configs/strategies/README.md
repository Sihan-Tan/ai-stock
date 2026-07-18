# 策略配置

## Python 注册（主路径）

来源：`packages/strategy/desk_strategy/strategies/`  
同步：策略页「同步策略」或 `POST /api/strategies/sync-python`

| ID | 名称 | 来源对照（CASE-AI） |
|----|------|---------------------|
| `ma_cross` | 双均线-日线(5/20) | `double_ma` / 日线双均线 |
| `macd_1d` | MACD·日K线 | `macd_1d` |
| `ma20_hold` | MA20持股法 | `ma20_hold` |
| `boll_revert` | 布林带均值回归 | `boll_revert` |
| `bias_revert` | 乖离率均值回归 | `bias_revert` |
| `rsi_reversion` | RSI反转 | walk_forward `rsi` |
| `turtle_donchian` | 海龟唐奇安通道 | `turtle_donchian` |
| `grid_classic` | 经典网格60日 | `grid_classic`（日线无状态版） |
| `multi_factor_lite` | 多因子轻量 | `multi_factor_top` 绝对阈值版 |

## 未迁移（依赖分钟/全市场/ML）

- `macd_5min` / `dual_ma_5min`：需分钟回测馈源
- `dragon_picker`：需量比与全市场截面
- `ml_prob`：依赖 CASE `ml_strategy` 滚动训练栈

## YAML

`breakout.yaml` 仍可通过「同步策略」或 YAML 编辑器加载。
