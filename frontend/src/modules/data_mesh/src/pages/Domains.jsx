import React, { useEffect, useState } from "react";
import { Table, Typography, Tag, Button, Spin } from "antd";
import axios from "axios";
import { API_BASE } from "../config";

const { Title } = Typography;

export default function Domains() {
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch metadata from backend (to be implemented)
    axios.get(`${API_BASE}/domains/metadata`).then(res => {
      setDomains(res.data || []);
      setLoading(false);
    });
  }, []);

  const columns = [
    { title: "Domain", dataIndex: "domain", render: v => <span style={{ whiteSpace: "normal", wordBreak: "break-word" }}>{v}</span> },
    { title: "Owner", dataIndex: "owner", render: v => <span style={{ whiteSpace: "normal", wordBreak: "break-word" }}>{v}</span> },
    { title: "Contact", dataIndex: "contact", render: v => <span style={{ whiteSpace: "normal", wordBreak: "break-word" }}>{v}</span> },
    { title: "Schema Version", dataIndex: "schema_version" },
    { title: "Contract Status", dataIndex: "contract_status", render: s => <Tag color={s === "Valid" ? "green" : s === "Unknown" ? "red" : "orange"}>{s}</Tag> },
    { title: "Last Modified", dataIndex: "last_modified", render: lm => lm ? new Date(lm).toLocaleString() : "-" },
    { title: "SLA", dataIndex: "sla", render: v => <span style={{ whiteSpace: "normal", wordBreak: "break-word" }}>{v}</span> },
    { title: "Health", dataIndex: "health", render: h => <Tag color={h === "Healthy" ? "green" : h === "Warning" ? "orange" : "red"}>{h}</Tag> },
    { title: "Contract", dataIndex: "contract_file", render: file => file ? (
      <Button href={`${API_BASE}/contracts/${file.split('/').pop()}`} target="_blank">View Contract</Button>
    ) : <span style={{ color: '#aaa' }}>No Contract</span> },
  ];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <Title level={3} style={{ marginBottom: 0, fontWeight: 700 }}>Domain Catalog & Ownership</Title>
        <span className="env-badge">Production</span>
      </div>
      <div className="section">
        {loading ? <Spin /> : <Table columns={columns} dataSource={domains} pagination={false} scroll={{ x: "max-content" }} />}
      </div>
    </div>
  );
}
