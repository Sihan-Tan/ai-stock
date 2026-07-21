import { groupFactorCatalog } from "./groupFactors";
import type { FactorMeta } from "./types";

/** 分类英文 key → 中文展示 */
const CATEGORY_LABELS: Record<string, string> = {
  overlap: "重叠指标",
  momentum: "动量",
  volatility: "波动",
  volume: "成交量",
  pattern: "K线形态",
  cycle: "周期",
  price: "价格变换",
  statistic: "统计",
  math: "数学",
  ml: "机器学习",
  other: "其他",
};

/**
 * @param category 注册表 category
 */
function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

export type FactorCatalogProps = {
  /** 目录元数据 */
  factors: FactorMeta[];
  /** 当前勾选 name */
  selected: Set<string>;
  /** 切换勾选 */
  onToggle: (name: string) => void;
  /** 搜索关键字 */
  query: string;
  /** 更新搜索关键字 */
  onQuery: (query: string) => void;
  /** 副图同时勾选上限 */
  panelLimit: number;
  /** 当前已选副图数量 */
  panelSelectedCount: number;
};

/**
 * 左栏因子目录：已选常显；分类下列出全部因子；副图满额时禁用未勾选的 panel。
 * @param props 目录数据与勾选受控状态
 */
export function FactorCatalog({
  factors,
  selected,
  onToggle,
  query,
  onQuery,
  panelLimit,
  panelSelectedCount,
}: FactorCatalogProps) {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? factors.filter(
        (f) => f.label.toLowerCase().includes(q) || f.name.toLowerCase().includes(q)
      )
    : factors;
  const { selected: selectedRows, collapsedCategories } = groupFactorCatalog(filtered, selected);
  const panelFull = panelSelectedCount >= panelLimit;

  /**
   * 未勾选的副图在满额时不可再选；已选与主图 overlay 始终可操作。
   * @param factor 因子元数据
   */
  const isToggleDisabled = (factor: FactorMeta): boolean => {
    if (selected.has(factor.name)) return false;
    if (factor.plot !== "panel") return false;
    return panelFull;
  };

  return (
    <aside className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] p-3">
      <input
        type="search"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="搜索因子"
        aria-label="搜索因子"
        className="w-full rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)] outline-none placeholder:text-[var(--desk-mist)] focus:border-[var(--desk-accent)]"
      />

      <p className="text-[11px] leading-snug text-[var(--desk-mist)]">
        副图 {panelSelectedCount}/{panelLimit}
        {panelFull ? " · 已满，先取消部分副图后再勾选" : " · 主图叠加不限"}
      </p>

      <section>
        <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-[var(--desk-mist)]">
          已选
        </h3>
        {selectedRows.length === 0 ? (
          <p className="text-xs text-[var(--desk-mist)]">暂无勾选</p>
        ) : (
          <ul className="space-y-1">
            {selectedRows.map((factor) => (
              <FactorCheckRow
                key={factor.name}
                factor={factor}
                checked
                disabled={false}
                onToggle={onToggle}
              />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-1.5">
        <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--desk-mist)]">
          全部分类
        </h3>
        {collapsedCategories.length === 0 ? (
          <p className="text-xs text-[var(--desk-mist)]">无因子</p>
        ) : (
          collapsedCategories.map(({ category, items }) => (
            <details
              key={category}
              className="rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)]/40 px-2 py-1"
            >
              <summary className="cursor-pointer select-none py-1 text-sm text-[var(--desk-text)]">
                {categoryLabel(category)}
                <span className="ml-1 text-xs text-[var(--desk-mist)]">({items.length})</span>
              </summary>
              <ul className="space-y-1 pb-1.5 pt-1">
                {items.map((factor) => (
                  <FactorCheckRow
                    key={factor.name}
                    factor={factor}
                    checked={selected.has(factor.name)}
                    disabled={isToggleDisabled(factor)}
                    onToggle={onToggle}
                  />
                ))}
              </ul>
            </details>
          ))
        )}
      </section>
    </aside>
  );
}

type FactorCheckRowProps = {
  factor: FactorMeta;
  checked: boolean;
  disabled: boolean;
  onToggle: (name: string) => void;
};

/**
 * 单个因子勾选行。
 * @param props 因子元数据与勾选状态
 */
function FactorCheckRow({ factor, checked, disabled, onToggle }: FactorCheckRowProps) {
  const title =
    disabled && factor.plot === "panel"
      ? "副图已满，请先取消部分已选副图"
      : undefined;

  return (
    <li>
      <label
        title={title}
        className={`flex items-start gap-2 rounded px-1 py-0.5 text-sm ${
          disabled
            ? "cursor-not-allowed opacity-45"
            : "cursor-pointer text-[var(--desk-text)] hover:bg-[var(--desk-ink)]/60"
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={() => {
            if (!disabled) onToggle(factor.name);
          }}
          className="mt-0.5 accent-[var(--desk-accent)] disabled:cursor-not-allowed"
        />
        <span className="min-w-0 leading-snug">
          <span className="block truncate">{factor.label}</span>
          <span className="block truncate text-[10px] text-[var(--desk-mist)]">
            {factor.name}
            {factor.plot === "panel" ? " · 副图" : " · 主图"}
          </span>
        </span>
      </label>
    </li>
  );
}
