import { useState } from "react";
import { formatJsonText, JSON_COLLAPSE_THRESHOLD } from "./detectContentKind";

type Props = {
  /** 原始 JSON 文本（可为未格式化） */
  text: string;
  /** 强制默认折叠；缺省时按长度阈值 */
  defaultCollapsed?: boolean;
};

/**
 * 格式化 JSON 可折叠代码块。
 * @param props.text 原始文本
 * @param props.defaultCollapsed 是否默认折叠
 */
export function JsonCodeBlock({ text, defaultCollapsed }: Props) {
  const pretty = formatJsonText(text);
  const autoCollapse = pretty.length >= JSON_COLLAPSE_THRESHOLD;
  const [open, setOpen] = useState(!(defaultCollapsed ?? autoCollapse));

  return (
    <div className="research-json overflow-hidden rounded-lg border border-[var(--desk-line)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 bg-[var(--desk-ink)] px-3 py-1.5 text-left text-[11px] text-[var(--desk-mist)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>JSON · 已格式化</span>
        <span>{open ? "▾ 折叠" : "▸ 展开"}</span>
      </button>
      {open ? (
        <pre className="m-0 max-h-[min(50vh,420px)] overflow-auto bg-[var(--desk-panel)] px-3 py-2 font-mono text-xs leading-relaxed text-[var(--desk-text)] whitespace-pre">
          {pretty}
        </pre>
      ) : null}
    </div>
  );
}
