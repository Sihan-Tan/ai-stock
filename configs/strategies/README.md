# 策略配置

## Python 注册（主路径）

来源：`packages/strategy/desk_strategy/strategies/`  
同步：策略页「同步策略」或 `POST /api/strategies/sync-python`

| ID | 名称 | 来源对照（CASE-AI） | 周期 |
|----|------|---------------------|------|
| `ma_cross` | 双均线-日线(5/20) | `double_ma` / 日线双均线 | 1d |
| `macd_1d` | MACD·日K线 | `macd_1d` | 1d |
| `ma20_hold` | MA20持股法 | `ma20_hold` | 1d |
| `boll_revert` | 布林带均值回归 | `boll_revert` | 1d |
| `bias_revert` | 乖离率均值回归 | `bias_revert` | 1d |
| `rsi_reversion` | RSI反转 | walk_forward `rsi` | 1d |
| `turtle_donchian` | 海龟唐奇安通道 | `turtle_donchian` | 1d |
| `grid_classic` | 经典网格60日 | `grid_classic`（日线无状态版） | 1d |
| `multi_factor_lite` | 多因子轻量 | `multi_factor_top` 绝对阈值版 | 1d |
| `macd_5min` | MACD·5分钟K线 | `macd_5min` | 5m |
| `dual_ma_5min` | 双均线 5min (5/20 EMA) | `dual_ma_5min` | 5m |
| `dragon_picker` | 龙头首板战法(单票) | `dragon_picker`（日线近似；有分钟则用当日累计量） | 1d |
| `ml_prob` | ML概率因子 | `ml_prob`（精简特征+滚动 XGB/LGBM） | 1d |

### 分钟策略说明

- `macd_5min` / `dual_ma_5min` 元数据含 `bar_period=5m`；回测会加载分钟线并重采样为 5 分钟。
- 无分钟数据时回测会明确报错，不会用日线冒充 5m。

### ML 策略说明

- `ml_prob` 依赖回测注入的 `ctx["history"]`；类实例单例缓存滚动模型。
- 特征为 pandas/`desk_indicators` 轻量集，不强制整包 CASE+talib。

## YAML

`breakout.yaml` 仍可通过「同步策略」或 YAML 编辑器加载。
