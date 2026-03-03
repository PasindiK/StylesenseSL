import React, { useEffect, useState } from "react";
import axios from "axios";
import { API_BASE } from "../config";

const STATUS_COLORS = {
  1: "#e74c3c", // anomaly
  0: "#2ecc71", // healthy
};

function AnomalyBadge({ flag }) {
  const color = STATUS_COLORS[flag] || "#bdc3c7";
  const text = flag === 1 ? "Anomaly" : "Healthy";
  return (
    <span style={{
      background: color,
      color: "#fff",
      borderRadius: "6px",
      padding: "4px 16px",
      fontWeight: "bold",
      fontSize: "1em",
      boxShadow: "0 1px 4px #e0e7ef33",
      letterSpacing: 1,
      display: "inline-block"
    }}>
      {text}
    </span>
  );
}

export default function DomainHealthDashboard() {
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios
      .get(`${API_BASE}/domain-health/anomalies`)
      .then((res) => {
        setDomains(res.data.domains || []);
        setLoading(false);
      })
      .catch((err) => {
        setError("Failed to fetch anomaly data");
        setLoading(false);
      });
  }, []);

  if (loading) return <div style={{ fontSize: 18, color: '#3b82f6', fontWeight: 600, margin: '2rem 0' }}>Loading domain health...</div>;
  if (error) return <div style={{ color: "#e74c3c", fontWeight: 600, fontSize: 16 }}>{error}</div>;

  return (
    <div>
      <h2 style={{ fontWeight: 700, fontSize: 32, marginBottom: 32, color: '#222', letterSpacing: 1 }}>Domain Health & Anomaly Dashboard</h2>
      <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, background: "#fafbfc", borderRadius: 12, boxShadow: "0 1px 8px #e0e7ef22", overflow: "hidden" }}>
        <thead>
          <tr style={{ background: "#f4f8fc", height: 56 }}>
            <th style={{ textAlign: "left", padding: "12px 18px", fontWeight: 600, fontSize: 16, color: '#3b82f6' }}>Domain</th>
            <th style={{ textAlign: "right", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Row Count</th>
            <th style={{ textAlign: "right", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Null %</th>
            <th style={{ textAlign: "right", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Duplicate %</th>
            <th style={{ textAlign: "right", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Freshness (hrs)</th>
            <th style={{ textAlign: "center", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Status</th>
            <th style={{ textAlign: "center", padding: "12px 18px", fontWeight: 600, fontSize: 16 }}>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {domains.map((d, i) => (
            <tr key={d.domain_name} style={{ background: i % 2 === 0 ? '#fff' : '#f6f8fa', height: 48 }}>
              <td style={{ padding: "10px 18px", fontWeight: 600, color: '#222', fontSize: 15 }}>{d.domain_name}</td>
              <td style={{ textAlign: "right", padding: "10px 18px", fontSize: 15 }}>{d.row_count}</td>
              <td style={{ textAlign: "right", padding: "10px 18px", fontSize: 15 }}>{d.null_percentage}</td>
              <td style={{ textAlign: "right", padding: "10px 18px", fontSize: 15 }}>{d.duplicate_percentage}</td>
              <td style={{ textAlign: "right", padding: "10px 18px", fontSize: 15 }}>{d.freshness_hours}</td>
              <td style={{ textAlign: "center", padding: "10px 18px" }}><AnomalyBadge flag={d.anomaly_flag} /></td>
              <td style={{ textAlign: "center", padding: "10px 18px", fontFamily: 'monospace', fontSize: 15 }}>{d.timestamp}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* TODO: Add time-series chart for each domain's anomaly history */}
    </div>
  );
}
