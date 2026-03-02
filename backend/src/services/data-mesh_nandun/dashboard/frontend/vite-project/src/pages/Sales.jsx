import { useEffect, useState } from "react";
import { fetchSales } from "../api/api";

export default function Sales() {
  const [sales, setSales] = useState([]);
  const [lastModified, setLastModified] = useState("");
  useEffect(() => {
    let mounted = true;
    const load = () => fetchSales().then(res => {
      if (mounted) {
        setSales(res.data || []);
        setLastModified(res.last_modified || "");
      }
    });
    load();
    const interval = setInterval(load, 30000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <h2 style={{ marginBottom: 0, fontWeight: 700 }}>Sales</h2>
        <span className="env-badge">Production</span>
        <span className="last-refresh">Last updated: {lastModified ? new Date(lastModified).toLocaleString() : "-"}</span>
      </div>
      <div className="section">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {sales[0] && Object.keys(sales[0]).map(k => <th key={k}>{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {sales.map((s, i) => (
              <tr key={i}>
                {Object.values(s).map((v, j) => <td key={j}>{v}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}