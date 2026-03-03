import React, { useEffect, useState } from "react";
import { Table, Typography, Tag, Spin } from "antd";
import axios from "axios";
import { API_BASE } from "../config";

const { Title } = Typography;

const DOMAINS = [
  { name: "Users", endpoint: "/users" },
  { name: "Products", endpoint: "/products" },
  { name: "Sales", endpoint: "/sales" },
  { name: "Shops", endpoint: "/shops" },
];

export default function Catalog() {
  const [schemas, setSchemas] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all(DOMAINS.map(d => axios.get(`${API_BASE}${d.endpoint}`))).then(responses => {
      setSchemas(responses.map((res, i) => ({
        key: DOMAINS[i].name,
        domain: DOMAINS[i].name,
        fields: res.data.data ? Object.keys(res.data.data[0] || {}) : Object.keys(res.data[0] || {}),
        schemaVersion: "v1", // Placeholder
        contractStatus: "Valid" // Placeholder
      })));
      setLoading(false);
    });
  }, []);

  const columns = [
    { title: "Domain", dataIndex: "domain" },
    { title: "Fields", dataIndex: "fields", render: f => f.join(", ") },
    { title: "Schema Version", dataIndex: "schemaVersion" },
    { title: "Contract Status", dataIndex: "contractStatus", render: s => <Tag color={s === "Valid" ? "green" : "red"}>{s}</Tag> }
  ];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <Title level={3} style={{ marginBottom: 0, fontWeight: 700 }}>Domain Catalog</Title>
        <span className="env-badge">Production</span>
      </div>
      <div className="section">
        {loading ? <Spin /> : <Table columns={columns} dataSource={schemas} pagination={false} />}
      </div>
    </div>
  );
}
