import React, { useEffect, useState } from "react";
import { Card, Row, Col, Spin, Typography } from "antd";
import axios from "axios";

const { Title } = Typography;
const BASE = "http://localhost:8000";

function PipelineStatusCard({ name, status, lastRun, duration, error }) {
  let color = '#888';
  if (status === 'success') color = '#22c55e';
  else if (status === 'failed') color = '#ef4444';
  else if (status === 'delayed') color = '#f59e42';
  return (
    <Card style={{ width: 260, margin: 8, border: `1.5px solid ${color}` }}>
      <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 6 }}>{name}</div>
      <div style={{ fontWeight: 600, color, fontSize: 16, marginBottom: 4 }}>Status: {status}</div>
      <div style={{ fontSize: 14, marginBottom: 2 }}>Last Run: {lastRun ? new Date(lastRun).toLocaleString() : '-'}</div>
      <div style={{ fontSize: 14, marginBottom: 2 }}>Duration: {duration ? duration + 's' : '-'}</div>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginTop: 4 }}>Error: {error}</div>}
    </Card>
  );
}

export default function PipelineMonitor() {
  const [pipelineStatus, setPipelineStatus] = useState(null);

  useEffect(() => {
    axios.get(`${BASE}/pipeline-status`).then(res => setPipelineStatus(res.data));
    const interval = setInterval(() => {
      axios.get(`${BASE}/pipeline-status`).then(res => setPipelineStatus(res.data));
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto' }}>
      <Title level={2} style={{ fontWeight: 700, marginBottom: 32 }}>Pipeline & Job Monitor</Title>
      <div style={{ marginBottom: 32 }}>
        <Title level={4} style={{ marginBottom: 12 }}>Current Pipeline/Job Status</Title>
        {pipelineStatus ? (
          <Row gutter={[16, 16]} style={{ flexWrap: 'wrap' }}>
            {Object.entries(pipelineStatus).map(([name, info]) => (
              <Col key={name} xs={24} sm={12} md={8} lg={8} xl={8}>
                <PipelineStatusCard
                  name={name}
                  status={info.status}
                  lastRun={info.last_run}
                  duration={info.duration}
                  error={info.error}
                />
              </Col>
            ))}
          </Row>
        ) : <Spin />}
      </div>
    </div>
  );
}
