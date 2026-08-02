# 因子中文三段式说明 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为全量 TA-Lib 注册因子、周期别名与价量伪因子提供三段式中文详述（含义/怎么用/注意点），列表短名与说明弹层分离，规则下拉不被长文污染。

**Architecture:** 保留 `TALIB_ZH_DESC` 作短 `label`；新建 `zh_guide.py` 的 `TALIB_ZH_GUIDE` + `zh_guide_for_talib()` 作 `description`。`registry._f` 拆分两者，周期别名追加「本条目默认周期」。前端解析 `【…】` 分节展示；`formatFactorOptionLabel` 只用 `label`。

**Tech Stack:** Python 3、pytest、React、Vitest、现有 `desk_factor` / Factors 页。

**Spec:** `docs/superpowers/specs/2026-08-02-factor-zh-guide-design.md`

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| Create: `packages/factor/desk_factor/zh_guide.py` | `_three` / `_cdl` 格式化；`TALIB_ZH_GUIDE` 全量；`zh_guide_for_talib` |
| Modify: `packages/factor/desk_factor/zh_desc.py` | 不改短名表；可选从 `zh_guide` 再导出（非必须） |
| Modify: `packages/factor/desk_factor/registry.py` | `_f`：`label`←短名，`description`←详述；别名附周期句 |
| Modify: `tests/test_factor_registry.py` | label/description 契约断言 |
| Create: `tests/test_zh_guide.py` | 覆盖率与格式断言 |
| Create: `apps/web/src/factors/parseFactorGuide.ts` | 解析三段标题 |
| Create: `apps/web/src/factors/parseFactorGuide.test.ts` | 解析单测 |
| Modify: `apps/web/src/pages/Factors.tsx` | `TaFactorExplainDialog` 分节渲染 |
| Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx` | `formatFactorOptionLabel` 仅用 label |
| Modify: `apps/web/src/pages/StrategyRuleBuilder.test.ts` | 同步期望 |
| Modify: `docs/superpowers/specs/2026-08-02-factor-zh-guide-design.md` | 状态改为已实现 |

---

### Task 1: 详述契约单测（先失败）

**Files:**
- Create: `tests/test_zh_guide.py`
- Modify: `tests/test_factor_registry.py`

- [ ] **Step 1: 写 `tests/test_zh_guide.py`**

```python
"""TALIB_ZH_GUIDE 覆盖率与三段式格式。"""

from __future__ import annotations

from desk_factor.zh_desc import TALIB_ZH_DESC
from desk_factor.zh_guide import TALIB_ZH_GUIDE, zh_guide_for_talib


def test_guide_covers_all_zh_desc_keys():
    missing = sorted(set(TALIB_ZH_DESC) - set(TALIB_ZH_GUIDE))
    assert missing == [], f"缺少详述: {missing}"


def test_guide_has_three_sections():
    for key, text in TALIB_ZH_GUIDE.items():
        assert "【含义】" in text, key
        assert "【怎么用】" in text, key
        assert "【注意点】" in text, key
        assert "【含义】" not in TALIB_ZH_DESC[key]


def test_zh_guide_fallback_unknown():
    # 未知键回退短名或原名，不得抛错
    out = zh_guide_for_talib("NOT_A_REAL_FACTOR_XYZ")
    assert isinstance(out, str) and out
```

- [ ] **Step 2: 更新 `tests/test_factor_registry.py` 中相关断言**

在 `test_registry_has_required_fields_and_plots` 内，把对 description 的短名断言改为同时校验 label / description：

```python
    assert "相对强弱" in by_name["RSI_14"]["label"]
    assert "【含义】" in by_name["RSI_14"]["description"]
    assert "【怎么用】" in by_name["RSI_14"]["description"]
    assert "【含义】" not in by_name["RSI_14"]["label"]
    assert "简单移动平均" in by_name["SMA_20"]["label"]
    assert "【含义】" in by_name["SMA_20"]["description"]
    assert "本条目默认周期" in by_name["SMA_20"]["description"]
    assert "本条目默认周期" in by_name["RSI_14"]["description"]
    assert "【含义】" in by_name["CLOSE"]["description"]
    assert "【含义】" in by_name["CDLDOJI"]["description"]
```

删除（或替换）旧的：

```python
    assert "相对强弱" in by_name["RSI_14"]["description"]
    assert "简单移动平均" in by_name["SMA_20"]["description"]
```

- [ ] **Step 3: 跑测确认失败**

Run:

```bash
pytest tests/test_zh_guide.py tests/test_factor_registry.py::test_registry_has_required_fields_and_plots -v
```

Expected: FAIL（`desk_factor.zh_guide` 不存在，或 description 尚无 `【含义】`）

- [ ] **Step 4: Commit**

```bash
git add tests/test_zh_guide.py tests/test_factor_registry.py
git commit -m "test: 因子三段式说明契约"
```

---

### Task 2: `zh_guide.py` 基础设施 + 非 CDL 全量文案

**Files:**
- Create: `packages/factor/desk_factor/zh_guide.py`

- [ ] **Step 1: 创建文件，先写格式化函数与查找函数**

```python
"""TA-Lib / 价量因子三段式中文详述（展示用）。"""

