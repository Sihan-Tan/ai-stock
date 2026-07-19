/**
 * 策略说明：适用场景 / 规则 / 示例摘要（供监控页弹框展示）。
 */

export type StrategyProfile = {
  /** 策略 ID */
  id: string;
  /** 展示名 */
  name: string;
  /** 一句话简介 */
  summary: string;
  /** 适用场景 */
  scenario: string;
  /** 规则说明 */
  rules: string;
  /** 无源码时的示例文案 */
  exampleHint: string;
};

const MANUAL: StrategyProfile = {
  id: "manual",
  name: "手动建仓",
  summary: "不由策略自动开平仓，仅作持仓标签与人工管理。",
  scenario: "试错建仓、对照观察、或暂时不想绑定自动策略时使用。",
  rules: "Runner / 定时扫描不会按本标签自动下单；需手动换绑策略后才会参与策略信号。",
  exampleHint: "添加股票时选择「手动建仓」，或在此弹框切换为其他策略。",
};

const PROFILES: Record<string, StrategyProfile> = {
  manual: MANUAL,
  ma_cross: {
    id: "ma_cross",
    name: "双均线-日线(5/20)",
    summary: "日线双均线趋势跟踪：金叉买、死叉卖。",
    scenario: "趋势行情、波动适中的主板/大盘股；不适合剧烈震荡或主题脉冲。",
    rules: "sma5 上穿 sma20 → 买；sma5 下穿 sma20 → 卖。需有前日与当日均线数据。",
    exampleHint: "关注 5/20 日均线交叉；典型日线趋势跟随。",
  },
  dual_ma_5min: {
    id: "dual_ma_5min",
    name: "双均线-5分钟",
    summary: "5 分钟级别双均线交叉。",
    scenario: "日内波段、需要更高频信号时；对滑点与手续费更敏感。",
    rules: "短均线上穿长均线买、下穿卖（5 分钟 K）。",
    exampleHint: "适合盘中 Runner；信号频率高于日线版。",
  },
  ma20_hold: {
    id: "ma20_hold",
    name: "MA20持股法",
    summary: "收盘价相对 MA20 的突破持股。",
    scenario: "中期趋势持股；希望减少交易次数时。",
    rules: "收盘上穿 MA20 买，下穿卖。",
    exampleHint: "站上 MA20 持有，跌破离场。",
  },
  rsi_reversion: {
    id: "rsi_reversion",
    name: "RSI反转",
    summary: "RSI14 超卖/超买均值回归。",
    scenario: "震荡市、有明确超买超卖边界的标的；趋势单边时易反复止损。",
    rules: "RSI14 < 30 买；> 70 卖。",
    exampleHint: "超卖抄底、超买卖出的经典反转规则。",
  },
  boll_revert: {
    id: "boll_revert",
    name: "布林带均值回归",
    summary: "价格触及布林带上下轨的回归交易。",
    scenario: "箱体震荡；强趋势突破后需谨慎。",
    rules: "接近/跌破下轨偏多，接近/突破上轨偏空（见策略实现细节）。",
    exampleHint: "围绕中轨与上下轨做回归。",
  },
  bias_revert: {
    id: "bias_revert",
    name: "乖离率均值回归",
    summary: "价格相对均线偏离过大时回归。",
    scenario: "短期情绪过热/过冷后的修复行情。",
    rules: "乖离过大偏卖、过小偏买（见具体阈值）。",
    exampleHint: "用乖离率刻画「涨太狠 / 跌太狠」。",
  },
  macd_1d: {
    id: "macd_1d",
    name: "MACD·日K线",
    summary: "日线 MACD 金叉/死叉。",
    scenario: "中短线趋势确认；滞后于价格，适合过滤噪音。",
    rules: "MACD 金叉买、死叉卖（日线）。",
    exampleHint: "DIF/DEA 交叉驱动信号。",
  },
  macd_5min: {
    id: "macd_5min",
    name: "MACD·5分钟",
    summary: "5 分钟 MACD 交叉。",
    scenario: "日内交易；信号更密，需控制频率与成本。",
    rules: "5 分钟 MACD 金叉买、死叉卖。",
    exampleHint: "更高频的 MACD 跟随。",
  },
  turtle_donchian: {
    id: "turtle_donchian",
    name: "海龟唐奇安通道",
    summary: "突破 20 日高买、跌破 10 日低卖。",
    scenario: "趋势突破行情；震荡市假突破较多。",
    rules: "收盘 > 20 日唐奇安上轨买；收盘 < 10 日下轨卖。",
    exampleHint: "经典海龟通道突破。",
  },
  grid_classic: {
    id: "grid_classic",
    name: "经典网格60日",
    summary: "60 日高低切 8 格：底部买、顶部卖。",
    scenario: "宽幅震荡、区间明确；单边趋势易踏空或触发止损格。",
    rules: "底部 2 格买，顶部 2 格卖；越界止盈/止损格卖出。",
    exampleHint: "按 60 日区间划网格分层买卖。",
  },
  multi_factor_lite: {
    id: "multi_factor_lite",
    name: "多因子轻量",
    summary: "轻量多因子打分选时。",
    scenario: "需要综合动量/价值等信号时；依赖因子字段完整性。",
    rules: "多因子加权打分超过阈值开仓，低于阈值减仓（见实现）。",
    exampleHint: "组合若干价量/技术因子。",
  },
  ml_prob: {
    id: "ml_prob",
    name: "ML概率因子",
    summary: "滚动训练分类器，按上涨概率交易。",
    scenario: "有足够历史特征与算力；样本外需单独验证。",
    rules: "预测概率 > 0.60 买、< 0.40 卖（默认阈值，依赖 history）。",
    exampleHint: "特征 + 滚动重训 → 概率信号。",
  },
  dragon_picker: {
    id: "dragon_picker",
    name: "龙头首板战法(单票)",
    summary: "涨幅、量比、价位打分的短线强度策略。",
    scenario: "情绪高潮、题材龙头试错；非情绪市慎用。",
    rules: "按当日涨幅、量比、高点等打分，达阈值给多头信号（日线近似）。",
    exampleHint: "偏短线强度/首板逻辑的单票适配版。",
  },
};

/**
 * 取策略说明；未知 ID 时用通用模板。
 * @param id 策略 ID
 * @param fallbackName 列表里的名称
 */
export function getStrategyProfile(id: string, fallbackName?: string): StrategyProfile {
  const key = (id || "manual").trim() || "manual";
  const known = PROFILES[key];
  if (known) return known;
  const name = fallbackName || key;
  return {
    id: key,
    name,
    summary: `${name}（自定义/YAML 或未收录说明）。`,
    scenario: "以策略编辑页正文与回测表现为准；上模拟前请确认生命周期阶段允许开仓。",
    rules: "规则以策略源码或 YAML when/then 为准；本弹框仅作导航说明。",
    exampleHint: "可在下方查看源码/YAML 示例，或到策略编辑页查看完整正文。",
  };
}
