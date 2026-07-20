import type { FactorMeta } from "./types";

export type CollapsedCategory = { category: string; items: FactorMeta[] };

/**
 * 左栏：已选常显；分类下列出全部因子（含已选），按 category 分组供折叠浏览。
 * @param factors 目录
 * @param selected 勾选 name 集合
 */
export function groupFactorCatalog(
  factors: FactorMeta[],
  selected: Set<string>
): { selected: FactorMeta[]; collapsedCategories: CollapsedCategory[] } {
  const selectedRows = factors.filter((f) => selected.has(f.name));
  const map = new Map<string, FactorMeta[]>();
  for (const f of factors) {
    const list = map.get(f.category) ?? [];
    list.push(f);
    map.set(f.category, list);
  }
  const collapsedCategories = [...map.entries()].map(([category, items]) => ({ category, items }));
  return { selected: selectedRows, collapsedCategories };
}