from __future__ import annotations

from desk_factor.zh_desc import zh_desc_for_talib


def _three(meaning: str, how: str, note: str) -> str:
    """
    组装三段式说明。

    @param meaning 含义
    @param how 怎么用
    @param note 注意点
    """
    return f"【含义】{meaning}\n【怎么用】{how}\n【注意点】{note}"


def _cdl(shape: str, bias: str, note: str | None = None) -> str:
    """
    K 线形态通用详述。

    @param shape 形态外观简述
    @param bias 多空倾向与用法
    @param note 额外注意；默认通用提示
    """
    return _three(
        f"K线形态识别：{shape}。命中时输出多为 ±100，未命中为 0。",
        f"{bias}；可与趋势方向、关键位或成交量确认合用。",
        note
        or "形态信号有滞后且易假突破，需结合周期与前后文，不宜单独作为交易依据。",
    )
```

- [ ] **Step 2: 写入非 CDL 的 `TALIB_ZH_GUIDE` 条目（102 个）**

在同一文件用 `_ROWS` 元组构建（key, meaning, how, note），再 `update` 进字典。下列为**完整**应写入内容（勿删减 key）：

```python
_ROWS: list[tuple[str, str, str, str]] = [
    # Cycle
    ("HT_DCPERIOD", "希尔伯特变换估计价格主导周期长度。", "周期拉长常对应趋势段，缩短对应震荡；可作自适应均线周期参考。", "对噪声敏感，短样本不稳定，宜作辅助而非硬阈值。"),
    ("HT_DCPHASE", "主导周期的相位角，描述周期内所处位置。", "相位变化可辅助判断周期拐点；常与正弦波指标同看。", "相位缠绕与跳变常见，需平滑或结合趋势过滤。"),
    ("HT_PHASOR", "希尔伯特相量：同相与正交分量。", "观察分量交叉/幅度变化，辅助识别周期转折。", "输出双序列，解读门槛较高，适合研究型用法。"),
    ("HT_SINE", "把主导周期映射为正弦/领先正弦。", "两线交叉常作周期拐点提示，震荡市更适用。", "趋势市交叉频繁失效，需 ADX 等趋势过滤。"),
    ("HT_TRENDMODE", "判别当前偏趋势模式还是周期模式。", "趋势模式偏均线/动量；周期模式偏振荡指标。", "为启发式分类，切换附近可能抖动。"),
    # Math operators
    ("ADD", "两序列逐点相加。", "合成价量或因子线性组合时使用。", "量纲需一致，避免无意义相加。"),
    ("DIV", "两序列逐点相除。", "做比率、标准化或相对强度。", "分母接近 0 会爆炸，需保护或过滤。"),
    ("MAX", "滚动窗口内最高值。", "阻力/通道上沿、突破参考。", "窗口过短噪声大，过长反应慢。"),
    ("MAXINDEX", "滚动窗口最高值出现的位置索引。", "分析高点是否递进或背离时使用。", "索引含义依赖实现基准，勿当价格用。"),
    ("MIN", "滚动窗口内最低值。", "支撑/通道下沿、跌破参考。", "同 MAX，注意窗口与滞后。"),
    ("MININDEX", "滚动窗口最低值位置索引。", "分析低点结构或背离。", "勿与价格序列直接比较。"),
    ("MINMAX", "同时给出窗口最低与最高。", "画通道或计算位置百分比。", "双输出，下游需按列名取用。"),
    ("MINMAXINDEX", "窗口最低/最高的位置索引。", "结构高低点定位。", "双输出索引，注意对齐。"),
    ("MULT", "两序列逐点相乘。", "加权、交互项或缩放。", "量纲放大要警惕。"),
    ("SUB", "两序列逐点相减。", "价差、因子差、偏离。", "确保对齐与同频。"),
    ("SUM", "滚动窗口求和。", "累计量、能量近似。", "未归一时不同标的不可比。"),
    # Math transform
    ("ACOS", "反余弦变换。", "极少直接交易；多用于研究变换。", "输入需在定义域内。"),
    ("ASIN", "反正弦变换。", "研究用非线性映射。", "定义域限制，实盘少用。"),
    ("ATAN", "反正切变换。", "可缓和极端值。", "改变量纲，策略阈值需重标定。"),
    ("CEIL", "向上取整。", "离散化或网格化。", "损失精度，不适合精细阈值。"),
    ("COS", "余弦变换。", "周期特征构造。", "对价格直接套用意义有限。"),
    ("COSH", "双曲余弦。", "研究用。", "增长快，注意数值稳定。"),
    ("EXP", "自然指数。", "还原对数价或放大差异。", "易溢出，需裁剪。"),
    ("FLOOR", "向下取整。", "离散化。", "同 CEIL。"),
    ("LN", "自然对数。", "收益近似、压缩量纲。", "非正数无法取对数。"),
    ("LOG10", "常用对数。", "跨量级比较。", "同 LN 的定义域问题。"),
    ("SIN", "正弦变换。", "周期特征。", "直接用于价格意义有限。"),
    ("SINH", "双曲正弦。", "研究用。", "极端值放大明显。"),
    ("SQRT", "平方根。", "波动或成交量压缩。", "负数无效。"),
    ("TAN", "正切变换。", "研究用。", "近奇点爆炸。"),
    ("TANH", "双曲正切，把值压到 (-1,1)。", "特征缩放、抑制离群。", "饱和后区分度下降。"),
    # Momentum
    ("ADX", "平均趋向指数，衡量趋势强度（不辨方向）。", "ADX 上行且较高时可信任突破/均线；低位偏震荡策略。", "高位只说明趋势强，不指示多空；不同标的阈值宜相对看。"),
    ("ADXR", "ADX 的平滑评级，趋势强度更稳。", "用法近 ADX，适合过滤抖动。", "更滞后，拐点反应更慢。"),
    ("APO", "绝对价格振荡器，快慢均线差值。", "上穿/下穿零轴看动量切换；可与价格背离同看。", "绝对价差跨股不可比，股票间慎直接套阈值。"),
    ("AROON", "阿隆：距最近高/低点的时间占比。", "Aroon Up 高、Down 低偏多头趋势；交叉可作转换提示。", "横盘时两线纠结，宜配合波动过滤。"),
    ("AROONOSC", "阿隆振荡器 = Up − Down。", "正值偏多、负值偏空；极值关注动能衰竭。", "震荡市信号频繁，需趋势或幅度过滤。"),
    ("BOP", "均势指标，用开高低收刻画多空力量。", "持续为正偏多，为负偏空；可看零轴穿越。", "单日噪声大，宜均线平滑后再用。"),
    ("CCI", "商品通道指数，价相对统计中枢的偏离。", "常用 ±100/±200 看超买超卖或突破启动。", "强趋势中可长期钝在极值，勿逆势盲反。"),
    ("CMO", "钱德动量，上涨日与下跌日动量对比。", "用法类似 RSI，看极值与回归。", "参数敏感，需与品种波动匹配。"),
    ("DX", "动向指数，ADX 的未平滑前身。", "观察趋势强度变化，常与 +DI/−DI 同看。", "比 ADX 更抖，实盘多用 ADX。"),
    ("MACD", "快慢 EMA 差（DIF）、信号线与柱。", "金叉/死叉、零轴上下、柱缩短看动能；可与背离合用。", "滞后指标；震荡市交叉多，宜加趋势或幅度过滤。"),
    ("MACDEXT", "可配置均线类型的 MACD。", "按品种选择 EMA/SMA 等，规则同 MACD。", "参数自由度高，回测易过拟合。"),
    ("MACDFIX", "固定 12/26 结构的 MACD 变体。", "用法同经典 MACD，便于统一参数。", "固定周期不适配所有品种与级别。"),
    ("MFI", "资金流量指标，带量的 RSI 思路。", "80/20 一带看热度；价量背离作警戒。", "依赖成交量质量，冷门股噪声大。"),
    ("MINUS_DI", "负向动向 −DI。", "−DI 上穿 +DI 偏空；与 ADX 确认趋势是否可信。", "单看 DI 交叉易假信号。"),
    ("MINUS_DM", "负向动向值 −DM（原始动量）。", "多作中间量或研究拆解。", "通常不如 DI/ADX 直观。"),
    ("MOM", "动量：现价相对 N 日前的差值。", "动量由负转正偏多；也可做排名选股。", "未标准化，跨股比较宜用收益率或排名。"),
    ("PLUS_DI", "正向动向 +DI。", "+DI 高于 −DI 且 ADX 上升偏多头趋势。", "交叉需强度确认。"),
    ("PLUS_DM", "正向动向值 +DM。", "研究或自定义 DI 时使用。", "实盘展示较少。"),
    ("PPO", "百分比价格振荡器，MACD 的百分比版。", "跨股可比性优于 APO；用法似 MACD。", "仍滞后，震荡市交叉多。"),
    ("ROC", "变动率百分比。", "动量强弱、截面排序；过零看方向切换。", "高波动品种阈值需放宽。"),
    ("ROCP", "变动率（小数）。", "同 ROC，量纲为比例。", "与 ROC 勿混用阈值。"),
    ("ROCR", "现价 / N 日前价。", "大于 1 偏上涨动量。", "注意除零与停牌缺口。"),
    ("ROCR100", "ROCR×100。", "以 100 为中轴观察。", "同 ROCR。"),
    ("RSI", "相对强弱指数，涨跌幅度相对强弱。", "经典 30/70 超卖超买；也可看中轴 50 与背离。", "单边趋势会长期钝化，反弹/回落信号需趋势过滤。"),
    ("STOCH", "慢速随机指标 KD。", "低位金叉偏多、高位死叉偏空；也可看超买超卖区。", "强趋势中 K/D 可顶背死叉失效。"),
    ("STOCHF", "快速随机指标，更灵敏。", "短线拐点提示；常再平滑成慢速 KD。", "假信号更多。"),
    ("STOCHRSI", "对 RSI 再做随机指标。", "放大 RSI 的超买超卖节奏。", "极度敏感，宜严格过滤。"),
    ("TRIX", "三重指数平滑后的变动率。", "零轴穿越看方向；滤噪后的动量。", "滞后明显，不适合极短线。"),
    ("ULTOSC", "多周期加权的终极振荡器。", "综合短中长压力，极值回归或突破用法。", "参数复杂，需样本外验证。"),
    ("WILLR", "威廉 %R，衡量收盘在高低区间位置。", "类似随机指标，−20/−80 看热度。", "趋势市钝化，忌机械逆势。"),
    # Overlap
    ("BBANDS", "布林带：中轨均线 ± 标准差轨。", "跌破下轨回抽或上轨压力；带宽扩大看波动升温。", "强趋势可沿轨行走，不要一碰轨就反手。"),
    ("DEMA", "双指数移动平均，滞后小于 EMA。", "作趋势线或金叉死叉；反应快于 SMA/EMA。", "更跟噪声，需配合波动过滤。"),
    ("EMA", "指数移动平均，近端权重大。", "多空分界、回踩支撑；多周期排列看趋势。", "震荡市来回打脸，宜加过滤。"),
    ("HT_TRENDLINE", "希尔伯特瞬时趋势线。", "作自适应均线支撑阻力。", "计算重、边界效应强。"),
    ("KAMA", "考夫曼自适应均线，趋势时跟、震荡时钝。", "价格相对 KAMA 位置与拐点作趋势跟随。", "效率比参数需适配品种。"),
    ("MA", "通用移动平均（类型可配）。", "同均线用法：方向、多空、交叉。", "类型与周期决定性格，勿混用。"),
    ("MAMA", "MESA 自适应均线及 FAMA。", "MAMA/FAMA 交叉作趋势切换提示。", "参数敏感，宜充分回测。"),
    ("MAVP", "周期可变的移动平均。", "用另一序列驱动周期，做自适应平滑。", "周期序列质量决定效果。"),
    ("MIDPOINT", "窗口最高最低的中点（基于价格序列）。", "作中轴或回归目标。", "不是成交量加权中心。"),
    ("MIDPRICE", "窗口最高价与最低价中点。", "通道中轴参考。", "忽略收盘分布。"),
    ("SAR", "抛物线转向，跟踪止损点。", "点位在价下偏多、价上偏空；翻转作转向提示。", "震荡市频繁翻转，交易成本高。"),
    ("SAREXT", "可扩展参数的抛物线转向。", "用法同 SAR，细调加速因子。", "过拟合风险更高。"),
    ("SMA", "简单移动平均，窗口均等权重。", "趋势方向与支撑阻力；多周期组合。", "滞后大于 EMA，突破确认更慢也更稳。"),
    ("T3", "T3 三重指数平滑均线。", "更平滑的趋势线，适合中线跟随。", "拐点更滞后。"),
    ("TEMA", "三重指数移动平均。", "低滞后趋势跟踪。", "更易被噪声带动。"),
    ("TRIMA", "三角移动平均，中部权重大。", "平滑趋势，过滤毛刺。", "端点反应慢。"),
    ("WMA", "加权移动平均，近端权重高。", "介于 SMA 与 EMA 之间的趋势线。", "权重固定，极端行情仍滞后。"),
    # Price transform
    ("AVGPRICE", "开高低收四价平均。", "作更稳的价格输入替代收盘。", "仍含开盘跳空影响。"),
    ("MEDPRICE", "最高最低中值。", "通道中轴或波动研究。", "不含收盘信息。"),
    ("TYPPRICE", "典型价格 (H+L+C)/3。", "常作 CCI 等输入。", "与收盘策略混用时注意一致性。"),
    ("WCLPRICE", "加权收盘 (H+L+2C)/4。", "更贴近收盘的典型价。", "定义需与公式库一致。"),
    ("CLOSE", "日/周期收盘价。", "规则比较、近端涨跌、作为其他因子输入。", "含停牌/复权差异，策略需统一复权口径。"),
    ("OPEN", "开盘价。", "缺口、集合竞价相关规则。", "盘中未定时仅对历史 bar 有意义。"),
    ("HIGH", "最高价。", "突破、压力、振幅。", "极值易被插针扭曲。"),
    ("LOW", "最低价。", "跌破、支撑、振幅。", "同 HIGH，注意影线噪音。"),
    ("VOLUME", "成交量。", "放量确认、量价背离、能量类因子输入。", "未流通盘标准化时跨股难比。"),
    # Statistic
    ("BETA", "相对另一序列的贝塔。", "衡量联动/弹性；配对或风险暴露。", "窗口与基准选择强烈影响结果。"),
    ("CORREL", "滚动皮尔逊相关。", "联动强弱、配对交易过滤。", "相关≠因果；结构突变后失效。"),
    ("LINEARREG", "窗口线性回归终点值。", "作平滑价或回归通道。", "窗口末端拟合，未来信息不可用于当根 bar 偷看。"),
    ("LINEARREG_ANGLE", "回归线角度。", "斜率转角度，看趋势陡峭度。", "角度量纲受价格尺度影响。"),
    ("LINEARREG_INTERCEPT", "回归截距。", "通道或残差分析组件。", "单独交易意义有限。"),
    ("LINEARREG_SLOPE", "回归斜率。", "动量/趋势强度代理。", "需标准化才能跨股比。"),
    ("STDDEV", "滚动标准差。", "波动估计、布林带宽组件。", "方差非常态时低估尾部风险。"),
    ("TSF", "时间序列预测（回归外推一点）。", "短期趋势外推参考。", "不是可靠预测，勿当未来价。"),
    ("VAR", "滚动方差。", "波动建模。", "同 STDDEV。"),
    # Volatility
    ("ATR", "平均真实波幅，含跳空的波动度量。", "仓位/止损距离、突破过滤（如 1×ATR）。", "波动抬升不等于方向；暴涨暴跌后 ATR 钝高。"),
    ("NATR", "ATR 相对价格的归一化。", "跨股波动比较、自适应阈值。", "极端低价股比例意义需谨慎。"),
    ("TRANGE", "真实波幅（单 bar，含跳空）。", "ATR 的原料；看单日波动冲击。", "未平滑，噪声大。"),
    # Volume
    ("AD", "累积/派发线，价位加权的量能累积。", "A/D 与价格背离作派发/吸筹警戒。", "需可靠成交量；板块联动时个体信号变弱。"),
    ("ADOSC", "A/D 的快慢线振荡器。", "零轴穿越看量能动量变化。", "参数敏感，宜配合趋势。"),
    ("OBV", "能量潮：涨日加量、跌日减量的累积线。", "OBV 创新高而价未确认可能蕴蓄突破；背离作警示。", "长期累积尺度大，宜看形态而非绝对水平。"),
]

