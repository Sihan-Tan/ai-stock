import { Alert } from "@heroui/react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { StockDetailView } from "../stock/StockDetailView";
import type { PositionContext } from "../stock/types";

type StockDetailLocationState = {
  position?: PositionContext | null;
};

/**
 * 解析路由参数并承载全页股票详情视图。
 */
export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const location = useLocation();
  const state = location.state as StockDetailLocationState | null;

  if (!symbol?.trim()) {
    return <Navigate to="/monitor" replace />;
  }

  if (!/^[A-Za-z0-9._-]+$/.test(symbol)) {
    return (
      <Alert color="warning" title="无效的股票代码">
        请使用有效的股票代码访问详情页。
      </Alert>
    );
  }

  return <StockDetailView symbol={symbol} position={state?.position ?? null} />;
}
