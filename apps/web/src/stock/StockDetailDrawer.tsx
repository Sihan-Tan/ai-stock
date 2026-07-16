import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { StockDetailView } from "./StockDetailView";
import type { PositionContext } from "./types";

type Props = {
  open: boolean;
  symbol: string;
  position?: PositionContext | null;
  onClose: () => void;
};

/**
 * 以右侧抽屉展示股票详情，并可跳转至对应的完整详情页。
 * @param props 抽屉开关、股票代码、可选持仓上下文及关闭处理函数
 */
export function StockDetailDrawer({ open, symbol, position = null, onClose }: Props) {
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;

  /**
   * 打开全页详情后关闭当前抽屉，避免返回时保留遮罩。
   */
  const expand = () => {
    navigate(`/stock/${encodeURIComponent(symbol)}`, { state: { position } });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 cursor-default bg-black/50"
        aria-label="关闭股票详情抽屉"
        onClick={onClose}
      />
      <aside
        aria-label="股票详情"
        aria-modal="true"
        className="relative z-10 ml-auto h-full w-full max-w-4xl overflow-y-auto border-l border-[var(--desk-line)] bg-[var(--desk-ink)] p-4 shadow-2xl sm:p-6"
        role="dialog"
      >
        <StockDetailView
          symbol={symbol}
          position={position}
          compact
          onExpand={expand}
          onClose={onClose}
        />
      </aside>
    </div>
  );
}