TALIB_ZH_GUIDE: dict[str, str] = {k: _three(a, b, c) for k, a, b, c in _ROWS}
```

- [ ] **Step 3: 实现 `zh_guide_for_talib`**

```python
def zh_guide_for_talib(talib_name: str) -> str:
    """
    返回三段式详述；缺失时回退短中文名。

    @param talib_name: TA-Lib 函数名或 CLOSE 等伪因子名
    """
    key = (talib_name or "").strip()
    if not key:
        return ""
    if key in TALIB_ZH_GUIDE:
        return TALIB_ZH_GUIDE[key]
    return zh_desc_for_talib(key)
```

此时 CDL 尚未写入，`test_guide_covers_all_zh_desc_keys` 仍应失败（缺 CDL）。先不提交完整通过，继续 Task 3；或本 Task 只提交非 CDL 骨架并接受覆盖率失败——**推荐直接进入 Task 3 一并写完再跑绿。**

---

### Task 3: CDL 形态全量详述

**Files:**
- Modify: `packages/factor/desk_factor/zh_guide.py`

- [ ] **Step 1: 用 `_cdl` 写入全部 61 个 CDL\*（完整列表）**

在 `TALIB_ZH_GUIDE` 构建后执行：

```python
_CDL: list[tuple[str, str, str]] = [
    ("CDL2CROWS", "两只乌鸦：高位两根阴线压制。", "偏空反转提示，宜出现在上升后。"),
    ("CDL3BLACKCROWS", "三只乌鸦：连续三根弱势阴线。", "强空头延续/反转信号。"),
    ("CDL3INSIDE", "三内部上涨/下跌：孕线后确认方向。", "第三根确认突破孕线方向。"),
    ("CDL3LINESTRIKE", "三线打击：三连阳/阴后大反向烛。", "反转意味强，需看突破是否站稳。"),
    ("CDL3OUTSIDE", "三外部：外包线后确认。", "方向随第三根确认。"),
    ("CDL3STARSINSOUTH", "南方三星：下跌末复杂止跌形态。", "偏多反转，较罕见。"),
    ("CDL3WHITESOLDIERS", "三白兵：连续三根上升阳线。", "偏多延续/反转，宜量能配合。"),
    ("CDLABANDONEDBABY", "弃婴：跳空十字星后反向跳空。", "较强反转，多空由方向决定。"),
    ("CDLADVANCEBLOCK", "大敌当前：上涨三连阳但实体缩短。", "升势减弱警戒，偏空警戒。"),
    ("CDLBELTHOLD", "捉腰带线：开盘极端后单方向实体。", "看多/看空吞没式力度。"),
    ("CDLBREAKAWAY", "脱离：加速后的反转组合。", "趋势末端反转提示。"),
    ("CDLCLOSINGMARUBOZU", "收盘光头光脚：收盘锁在高低极值。", "方向强势，延续概率偏高。"),
    ("CDLCONCEALBABYSWALL", "藏婴吞没：下跌中特殊吞没变体。", "偏多反转，样本少。"),
    ("CDLCOUNTERATTACK", "反击线：同收盘价的反向实体。", "反转提示，需次日确认。"),
    ("CDLDARKCLOUDCOVER", "乌云盖顶：高开阴线深入前阳。", "偏空反转，深入越多越强。"),
    ("CDLDOJI", "十字星：开收接近，多空平衡。", "拐点警戒，需前后趋势与次日确认。"),
    ("CDLDOJISTAR", "十字星形态（带缺口语境）。", "反转星线，方向看前后。"),
    ("CDLDRAGONFLYDOJI", "蜻蜓十字：长下影、开收在高位。", "下跌后偏多；上涨后需谨慎。"),
    ("CDLENGULFING", "吞没：后烛实体吞没前烛。", "阳吞没偏多、阴吞没偏空。"),
    ("CDLEVENINGDOJISTAR", "黄昏十字星。", "顶部反转偏空。"),
    ("CDLEVENINGSTAR", "黄昏之星。", "顶部反转偏空。"),
    ("CDLGAPSIDESIDEWHITE", "跳空并列阳线。", "延续或整理，需看缺口方向。"),
    ("CDLGRAVESTONEDOJI", "墓碑十字：长上影。", "上涨后偏空警戒。"),
    ("CDLHAMMER", "锤头：长下影小实体。", "下跌后偏多反转。"),
    ("CDLHANGINGMAN", "上吊线：形状似锤头但在上涨后。", "顶部警戒偏空。"),
    ("CDLHARAMI", "母子线：前大后小孕线。", "反转酝酿，等待确认。"),
    ("CDLHARAMICROSS", "十字母子。", "比普通孕线更强的转机提示。"),
    ("CDLHIGHWAVE", "风高浪大：长上下影。", "犹豫/波动加大，方向待定。"),
    ("CDLHIKKAKE", "陷阱形态。", "假突破后反向，短线交易者关注。"),
    ("CDLHIKKAKEMOD", "修正陷阱。", "用法同陷阱，条件更严。"),
    ("CDLHOMINGPIGEON", "家鸽：下跌中的弱孕线。", "偏多反转酝酿。"),
    ("CDLIDENTICAL3CROWS", "三胞胎乌鸦。", "强空信号。"),
    ("CDLINNECK", "颈内线。", "下跌延续偏空。"),
    ("CDLINVERTEDHAMMER", "倒锤头。", "下跌后偏多警戒，需确认。"),
    ("CDLKICKING", "反冲：反向光头跳空。", "强反转信号。"),
    ("CDLKICKINGBYLENGTH", "由更长实体决定的反冲。", "同反冲，强调实体长度。"),
    ("CDLLADDERBOTTOM", "梯底。", "下跌末偏多反转。"),
    ("CDLLONGLEGGEDDOJI", "长脚十字。", "平衡且波动大，转机警戒。"),
    ("CDLLONGLINE", "长实体蜡烛。", "方向强，作动量确认。"),
    ("CDLMARUBOZU", "光头光脚大实体。", "极端强势方向烛。"),
    ("CDLMATCHINGLOW", "相同低价。", "下跌中偏多支撑提示。"),
    ("CDLMATHOLD", "铺垫。", "上升中继偏多。"),
    ("CDLMORNINGDOJISTAR", "早晨十字星。", "底部反转偏多。"),
    ("CDLMORNINGSTAR", "早晨之星。", "底部反转偏多。"),
    ("CDLONNECK", "颈上线。", "下跌延续偏空。"),
    ("CDLPIERCING", "刺透：低开阳线深入前阴。", "偏多反转。"),
    ("CDLRICKSHAWMAN", "黄包车夫（长脚十字变体）。", "平衡犹豫，待确认。"),
    ("CDLRISEFALL3METHODS", "上升/下降三法。", "中继形态，顺原趋势。"),
    ("CDLSEPARATINGLINES", "分离线。", "趋势延续提示。"),
    ("CDLSHOOTINGSTAR", "射击之星：长上影。", "上涨后偏空。"),
    ("CDLSHORTLINE", "短实体蜡烛。", "整理/犹豫，方向弱。"),
    ("CDLSPINNINGTOP", "纺锤：小实体长影线。", "犹豫，常出现在转折附近。"),
    ("CDLSTALLEDPATTERN", "停顿形态。", "升势减速警戒。"),
    ("CDLSTICKSANDWICH", "条形三明治。", "偏多反转变体。"),
    ("CDLTAKURI", "探水竿（长下影蜻蜓）。", "下跌后偏多。"),
    ("CDLTASUKIGAP", "跳空并列阴阳线。", "缺口中继，顺势。"),
    ("CDLTHRUSTING", "插入线。", "下跌中继偏空（弱于刺透）。"),
    ("CDLTRISTAR", "三星：三个十字。", "反转提示，较罕见。"),
    ("CDLUNIQUE3RIVER", "奇特三河床。", "偏多反转。"),
    ("CDLUPSIDEGAP2CROWS", "向上跳空两只乌鸦。", "顶部偏空。"),
    ("CDLXSIDEGAP3METHODS", "上升/下降跳空三法。", "跳空中继，顺势。"),
]

