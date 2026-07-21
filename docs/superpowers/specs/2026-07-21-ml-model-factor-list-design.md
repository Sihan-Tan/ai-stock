# 登记模型：删除与放入因子列表

**日期：** 2026-07-21  
**状态：** 已实现（未提交）  
**范围：** 模型训练页操作 + 因子图表目录/序列打分；不接回测/纸交易策略绑定。

## 目标

1. 已登记模型可删除（库记录 + 本地文件）。
2. 用户主动「放入因子列表」后，模型出现在因子图表左侧目录；勾选后对该股日线打分并画副图。
3. 可「移出因子列表」；删除已放入的模型时一并清理。

## 非目标

- 不把登记模型接到 `ml_prob` / 回测 / 纸交易参数。
- 不扩展训练特征集（金叉等）。
- 未放入的登记模型不出现在因子目录。

## 数据模型

在 `ml_models` 增加：

| 字段 | 类型 | 说明 |
|------|------|------|
| `as_factor` | bool / int，默认 false | 是否出现在因子目录 |

迁移：Alembic + SQLite 启动补列（与现有库演进方式一致）。

## API

| 方法 | 路径 | 行为 |
|------|------|------|
| `DELETE` | `/api/ml/models/{model_id}` | 删 DB 行；尽量删除 `path` 对应模型文件/目录；404 若不存在 |
| `POST` | `/api/ml/models/{model_id}/as-factor` | body `{ "as_factor": true \| false }`；更新标记；返回模型摘要 |
| `GET` | `/api/ml/models` | 现有列表；响应增加 `as_factor` |
| `GET` | `/api/factors` | 静态 TA 因子 + `as_factor=true` 的 ML 伪因子 |
| `GET` | `/api/factors/series` | `names` 可含 `ml:{model_id}`；其余行为不变 |

### ML 伪因子元数据约定

- `name`: `ml:{model_id}`（`model_id` 本身不含冒号）
- `label`: 如 `{model_id}（{engine}）`
- `category`: `ml`
- `plot`: `panel`
- `default_enabled`: `false`
- `enabled`: `true`
- `talib`: 空或占位（计算走 ML 分支，不走 TA-Lib）
- `outputs`: `["ml_score"]`
- `params`: 可含 `model_id` / `engine` 供前端展示

## 计算路径

`FactorService.compute_series` / `compute_series_from_df`：

1. 将 `names` 拆成 TA 名与 `ml:*` 名。
2. TA 部分沿用现有 `apply_factor_specs`。
3. 对每个 `ml:{model_id}`：
   - 查库确认存在且 `as_factor=true`（系列请求也可仅要求存在，但目录只展示已放入的；系列侧对未放入返回 400 更清晰）。
   - 用 `desk_strategy.ml_prob_engine.calc_features` + 模型登记的 `features_json`（缺省则用 `FEATURE_COLS`）构造特征矩阵。
   - `MlInferencer.score(model_id, X)` 得到分数序列。
   - 写入 `series[name].outputs.ml_score`（日期对齐日线；特征 NaN 行分数为 null）。
4. 预热：若 `names` 含 ML 项，warmup 至少覆盖特征所需（约 60 交易日量级，可复用/抬高现有日历预热下限）。

## 前端（因子页）

**模型训练 Tab — 已登记模型表：**

- 列增加：是否已放入、操作。
- 操作：「放入因子列表」/「移出因子列表」、「删除」（删除前简易确认）。
- 成功后刷新模型列表；若当前在图表 Tab，下次加载目录时可见变化（或放入后提示切换到图表）。

**图表 Tab：**

- 目录自然出现 `category=ml` 项（`FactorCatalog` 若按 category 分组则自动多一类）。
- 勾选 + 计算：沿用现有 `/api/factors/series`；副图渲染 `ml_score`（与其它 panel 一致）。

## 测试

- 删除：存在则消失；重复删 404。
- 放入/移出：`GET /api/factors` 含/不含 `ml:{id}`。
- 系列：对有日线标的请求 `ml:{id}` 返回非空 `ml_score` 点列（可用 fixture 小模型或 mock inferencer）。

## 风险与边界

- 打分依赖本地模型文件完整；文件缺失时 API 返回明确错误，避免静默随机分（现有 `MlInferencer` 回退随机分仅适合 demo——本功能路径应优先失败可见）。
- `model_id` 变更/覆盖训练时同 id upsert：`as_factor` 保留原值（除非产品另定重置）。
