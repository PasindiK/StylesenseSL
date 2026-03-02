import React, { useEffect, useState } from "react";
import { Table, Tag, Typography, Spin } from "antd";
import axios from "axios";

const { Title } = Typography;
const BASE = "http://localhost:8000";

export default function Health() {
  const [health, setHealth] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${BASE}/health`).then(res => {
      const data = Object.entries(res.data).map(([domain, info]) => ({
        key: domain,
        domain,
        ...info
      }));
      setHealth(data);
      setLoading(false);
    });
  }, []);

  const columns = [
    { title: "Domain", dataIndex: "domain" },
    { title: "Row Count", dataIndex: "row_count" },
    { title: "Null Counts", dataIndex: "null_counts", render: nc => nc ? Object.entries(nc).map(([k, v]) => `${k}: ${v}`).join(", ") : "-" },
    { title: "Last Modified", dataIndex: "last_modified", render: lm => lm ? new Date(lm).toLocaleString() : "-" },
    { title: "Freshness", dataIndex: "last_modified", render: lm => {
      if (!lm) return <Tag color="red">Stale</Tag>;
      const age = (Date.now() - new Date(lm).getTime()) / 1000 / 60 / 60;
      return <Tag color={age < 24 ? "green" : age < 72 ? "orange" : "red"}>{age < 24 ? "Fresh" : age < 72 ? "Aging" : "Stale"}</Tag>;
    }}
  ];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <Title level={3} style={{ marginBottom: 0, fontWeight: 700 }}>Domain Health</Title>
        <span className="env-badge">Production</span>
      </div>
      <div className="section">
        {loading ? <Spin /> : <Table columns={columns} dataSource={health} pagination={false} />}
      </div>
    </div>
  );
}