for name, shape, bias in _CDL:
    TALIB_ZH_GUIDE[name] = _cdl(shape, bias)
```

- [ ] **Step 2: 断言 key 集合一致（本地快速检查）**

Run:

```bash
python -c "from desk_factor.zh_desc import TALIB_ZH_DESC; from desk_factor.zh_guide import TALIB_ZH_GUIDE; print(sorted(set(TALIB_ZH_DESC)-set(TALIB_ZH_GUIDE))); print(len(TALIB_ZH_GUIDE))"
```

Expected: 空列表缺失；长度为 163。

- [ ] **Step 3: Commit**

```bash
git add packages/factor/desk_factor/zh_guide.py
git commit -m "feat(factor): 全量 TA-Lib 三段式中文详述"
```

---

### Task 4: registry 接线 label / description

**Files:**
- Modify: `packages/factor/desk_factor/registry.py`（`_f` 函数，约 122–148 行）

- [ ] **Step 1: 改写 `_f`**

```python
def _f(
    name: str,
    *,
    talib: str,
    label: str | None = None,
    category: str,
    params: dict[str, Any] | None = None,
    outputs: list[str] | None = None,
    plot: PlotKind,
    default_enabled: bool = False,
    description: str | None = None,
) -> FactorMeta:
    from desk_factor.zh_desc import zh_desc_for_talib
    from desk_factor.zh_guide import zh_guide_for_talib

    params = params or {}
    lookup = (talib or name).strip()
    short = zh_desc_for_talib(lookup)
    guide = (description or "").strip() or zh_guide_for_talib(lookup)
    tp = params.get("timeperiod")
    if (
        tp is not None
        and name.strip().upper() != lookup.upper()
        and "【含义】" in guide
        and "本条目默认周期" not in guide
    ):
        guide = f"{guide}\n（本条目默认周期 {int(tp)}）"
    return {
        "name": name,
        "label": (label or short or name),
        "category": category,
        "params": params,
        "outputs": outputs or [name.lower()],
        "plot": plot,
        "default_enabled": default_enabled,
        "enabled": True,
        "talib": talib,
        "description": guide,
    }
