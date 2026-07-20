import type { FactorMeta } from "./types";

export type CollapsedCategory = { category: string; items: FactorMeta[] };

/**
 * 左栏：已选常显；未选按分类折叠。
 * @param factors 目录
 * @param selected 勾选 name 集合
 */
export function groupFactorCatalog(
  factors: FactorMeta[],
  selected: Set<string>
): { selected: FactorMeta[]; collapsedCategories: CollapsedCategory[] } {
  const selectedRows = factors.filter((f) => selected.has(f.name));
  const unselected = factors.filter((f) => !selected.has(f.name));
  const map = new Map<string, FactorMeta[]>();
  for (const f of unselected) {
    const list = map.get(f.category) ?? [];
    list.push(f);
    map.set(f.category, list);
  }
  const collapsedCategories = [...map.entries()].map(([category, items]) => ({ category, items }));
  return { selected: selectedRows, collapsedCategories };
}
