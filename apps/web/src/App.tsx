import { useEffect, useMemo, useState } from "react";

type Page =
  | "overview"
  | "watchlist"
  | "sentiment"
  | "lhb"
  | "calendar"
  | "strategies"
  | "factors"
  | "paper"
  | "risk"
  | "alerts"
  | "ai"
  | "morning"
  | "review"
  | "knowledge";

const NAV: { id: Page; label: string }[] = [
  { id: "overview", label: "总览" },
  { id: "watchlist", label: "行情自选" },
  { id: "sentiment", label: "打板情绪" },
  { id: "lhb", label: "龙虎榜" },
  { id: "calendar", label: "日历/停牌" },
  { id: "strategies", label: "策略" },
  { id: "factors", label: "因子/ML" },
  { id: "paper", label: "模拟盘" },
  { id: "risk", label: "实盘风控" },
  { id: "alerts", label: "告警" },
  { id: "ai", label: "投研 nanobot" },
  { id: "morning", label: "晨会" },
  { id: "review", label: "复盘" },
  { id: "knowledge", label: "知识库" },
];

/**
 * 调用后端 JSON API。
 * @param path API 路径
 * @param init fetch 选项
 */
async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as T;
}

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState("就绪");

  useEffect(() => {
    api<Record<string, unknown>>("/health")
      .then(setHealth)
      .catch((e) => setLog(String(e)));
  }, []);

  const title = useMemo(() => NAV.find((n) => n.id === page)?.label ?? "", [page]);

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          刻度<span>·</span>Desk
        </div>
        {NAV.map((n) => (
          <button
            key={n.id}
            type="button"
            className={page === n.id ? "active" : ""}
            onClick={() => setPage(n.id)}
          >
            {n.label}
          </button>
        ))}
      </aside>
      <main className="main">
        <h1>{title}</h1>
        <div className="card muted">
          API 健康：{health ? JSON.stringify(health) : "检测中…"} · {log}
        </div>
        {page === "overview" && <Overview setLog={setLog} />}
        {page === "watchlist" && <Watchlist setLog={setLog} />}
        {page === "sentiment" && <Sentiment setLog={setLog} />}
        {page === "lhb" && <Lhb setLog={setLog} />}
        {page === "calendar" && <CalendarPanel setLog={setLog} />}
        {page === "strategies" && <Strategies setLog={setLog} />}
        {page === "factors" && <Factors setLog={setLog} />}
        {page === "paper" && <Paper setLog={setLog} />}
        {page === "risk" && <RiskPanel setLog={setLog} />}
        {page === "alerts" && <Alerts setLog={setLog} />}
        {page === "ai" && <Research setLog={setLog} />}
        {page === "morning" && <Morning setLog={setLog} />}
        {page === "review" && <ReviewPanel setLog={setLog} />}
        {page === "knowledge" && <Knowledge setLog={setLog} />}
      </main>
    </div>
  );
}