```

- [ ] **Step 2: 跑测**

Run:

```bash
pytest tests/test_zh_guide.py tests/test_factor_registry.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add packages/factor/desk_factor/registry.py
git commit -m "feat(factor): registry 拆分短名 label 与详述 description"
```

---

### Task 5: 前端解析与说明弹层分节

**Files:**
- Create: `apps/web/src/factors/parseFactorGuide.ts`
- Create: `apps/web/src/factors/parseFactorGuide.test.ts`
- Modify: `apps/web/src/pages/Factors.tsx`（`TaFactorExplainDialog`）

- [ ] **Step 1: 写失败单测**

```typescript
/** parseFactorGuide：三段式标题拆分。 */
import { describe, expect, it } from "vitest";
import { parseFactorGuide } from "./parseFactorGuide";

describe("parseFactorGuide", () => {
  it("splits three titled sections", () => {
    const text = "【含义】甲\n【怎么用】乙\n【注意点】丙";
    expect(parseFactorGuide(text)).toEqual([
      { title: "含义", body: "甲" },
      { title: "怎么用", body: "乙" },
      { title: "注意点", body: "丙" },
    ]);
  });

  it("returns single untitled block when no markers", () => {
    expect(parseFactorGuide("普通说明")).toEqual([{ title: "", body: "普通说明" }]);
  });

  it("keeps trailing period note as part of last or extra paragraph", () => {
    const text = "【含义】甲\n【怎么用】乙\n【注意点】丙\n（本条目默认周期 14）";
    const parts = parseFactorGuide(text);
    expect(parts.some((p) => p.body.includes("本条目默认周期") || p.title === "")).toBe(true);
  });
});
```

- [ ] **Step 2: 实现 `parseFactorGuide.ts`**

```typescript
/** 因子详述分节。 */
export type FactorGuideSection = {
  title: string;
  body: string;
};

