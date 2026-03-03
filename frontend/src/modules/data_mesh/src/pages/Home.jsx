import { useEffect, useState } from "react";
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

  if (!overview) return <div className="section">Loading...</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <h2 style={{ marginBottom: 0, fontWeight: 700 }}>Dashboard Overview</h2>
        <span className="env-badge">Production</span>
        <span className="last-refresh">Last refresh: {lastRefresh ? new Date(lastRefresh).toLocaleString() : "-"}</span>
      </div>
      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <KpiCard label="Users" value={overview.user_count} />
        <KpiCard label="Products" value={overview.product_count} />
        <KpiCard label="Sales" value={overview.sales_count} />
        <KpiCard label="Total Sales (LKR)" value={overview.total_sales?.toLocaleString()} />
      </div>
      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <StatusCard label="Healthy Domains" value={overview.healthy_domains} color="#4caf50" icon="✔️" />
        <StatusCard label="Anomalous Domains" value={overview.anomalous_domains} color="#f44336" icon="⚠️" />
        <KpiCard label="Last Refreshed" value={overview.last_refreshed ? new Date(overview.last_refreshed).toLocaleString() : "-"} />
      </div>
      <div className="section">
        <h3 style={{ fontWeight: 600 }}>Recent Anomalies</h3>
        {overview.recent_anomalies && overview.recent_anomalies.length > 0 ? (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: 8 }}>Domain</th>
                <th style={{ textAlign: "left", padding: 8 }}>Detected At</th>
              </tr>
            </thead>
            <tbody>
              {overview.recent_anomalies.map((a, i) => (
                <tr key={i} style={{ background: i % 2 ? "#f9f9f9" : "white" }}>
                  <td style={{ padding: 8 }}>{a.domain_name}</td>
                  <td style={{ padding: 8 }}>{new Date(a.timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: "#4caf50" }}>No recent anomalies detected.</div>
        )}
      </div>
    </div>
  );
}

function KpiCard({ label, value }) {
  return (
    <div className="ant-card" style={{ padding: 16, minWidth: 160 }}>
      <div style={{ fontSize: 14, color: "#888" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 600 }}>{value ?? "-"}</div>
    </div>
  );
}

function StatusCard({ label, value, color, icon }) {
  return (
    <div className="ant-card" style={{ padding: 16, minWidth: 180, display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ fontSize: 24 }}>{icon}</span>
      <div>
        <div style={{ fontSize: 14, color: "#888" }}>{label}</div>
        <div style={{ fontSize: 24, fontWeight: 600, color }}>{value ?? "-"}</div>
      </div>
    </div>
  );
}