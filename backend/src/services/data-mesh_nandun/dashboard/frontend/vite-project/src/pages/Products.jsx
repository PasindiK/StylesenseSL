import { useEffect, useState } from "react";
import { fetchDataProducts } from "../api/api";

export default function Products() {
  const [products, setProducts] = useState([]);
  const [lastModified, setLastModified] = useState("");
  useEffect(() => {
    let mounted = true;
    const load = () => fetchDataProducts().then(res => {
      if (mounted) {
        // Sort domains alphabetically and show raw domain name for clarity
        const allProducts = (res.data || []).sort((a, b) => a.domain.localeCompare(b.domain));
        setProducts(allProducts);
        setLastModified(new Date().toLocaleString());
      }
    });
    load();
    const interval = setInterval(load, 30000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <h2 style={{ marginBottom: 0, fontWeight: 700 }}>Data Products</h2>
        <span className="env-badge">Production</span>
        <span className="last-refresh">Last updated: {lastModified}</span>
      </div>
      <div className="section">
        {products.length === 0 ? (
          <div>No data products found.</div>
        ) : (
          products.map((prod, idx) => (
            <div key={idx} style={{ marginBottom: 32, border: "1px solid #eee", borderRadius: 8, padding: 16 }}>
              <h3 style={{ margin: 0, fontWeight: 600 }}>{prod.domain}</h3>
              <div><b>Raw Domain Name:</b> {prod.domain}</div>
              <div>Rows: {prod.row_count}</div>
              <div>Last Modified: {prod.last_modified ? new Date(prod.last_modified).toLocaleString() : "-"}</div>
              <div>Columns: {prod.columns.join(", ")}</div>
              <div>Sample Data:</div>
              <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 8 }}>
                <thead>
                  <tr>{prod.sample[0] && Object.keys(prod.sample[0]).map(k => <th key={k}>{k}</th>)}</tr>
                </thead>
                <tbody>
                  {prod.sample.map((row, i) => (
                    <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{v}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
      </div>
    </div>
  );
}