/**
 * 将【标题】正文拆成章节；无标记时整段作为无标题正文。
 * @param text API description
 */
export function parseFactorGuide(text: string): FactorGuideSection[] {
  const raw = (text || "").trim();
  if (!raw) return [{ title: "", body: "暂无说明" }];
  const re = /【([^】]+)】/g;
  const indices: { title: string; start: number; bodyStart: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    indices.push({ title: m[1], start: m.index, bodyStart: m.index + m[0].length });
  }
  if (indices.length === 0) return [{ title: "", body: raw }];

  const sections: FactorGuideSection[] = [];
  if (indices[0].start > 0) {
    const head = raw.slice(0, indices[0].start).trim();
    if (head) sections.push({ title: "", body: head });
  }
  for (let i = 0; i < indices.length; i++) {
    const end = i + 1 < indices.length ? indices[i + 1].start : raw.length;
    const body = raw.slice(indices[i].bodyStart, end).trim();
    sections.push({ title: indices[i].title, body });
  }
  return sections;
}
```

说明：周期附注若写在最后且无新 `【】`，会落在「注意点」的 `body` 内——可接受。若附注单独成行且希望独立展示，`body` 含该行即可，测试第三例通过。

- [ ] **Step 3: 改 `TaFactorExplainDialog` 正文区**

将：

```tsx
<p className="leading-relaxed">{desc}</p>
```

替换为：

```tsx
{parseFactorGuide(desc).map((section, idx) => (
  <div key={`${section.title}-${idx}`} className="space-y-1">
    {section.title ? (
      <h3 className="text-xs font-medium text-[var(--desk-mist)]">{section.title}</h3>
    ) : null}
    <p className="leading-relaxed whitespace-pre-wrap">{section.body}</p>
  </div>
))}
```

并在文件顶部增加：

```typescript
import { parseFactorGuide } from "../factors/parseFactorGuide";
```

- [ ] **Step 4: 跑测**

Run:

```bash
cd apps/web
pnpm exec vitest run src/factors/parseFactorGuide.test.ts --environment node
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/factors/parseFactorGuide.ts apps/web/src/factors/parseFactorGuide.test.ts apps/web/src/pages/Factors.tsx
git commit -m "feat(web): 因子说明弹层分节展示"
```

---

### Task 6: 规则构建器下拉只用短 label

**Files:**
- Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx`（`formatFactorOptionLabel`）
- Modify: `apps/web/src/pages/StrategyRuleBuilder.test.ts`