function Overview({ setLog }: { setLog: (s: string) => void }) {
  const seedAll = async () => {
    try {
      await api("/api/market/seed", { method: "POST" });
      await api("/api/calendar/seed", { method: "POST" });
      await api("/api/sentiment/seed", { method: "POST" });
      await api("/api/lhb/seed", { method: "POST" });
      await api("/api/strategies/sync-python", { method: "POST" });
      await api("/api/strategies/load-yaml-file", { method: "POST" });
      setLog("已写入演示数据");
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <div className="card">
      <p className="muted">v1 已冻结功能的工作台壳。先注入演示数据，再浏览各页。</p>
      <button type="button" className="btn primary" onClick={seedAll}>
        注入演示数据
      </button>
    </div>
  );
}

function Watchlist({ setLog }: { setLog: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const load = () =>
    api<any[]>("/api/market/watchlist")
      .then(setRows)
      .catch((e) => setLog(String(e)));
  useEffect(() => {
    load();
  }, []);
  return (
    <div className="card">
      <div className="row">
        <button type="button" className="btn" onClick={load}>
          刷新
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>现价</th>
            <th>涨跌</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td className="mono">{r.symbol}</td>
              <td>{r.name}</td>
              <td className="mono">{r.last}</td>
              <td className="mono">{r.pct_chg}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Sentiment({ setLog }: { setLog: (s: string) => void }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api("/api/sentiment/seed", { method: "POST" })
      .then(() => api("/api/sentiment/snapshot"))
      .then(setData)
      .catch((e) => setLog(String(e)));
  }, []);
  if (!data) return <div className="card muted">加载中…</div>;
  return (
    <div className="card">
      <p className="mono">
        涨停 {data.limit_up_count} · 跌停 {data.limit_down_count} · 最高 {data.max_board} 板 · 晋级率{" "}
        {data.promote_rate}
      </p>
      <table>
        <thead>
          <tr>
            <th>高度</th>
            <th>代码</th>
            <th>名称</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {data.ladder?.map((x: any) => (
            <tr key={x.symbol}>
              <td>{x.board_height}</td>
              <td className="mono">{x.symbol}</td>
              <td>{x.name}</td>
              <td>{x.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Lhb({ setLog }: { setLog: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api("/api/lhb/seed", { method: "POST" })
      .then(() => api<any[]>("/api/lhb"))
      .then(setRows)
      .catch((e) => setLog(String(e)));
  }, []);
  return (
    <div className="card">
      <pre>{JSON.stringify(rows, null, 2)}</pre>
    </div>
  );
}

function CalendarPanel({ setLog }: { setLog: (s: string) => void }) {
  const [month, setMonth] = useState<any[]>([]);
  const [susp, setSusp] = useState<any[]>([]);
  useEffect(() => {
    const now = new Date();
    api("/api/calendar/seed", { method: "POST" })
      .then(() =>
        Promise.all([
          api(`/api/calendar/month?year=${now.getFullYear()}&month=${now.getMonth() + 1}`),
          api("/api/calendar/suspensions"),
        ])
      )
      .then(([m, s]) => {
        setMonth(m as any[]);
        setSusp(s as any[]);
      })
      .catch((e) => setLog(String(e)));
  }, []);
  return (
    <>
      <div className="card">
        <h3>本月交易日（{month.filter((x) => x.is_open).length}）</h3>
        <p className="muted mono">{month.slice(0, 10).map((x) => x.date).join(" · ")} …</p>
      </div>
      <div className="card">
        <h3>停牌提醒</h3>
        <pre>{JSON.stringify(susp, null, 2)}</pre>
      </div>
    </>
  );
}

function Strategies({ setLog }: { setLog: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const load = () =>
    api<any[]>("/api/strategies")
      .then(setRows)
      .catch((e) => setLog(String(e)));
  useEffect(() => {
    api("/api/strategies/sync-python", { method: "POST" })
      .then(() => api("/api/strategies/load-yaml-file", { method: "POST" }))
      .then(load)
      .catch((e) => setLog(String(e)));
  }, []);
  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>名称</th>
            <th>来源</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.id}-${r.version}`}>
              <td className="mono">{r.id}</td>
              <td>{r.name}</td>
              <td>{r.source}</td>
              <td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Paper({ setLog }: { setLog: (s: string) => void }) {
  const [sum, setSum] = useState<any>(null);
  const refresh = () =>
    api("/api/broker/paper")
      .then(setSum)
      .catch((e) => setLog(String(e)));
  useEffect(() => {
    refresh();
  }, []);
  const buy = async () => {
    try {
      await api("/api/broker/order", {
        method: "POST",
        body: JSON.stringify({
          symbol: "600519.SH",
          side: "buy",
          qty: 100,
          price: 1680,
          mode: "paper",
        }),
      });
      await refresh();
      setLog("模拟买入完成");
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <div className="card">
      <div className="row">
        <button type="button" className="btn primary" onClick={buy}>
          模拟买入 600519
        </button>
        <button type="button" className="btn" onClick={refresh}>
          刷新
        </button>
      </div>
      <pre>{JSON.stringify(sum, null, 2)}</pre>
    </div>
  );
}

function Research({ setLog }: { setLog: (s: string) => void }) {
  const [skills, setSkills] = useState<any[]>([]);
  const [q, setQ] = useState("帮我写一个竞价高开策略草稿");
  const [ans, setAns] = useState("");
  useEffect(() => {
    api<any[]>("/api/ai/skills")
      .then(setSkills)
      .catch((e) => setLog(String(e)));
  }, []);
  const send = async () => {
    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: q }] }),
      });
      setAns(await res.text());
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <>
      <div className="card">
        <h3>Skills</h3>
        <ul>
          {skills.map((s) => (
            <li key={s.name}>
              <span className="mono">{s.name}</span> — {s.description}
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <textarea rows={3} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="row" style={{ marginTop: 8 }}>
          <button type="button" className="btn primary" onClick={send}>
            发送
          </button>
        </div>
        <pre>{ans}</pre>
      </div>
    </>
  );
}

function Morning({ setLog }: { setLog: (s: string) => void }) {
  const [pre, setPre] = useState<any>(null);
  const [post, setPost] = useState<any>(null);
  const run = async () => {
    try {
      setPre(await api("/api/morning/preopen", { method: "POST" }));
      setPost(await api("/api/morning/post-auction", { method: "POST" }));
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <div className="card">
      <button type="button" className="btn primary" onClick={run}>
        运行开盘前 + 竞价选拔
      </button>
      <pre>{JSON.stringify({ pre, post }, null, 2)}</pre>
    </div>
  );
}

function Knowledge({ setLog }: { setLog: (s: string) => void }) {
  const [docs, setDocs] = useState<any[]>([]);
  const upload = async () => {
    try {
      await api("/api/knowledge/docs", {
        method: "POST",
        body: JSON.stringify({
          title: "半导体景气笔记",
          tags: "半导体",
          content: "高位晋级率若连续两日低于 30%，短线情绪退潮概率上升。连板高度与溢价需分开看。",
        }),
      });
      setDocs(await api("/api/knowledge/docs"));
      setLog("已上传笔记");
    } catch (e) {
      setLog(String(e));
    }
  };
  useEffect(() => {
    api<any[]>("/api/knowledge/docs")
      .then(setDocs)
      .catch(() => undefined);
  }, []);
  return (
    <div className="card">
      <button type="button" className="btn primary" onClick={upload}>
        上传示例笔记
      </button>
      <pre>{JSON.stringify(docs, null, 2)}</pre>
    </div>
  );
}

function Factors({ setLog }: { setLog: (s: string) => void }) {
  const [factors, setFactors] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [cmp, setCmp] = useState<any>(null);
  const refresh = async () => {
    try {
      setFactors(await api("/api/factors"));
      setModels(await api("/api/ml/models"));
    } catch (e) {
      setLog(String(e));
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  const trainBoth = async () => {
    try {
      setCmp(await api("/api/ml/compare-engines", { method: "POST" }));
      await refresh();
      setLog("双引擎对比训练完成");
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <>
      <div className="card">
        <div className="row">
          <button type="button" className="btn primary" onClick={trainBoth}>
            LGBM vs XGB 对比训练
          </button>
          <button type="button" className="btn" onClick={refresh}>
            刷新
          </button>
        </div>
        <h3>因子库</h3>
        <pre>{JSON.stringify(factors, null, 2)}</pre>
      </div>
      <div className="card">
        <h3>模型</h3>
        <pre>{JSON.stringify(models, null, 2)}</pre>
        {cmp && (
          <>
            <h3>引擎对比</h3>
            <pre>{JSON.stringify(cmp, null, 2)}</pre>
          </>
        )}
      </div>
    </>
  );
}

function RiskPanel({ setLog }: { setLog: (s: string) => void }) {
  const [risk, setRisk] = useState<any>(null);
  const [qmt, setQmt] = useState<any>(null);
  const load = async () => {
    try {
      setRisk(await api("/api/broker/risk"));
      setQmt(await api("/api/broker/qmt/ping"));
    } catch (e) {
      setLog(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);
  const arm = async () => {
    try {
      setRisk(
        await api("/api/broker/risk", {
          method: "POST",
          body: JSON.stringify({ armed: true, whitelist: ["600519.SH"] }),
        })
      );
      setLog("已 ARM（仍需白名单内标的）");
    } catch (e) {
      setLog(String(e));
    }
  };
  const kill = async () => {
    try {
      setRisk(await api("/api/broker/risk", { method: "POST", body: JSON.stringify({ kill_switch: true }) }));
      setLog("Kill Switch 已开启");
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <div className="card">
      <div className="row">
        <button type="button" className="btn primary" onClick={arm}>
          ARM
        </button>
        <button type="button" className="btn" onClick={kill}>
          Kill Switch
        </button>
        <button type="button" className="btn" onClick={load}>
          刷新
        </button>
      </div>
      <pre>{JSON.stringify({ qmt, risk }, null, 2)}</pre>
    </div>
  );
}

function Alerts({ setLog }: { setLog: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const load = () =>
    api<any[]>("/api/alerts")
      .then(setRows)
      .catch((e) => setLog(String(e)));
  useEffect(() => {
    load();
  }, []);
  const send = async () => {
    try {
      await api("/api/alerts/send", {
        method: "POST",
        body: JSON.stringify({ title: "演示告警", body: "来自前端", dedupe_key: `ui-${Date.now()}` }),
      });
      await load();
    } catch (e) {
      setLog(String(e));
    }
  };
  return (
    <div className="card">
      <button type="button" className="btn primary" onClick={send}>
        发送演示告警
      </button>
      <pre>{JSON.stringify(rows, null, 2)}</pre>
    </div>
  );
}

function ReviewPanel({ setLog }: { setLog: (s: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const save = async () => {
    try {
      const asof = new Date().toISOString().slice(0, 10);
      await api("/api/review", {
        method: "POST",
        body: JSON.stringify({ asof, content: "盘面复盘：情绪与执行偏差备注", deviations: [{ type: "slip" }] }),
      });
      setRows(await api("/api/review"));
      setLog("复盘已保存");
    } catch (e) {
      setLog(String(e));
    }
  };
  useEffect(() => {
    api<any[]>("/api/review")
      .then(setRows)
      .catch(() => undefined);
  }, []);
  return (
    <div className="card">
      <button type="button" className="btn primary" onClick={save}>
        写入今日复盘
      </button>
      <pre>{JSON.stringify(rows, null, 2)}</pre>
    </div>
  );
}
