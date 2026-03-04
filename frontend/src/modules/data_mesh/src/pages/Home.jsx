import { useEffect, useMemo, useState } from "react";
import {
  TeamOutlined,
  ShoppingOutlined,
  BarChartOutlined,
  DollarOutlined,
  CheckCircleFilled,
  WarningFilled,
  ClockCircleOutlined,
  LineChartOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined
} from "@ant-design/icons";
import { fetchOverview } from "../api/api";

export default function Home() {
  const [overview, setOverview] = useState(null);
  const [lastRefresh, setLastRefresh] = useState("");

  useEffect(() => {
    let mounted = true;
    const load = () => fetchOverview().then(data => {
      if (mounted) {
        setOverview(data);
        setLastRefresh(data.last_refreshed || "");
      }
    });
    load();
    const interval = setInterval(load, 30000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  const stats = useMemo(() => {
    if (!overview) return null;

    const users = Number(overview.user_count || 0);
    const products = Number(overview.product_count || 0);
    const sales = Number(overview.sales_count || 0);
    const totalSales = Number(overview.total_sales || 0);
    const healthy = Number(overview.healthy_domains || 0);
    const anomalous = Number(overview.anomalous_domains || 0);
    const totalDomains = healthy + anomalous;
    const healthPct = totalDomains > 0 ? Math.round((healthy / totalDomains) * 100) : 100;

    return {
      users,
      products,
      sales,
      totalSales,
      healthy,
      anomalous,
      healthPct,
      gatewayHealthy: anomalous === 0
    };
  }, [overview]);

  const kpiCards = useMemo(() => {
    if (!stats) return [];
    return [
      {
        key: "users",
        label: "Users",
        value: formatInt(stats.users),
        icon: <TeamOutlined />,
        trend: "+12%",
        trendData: buildTrend(stats.users)
      },
      {
        key: "products",
        label: "Products",
        value: formatInt(stats.products),
        icon: <ShoppingOutlined />,
        trend: "+8%",
        trendData: buildTrend(stats.products)
      },
      {
        key: "sales",
        label: "Sales",
        value: formatInt(stats.sales),
        icon: <BarChartOutlined />,
        trend: "+6%",
        trendData: buildBars(stats.sales)
      },
      {
        key: "amount",
        label: "Total Sales (LKR)",
        value: formatInt(stats.totalSales),
        suffix: "Rs.",
        icon: <DollarOutlined />,
        trend: "+5%",
        trendData: buildTrend(stats.totalSales)
      }
    ];
  }, [stats]);

  if (!overview || !stats) return <div className="section">Loading...</div>;

  const anomalies = overview.recent_anomalies || [];

  return (
    <div className="dm-ov-wrap">
      <div className="dm-ov-top">
        <h2 className="dm-ov-title">Dashboard Overview</h2>
        <div className="dm-ov-gateway">
          <div className="dm-ov-gateway-badge" aria-hidden="true">
            <span className="dm-ov-pulse-icon"><span /></span>
          </div>
          <div className="dm-ov-gateway-content">
            <div className="dm-ov-gateway-label">API GATEWAY STATUS</div>
            <div className={`dm-ov-gateway-value ${stats.gatewayHealthy ? "ok" : "warn"}`}>
              {stats.gatewayHealthy ? "HEALTHY" : "DEGRADED"}
            </div>
          </div>
          <div className="dm-ov-gateway-time">
            Last Check: {lastRefresh ? new Date(lastRefresh).toLocaleString() : "-"}
          </div>
          <button className="dm-ov-check-btn" type="button">Check Now</button>
        </div>
      </div>

      <div className="dm-ov-kpi-grid">
        {kpiCards.map((card) => (
          <KpiCard key={card.key} {...card} />
        ))}
      </div>

      <div className="dm-ov-status-grid">
        <StatusCard label="Healthy Domains" value={stats.healthy} tone="success" icon={<CheckCircleFilled />} />
        <StatusCard label="Anomalous Domains" value={stats.anomalous} tone="warning" icon={<WarningFilled />} />
        <StatusCard
          label="Last Refreshed"
          value={overview.last_refreshed ? new Date(overview.last_refreshed).toLocaleString() : "-"}
          tone="neutral"
          icon={<ClockCircleOutlined />}
          valueSmall
        />
      </div>

      <div className="dm-ov-table-card">
        <h3 className="dm-ov-section-title">Recent Anomalies (Past 24 Hours)</h3>
        {anomalies.length > 0 ? (
          <div className="dm-ov-table-wrap">
          <table className="dm-ov-table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Anomaly Type</th>
                <th>Timestamp</th>
                <th>Domain</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((a, i) => (
                <tr key={i}>
                  <td>
                    <PriorityBadge index={i} />
                  </td>
                  <td>{anomalyMessage(a.domain_name, i)}</td>
                  <td>{a.timestamp ? new Date(a.timestamp).toLocaleString() : "-"}</td>
                  <td>{a.domain_name || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        ) : (
          <div className="dm-ov-empty">No recent anomalies detected.</div>
        )}
      </div>

      <div className="dm-ov-footer-note">
        <LineChartOutlined /> Overall Health Score: <strong>{stats.healthPct}%</strong>
      </div>
    </div>
  );
}

function KpiCard({ label, value, suffix, icon, trend, trendData }) {
  return (
    <div className="dm-ov-kpi-card">
      <div className="dm-ov-kpi-head">
        <div className="dm-ov-kpi-label">{label}</div>
        <div className="dm-ov-kpi-icon">{icon}</div>
      </div>
      <div className="dm-ov-kpi-value">{value ?? "-"}{suffix ? <span className="dm-ov-kpi-suffix"> {suffix}</span> : null}</div>
      <div className="dm-ov-kpi-bottom">
        <MiniTrend data={trendData} />
        <div className="dm-ov-kpi-trend"><ArrowUpOutlined /> {trend}</div>
      </div>
    </div>
  );
}

function StatusCard({ label, value, tone, icon, valueSmall = false }) {
  return (
    <div className="dm-ov-status-card">
      <div className={`dm-ov-status-icon ${tone}`}>{icon}</div>
      <div className="dm-ov-status-content">
        <div className="dm-ov-status-label">{label}</div>
        <div className={`dm-ov-status-value ${valueSmall ? "small" : ""}`}>{value ?? "-"}</div>
      </div>
    </div>
  );
}

function PriorityBadge({ index }) {
  const priorityMap = [
    { label: "High", className: "high", mark: "H" },
    { label: "Medium", className: "medium", mark: "M" },
    { label: "Low", className: "low", mark: "✓" }
  ];
  const priority = priorityMap[index % priorityMap.length];
  return (
    <span className={`dm-ov-priority ${priority.className}`}>
      <span className="dm-ov-priority-mark">{priority.mark}</span>
      {priority.label}
    </span>
  );
}

function MiniTrend({ data = [] }) {
  if (!data.length) return null;
  const width = 92;
  const height = 30;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * (width - 2) + 1;
      const y = height - (((d - min) / range) * (height - 8) + 4);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} className="dm-ov-trend-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline fill="none" stroke="#5b88c7" strokeWidth="2.2" points={points} />
    </svg>
  );
}

function buildTrend(seed) {
  const base = Math.max(5, Math.log10(Math.max(1, Number(seed || 1))) * 10);
  return [
    base * 0.72,
    base * 0.84,
    base * 0.79,
    base * 0.95,
    base * 0.9,
    base * 1.08,
    base * 1.16
  ].map((n) => Number(n.toFixed(2)));
}

function buildBars(seed) {
  const base = Math.max(6, Math.log10(Math.max(1, Number(seed || 1))) * 8);
  return [
    base * 0.5,
    base * 0.62,
    base * 0.84,
    base * 0.7,
    base * 1.0,
    base * 0.82,
    base * 0.92,
    base * 1.18
  ].map((n) => Number(n.toFixed(2)));
}

function anomalyMessage(domainName, idx) {
  const domain = String(domainName || "domain").replace(/_/g, " ");
  const templates = [
    "Spike in API Error Rates",
    "Unusual Traffic Pattern",
    "Data Latency Issue"
  ];
  return `${templates[idx % templates.length]} (${domain})`;
}

function formatInt(value) {
  const n = Number(value || 0);
  return n.toLocaleString();
}