- [ ] **Step 1: 改测试期望**

```typescript
  it("uses label only and ignores long description", () => {
    expect(
      formatFactorOptionLabel(
        "RSI_14",
        "相对强弱指数 RSI",
        "【含义】很长\n【怎么用】x\n【注意点】y"
      )
    ).toBe("RSI_14（相对强弱指数 RSI）");
  });
```

删除或改写原「prefers description over label」用例为上面这一条。

- [ ] **Step 2: 改实现**

```typescript
/**
 * 规则构建器因子下拉文案：因子名（短中文 label）。
 * @param name 因子名
 * @param label 短标签
 * @param _description 详述（仅供调用方兼容；不用于选项主文案）
 */
export function formatFactorOptionLabel(
  name: string,
  label: string,
  _description?: string
): string {
  const tip = (label || "").trim();
  if (!tip || tip === name) return name;
  return `${name}（${tip}）`;
}
```

保留构建 `searchText` 时拼接 `description`，以便搜索仍能命中详述关键词（现有 `buildFactorOptions` 逻辑不变）。

- [ ] **Step 3: 跑测**

Run:

```bash
cd apps/web
pnpm exec vitest run src/pages/StrategyRuleBuilder.test.ts --environment node
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/StrategyRuleBuilder.tsx apps/web/src/pages/StrategyRuleBuilder.test.ts
git commit -m "fix(web): 规则因子下拉仅展示短 label"
```

---

### Task 7: 规格状态与总验证

**Files:**
- Modify: `docs/superpowers/specs/2026-08-02-factor-zh-guide-design.md`

- [ ] **Step 1: 规格头改为已实现**

```markdown
> 状态：已实现
> 日期：2026-08-02
```

- [ ] **Step 2: 总验证**

```bash
pytest tests/test_zh_guide.py tests/test_factor_registry.py -v
cd apps/web
pnpm exec vitest run src/factors/parseFactorGuide.test.ts src/pages/StrategyRuleBuilder.test.ts --environment node
```

Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-02-factor-zh-guide-design.md
git commit -m "docs: 因子三段式说明规格标为已实现"
```

---

## Self-Review

1. **Spec coverage:** 全量详述（Task 2–3）、label/description 拆分（Task 4）、弹层分节（Task 5）、下拉短文案（Task 6）、测试契约（Task 1/7）均已覆盖；ML/迅投明确不改。
2. **Placeholder scan:** 文案以完整 `_ROWS` / `_CDL` 给出；无 TBD。
3. **Type consistency:** `FactorGuideSection`、`zh_guide_for_talib`、`_three`/`_cdl` 命名前后一致；registry 仍输出 `label`/`description` 字符串字段。
