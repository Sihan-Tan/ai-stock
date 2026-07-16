import { parseSearchSymbol } from "./parseSearchSymbol";

export type SearchHit = {
  symbol: string;
  name: string;
  match_type?: string;
};

/**
 * 根据输入与当前候选决定跳转 symbol；无法跳转时返回 null。
 * @param query 搜索框原文
 * @param items 当前下拉候选（已按相关度排序）
 */
export function resolveSearchNavigation(
  query: string,
  items: SearchHit[]
): string | null {
  const direct = parseSearchSymbol(query);
  if (direct) return direct;
  if (items.length > 0) return items[0].symbol;
  return null;
}
