import { groupFactorCatalog } from "./groupFactors";
import type { FactorMeta } from "./types";

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
};

/**
 * 左栏因子目录：已选常显，未选按分类折叠，支持搜索过滤。
 * @param props 目录数据与勾选受控状态
 */
export function FactorCatalog({
  factors,
  selected,
  onToggle,
  query,
  onQuery,
}: FactorCatalogProps) {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? factors.filter(
        (f) => f.label.toLowerCase().includes(q) || f.name.toLowerCase().includes(q)
      )
    : factors;
  const { selected: selectedRows, collapsedCategories } = groupFactorCatalog(filtered, selected);

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
                onToggle={onToggle}
              />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-1.5">
        <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--desk-mist)]">
          分类
        </h3>
        {collapsedCategories.length === 0 ? (
          <p className="text-xs text-[var(--desk-mist)]">无更多因子</p>
        ) : (
          collapsedCategories.map(({ category, items }) => (
            <details
              key={category}
              className="rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)]/40 px-2 py-1"
            >
              <summary className="cursor-pointer select-none py-1 text-sm text-[var(--desk-text)]">
                {category}
                <span className="ml-1 text-xs text-[var(--desk-mist)]">({items.length})</span>
              </summary>
              <ul className="space-y-1 pb-1.5 pt-1">
                {items.map((factor) => (
                  <FactorCheckRow
                    key={factor.name}
                    factor={factor}
                    checked={false}
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
  onToggle: (name: string) => void;
};

/**
 * 单个因子勾选行。
 * @param props 因子元数据与勾选状态
 */
function FactorCheckRow({ factor, checked, onToggle }: FactorCheckRowProps) {
  return (
    <li>
      <label className="flex cursor-pointer items-start gap-2 rounded px-1 py-0.5 text-sm text-[var(--desk-text)] hover:bg-[var(--desk-ink)]/60">
        <input
          type="checkbox"
          checked={checked}
          onChange={() => onToggle(factor.name)}
          className="mt-0.5 accent-[var(--desk-accent)]"
        />
        <span className="min-w-0 leading-snug">
          <span className="block truncate">{factor.label}</span>
          <span className="block truncate text-[10px] text-[var(--desk-mist)]">{factor.name}</span>
        </span>
      </label>
    </li>
  );
}
