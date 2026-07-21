import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { parseSearchSymbol } from "./parseSearchSymbol";
import {
  resolveSearchNavigation,
  type SearchHit,
} from "./resolveSearchNavigation";

type SearchResponse = { query: string; items: SearchHit[] };

type SymbolSearchFieldProps = {
  /** 已确认的标的代码，如 600519.SH */
  value: string;
  /** 选中或确认后的回调 */
  onChange: (symbol: string) => void;
  /**
   * 选中时附带名称（搜索命中时有值；纯代码确认可能为空串）。
   * @param item 标准代码与名称
   */
  onPick?: (item: { symbol: string; name: string }) => void;
  /**
   * 确认后清空输入（用于「添加标的」类场景；父组件 value 常保持为空串）。
   */
  clearAfterCommit?: boolean;
  /** 输入框 className */
  className?: string;
  /** placeholder */
  placeholder?: string;
  /** 无障碍标签 */
  "aria-label"?: string;
};

/**
 * 标的搜索框：支持代码 / 名称 / 拼音，下拉选择后回写标准 symbol。
 * @param props 受控 value 与 onChange
 */
export function SymbolSearchField({
  value,
  onChange,
  onPick,
  clearAfterCommit = false,
  className,
  placeholder = "代码 / 名称 / 拼音",
  "aria-label": ariaLabel = "搜索标的",
}: SymbolSearchFieldProps) {
  const [query, setQuery] = useState(value);
  const [suggestions, setSuggestions] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const skipSearchRef = useRef(false);

  useEffect(() => {
    // 父组件清空 value 时必须清空输入（否则「代码 名称」展示态会因 startsWith("") 被跳过）
    if (value === "") {
      setQuery("");
      return;
    }
    // 外部 value 变化且本地未在编辑名称时同步展示
    const parsed = parseSearchSymbol(query);
    if (parsed === value) return;
    if (query.startsWith(value) && query.length > value.length) return;
    setQuery(value);
  }, [value]);

  useEffect(() => {
    if (skipSearchRef.current) {
      skipSearchRef.current = false;
      return;
    }
    const q = query.trim();
    if (!q || parseSearchSymbol(q) === value) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    const timer = window.setTimeout(() => {
      api<SearchResponse>(
        `/api/market/stock/search?q=${encodeURIComponent(q)}&limit=8`
      )
        .then((res) => {
          setSuggestions(res.items || []);
          setOpen((res.items || []).length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setOpen(false);
        });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query, value]);

  useEffect(() => {
    const onDocMouseDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  /**
   * 确认某一标的。
   * @param symbol 标准代码
   * @param name 股票名称（可空）
   * @param label 输入框展示文案
   */
  const commit = (symbol: string, name = "", label?: string) => {
    skipSearchRef.current = true;
    onChange(symbol);
    onPick?.({ symbol, name });
    setQuery(clearAfterCommit ? "" : label ?? (name ? `${symbol} ${name}` : symbol));
    setSuggestions([]);
    setOpen(false);
  };

  /**
   * 从当前输入与候选解析并确认。
   */
  const commitFromQuery = () => {
    // 已是「代码」或「代码 名称」展示态，失焦时不要冲掉名称
    if (value && (query === value || query.startsWith(`${value} `))) {
      const direct = parseSearchSymbol(value);
      if (direct) {
        const nameFromLabel = query.startsWith(`${direct} `)
          ? query.slice(direct.length + 1).trim()
          : "";
        onChange(direct);
        onPick?.({ symbol: direct, name: nameFromLabel });
      }
      setOpen(false);
      return;
    }
    const target = resolveSearchNavigation(query, suggestions);
    if (!target) {
      setQuery(value);
      setOpen(false);
      return;
    }
    const hit = suggestions.find((item) => item.symbol === target);
    commit(target, hit?.name ?? "", hit ? `${hit.symbol} ${hit.name}` : target);
  };

  return (
    <div ref={wrapRef} className="relative">
      <input
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-expanded={open}
        role="combobox"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commitFromQuery();
          }
          if (event.key === "Escape") {
            setOpen(false);
            setQuery(value);
          }
        }}
        onBlur={() => {
          // 延迟以允许点击下拉项（mousedown 已 preventDefault）
          window.setTimeout(() => {
            if (!wrapRef.current?.contains(document.activeElement)) {
              commitFromQuery();
            }
          }, 120);
        }}
        className={className}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <ul
          className="absolute left-0 top-full z-30 mt-1 max-h-60 w-full min-w-[16rem] overflow-auto rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-lg"
          role="listbox"
        >
          {suggestions.map((item) => (
            <li key={item.symbol}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--desk-line)]"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => commit(item.symbol, item.name, `${item.symbol} ${item.name}`)}
              >
                <span className="font-mono text-xs text-[var(--desk-mist)]">
                  {item.symbol}
                </span>
                <span className="truncate text-[var(--desk-text)]">{item.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
