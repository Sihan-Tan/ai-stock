import {
  DATE_RANGE_PRESET_OPTIONS,
  applyPreset,
  type DateRangePreset,
  type DateRangeValue,
  validateDateRange,
} from "./dateRange";

export type DateRangePresetSelectProps = {
  /** 当前区间 */
  value: DateRangeValue;
  /** 变更回调 */
  onChange: (next: DateRangeValue) => void;
  /** 无障碍标签 */
  "aria-label"?: string;
  /** 附加 class */
  className?: string;
};

const controlClass =
  "rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 时间区间选择：快捷项 + 自定义起止日。
 * @param props 受控值与回调
 */
export function DateRangePresetSelect({
  value,
  onChange,
  "aria-label": ariaLabel = "时间区间",
  className = "",
}: DateRangePresetSelectProps) {
  const rangeError =
    value.preset === "custom" ? validateDateRange(value.start, value.end) : null;

  /**
   * 切换快捷项。
   * @param preset 新快捷项
   */
  const onPresetChange = (preset: DateRangePreset) => {
    onChange(applyPreset(value, preset));
  };

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`.trim()}>
      <select
        value={value.preset}
        onChange={(e) => onPresetChange(e.target.value as DateRangePreset)}
        aria-label={ariaLabel}
        className={controlClass}
      >
        {DATE_RANGE_PRESET_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {value.preset === "custom" ? (
        <>
          <label className="flex items-center gap-1.5 text-xs text-[var(--desk-mist)]">
            <span>起</span>
            <input
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(e) =>
                onChange({ ...value, preset: "custom", start: e.target.value })
              }
              aria-label="开始日期"
              className={controlClass}
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-[var(--desk-mist)]">
            <span>止</span>
            <input
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(e) =>
                onChange({ ...value, preset: "custom", end: e.target.value })
              }
              aria-label="结束日期"
              className={controlClass}
            />
          </label>
          {rangeError ? <span className="text-xs text-red-400">{rangeError}</span> : null}
        </>
      ) : null}
    </div>
  );
}
