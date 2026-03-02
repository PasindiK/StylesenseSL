import { useEffect, useState } from "react";
import { fetchUsers } from "../api/api";

export default function Users() {
  const [users, setUsers] = useState([]);
  const [lastModified, setLastModified] = useState("");
  useEffect(() => {
    let mounted = true;
    const load = () => fetchUsers().then(res => {
      if (mounted) {
        setUsers(res.data || []);
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
        <h2 style={{ marginBottom: 0, fontWeight: 700 }}>Users</h2>
        <span className="env-badge">Production</span>
        <span className="last-refresh">Last updated: {lastModified ? new Date(lastModified).toLocaleString() : "-"}</span>
      </div>
      <div className="section">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>{users[0] && Object.keys(users[0]).map(k => <th key={k}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={i}>{Object.values(u).map((v, j) => <td key={j}>{v}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}