import { beijingToday } from "../api";

/** 时间区间快捷键 */
export type DateRangePreset = "1m" | "3m" | "6m" | "1y" | "custom";

/** 受控时间区间值（日期均为北京日历 YYYY-MM-DD） */
export type DateRangeValue = {
  preset: DateRangePreset;
  start: string;
  end: string;
};

/** 快捷项展示 */
export const DATE_RANGE_PRESET_OPTIONS: ReadonlyArray<{
  value: DateRangePreset;
  label: string;
}> = [
  { value: "1m", label: "近1个月" },
  { value: "3m", label: "近3个月" },
  { value: "6m", label: "近半年" },
  { value: "1y", label: "近1年" },
  { value: "custom", label: "自定义" },
];

/**
 * 按快捷项推算起止日（北京日期）。
 * @param preset 快捷项；custom 时返回 today 往前 1 年作为初始自定义区间
 * @param today 可选锚点日，默认 beijingToday()
 */
export function boundsForPreset(
  preset: Exclude<DateRangePreset, "custom"> | "custom",
  today: string = beijingToday()
): { start: string; end: string } {
  const end = today;
  const endDate = new Date(`${end}T12:00:00Z`);
  const startDate = new Date(endDate);
  if (preset === "1m") {
    startDate.setUTCMonth(startDate.getUTCMonth() - 1);
  } else if (preset === "3m") {
    startDate.setUTCMonth(startDate.getUTCMonth() - 3);
  } else if (preset === "6m") {
    startDate.setUTCMonth(startDate.getUTCMonth() - 6);
  } else {
    // 1y 与 custom 初始默认
    startDate.setUTCFullYear(startDate.getUTCFullYear() - 1);
  }
  return { start: startDate.toISOString().slice(0, 10), end };
}

/**
 * 构建默认区间值（近1年）。
 * @param today 可选锚点日
 */
export function defaultDateRangeValue(today: string = beijingToday()): DateRangeValue {
  const { start, end } = boundsForPreset("1y", today);
  return { preset: "1y", start, end };
}

/**
 * 切换快捷项后的下一状态。
 * @param prev 当前值
 * @param preset 新快捷项
 * @param today 可选锚点日
 */
export function applyPreset(
  prev: DateRangeValue,
  preset: DateRangePreset,
  today: string = beijingToday()
): DateRangeValue {
  if (preset === "custom") {
    return {
      preset: "custom",
      start: prev.start || boundsForPreset("1y", today).start,
      end: prev.end || today,
    };
  }
  const { start, end } = boundsForPreset(preset, today);
  return { preset, start, end };
}

/**
 * 校验自定义区间：start <= end；非法时返回错误文案。
 * @param start 起点
 * @param end 终点
 */
export function validateDateRange(start: string, end: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return "请填写有效日期";
  }
  if (start > end) {
    return "开始日期不能晚于结束日期";
  }
  return null;
}
