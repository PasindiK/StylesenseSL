import React, { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Row, Spin, Statistic, Table, Tag, Typography } from "antd";
import axios from "axios";
import { ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip, ScatterChart, Scatter, ZAxis } from "recharts";
import { API_BASE } from "../config";

const { Title, Paragraph } = Typography;

function priorityColor(value) {
  if (value === "High") return "red";
  if (value === "Medium") return "orange";
  return "blue";
}

function confidenceColor(level) {
  const value = String(level || "low").toLowerCase();
  if (value === "high") return "green";
  if (value === "medium") return "orange";
  return "red";
}

function chartTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload || {};
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px" }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{point.domain_name || "-"}</div>
      <div>Reliability (ADGRI): {Number(point.reliability || 0).toFixed(2)}</div>
      <div>Governance Impact: {Number(point.impact || 0).toFixed(2)}</div>
      <div>Criticality: {Number(point.criticality || 0).toFixed(2)}</div>
    </div>
  );
}

export default function GovernancePrioritization() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState(null);

  useEffect(() => {
    setLoading(true);
    axios
      .get(`${API_BASE}/governance/priorities`)
      .then((res) => setPayload(res.data || null))
      .catch(() => setError("Unable to load governance prioritization data."))
      .finally(() => setLoading(false));
  }, []);

  const ranked = useMemo(() => payload?.ranked_priorities || [], [payload]);
  const highest = payload?.highest_priority_domain || null;
  const avgImpact = Number(payload?.average_impact_score || 0);
  const highCount = Number(payload?.high_priority_domains_count || 0);
  const mediumCount = Number(payload?.medium_priority_domains_count || 0);
  const lowCount = Number(payload?.low_priority_domains_count || 0);
  const actionStrategy = payload?.action_strategy || "Routine";
  const actionSummary = payload?.action_summary || "No urgent governance actions required.";
  const noActionMessage = mediumCount > 0
    ? "No urgent governance actions are required. Medium-priority domains should be monitored."
    : "No urgent governance actions are required. Continue routine observation of low-priority domains.";

  const chartData = useMemo(
    () =>
      ranked.map((item) => ({
        domain_name: item.domain_name,
        reliability: Number(item.adgri_score || 0),
        impact: Number(item.governance_impact_score || 0),
        criticality: Number(item.criticality_score || 0),
      })),
    [ranked]
  );

  const actions = useMemo(() => {
    const high = ranked.filter((item) => item.priority_level === "High");
    if (high.length) return high.slice(0, 5);
    const medium = ranked.filter((item) => item.priority_level === "Medium");
    if (medium.length) return medium.slice(0, 5);
    return [];
  }, [ranked]);

  return (
    <div style={{ padding: 16, maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <Title level={2} style={{ marginBottom: 8 }}>Governance Prioritization</Title>
      <Paragraph style={{ color: "#64748b", marginBottom: 16 }}>
        Built on ADGRI to prioritize governance attention across domains. This is a secondary decision-support extension to the Governance Control Plane.
      </Paragraph>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}

      {loading ? (
        <Spin />
      ) : (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} md={8}>
              <Card>
                <Statistic title="Highest Priority Domain" value={highest?.domain_name || "-"} />
                {highest ? <Tag color={priorityColor(highest.priority_level)} style={{ marginTop: 8 }}>{highest.priority_level}</Tag> : null}
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card>
                <Statistic title="Average Impact Score" value={avgImpact} precision={2} />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card>
                <Statistic title="High Priority Domains" value={highCount} />
                <div style={{ color: "#64748b", marginTop: 8 }}>
                  Medium: {mediumCount} · Low: {lowCount}
                </div>
              </Card>
            </Col>
          </Row>

          <Card title="Ranked Governance Priorities" style={{ marginBottom: 16 }}>
            <Table
              rowKey="domain_name"
              pagination={false}
              dataSource={ranked}
              columns={[
                { title: "Domain", dataIndex: "domain_name" },
                {
                  title: "ADGRI (Reliability)",
                  dataIndex: "adgri_score",
                  render: (value) => Number(value || 0).toFixed(2),
                },
                {
                  title: "Criticality Score",
                  dataIndex: "criticality_score",
                  render: (value) => Number(value || 0).toFixed(2),
                },
                {
                  title: "Governance Impact Score",
                  dataIndex: "governance_impact_score",
                  render: (value) => Number(value || 0).toFixed(2),
                },
                {
                  title: "Priority",
                  dataIndex: "priority_level",
                  render: (value) => <Tag color={priorityColor(value)}>{String(value || "Low")}</Tag>,
                },
                {
                  title: "Confidence",
                  dataIndex: "confidence_level",
                  render: (value) => <Tag color={confidenceColor(value)}>{String(value || "Low")}</Tag>,
                },
                {
                  title: "Top Governance Concern",
                  dataIndex: "top_governance_concern",
                  render: (value) => value || "-",
                },
                {
                  title: "Recommended Action",
                  dataIndex: "recommended_action",
                  render: (value) => value || "-",
                },
              ]}
            />
          </Card>

          <Card title="Impact vs Reliability View" style={{ marginBottom: 16 }}>
            <ResponsiveContainer width="100%" height={320}>
              <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                <CartesianGrid />
                <XAxis
                  type="number"
                  dataKey="reliability"
                  name="Reliability / ADGRI"
                  domain={[0, 100]}
                  label={{ value: "Reliability / ADGRI", position: "insideBottom", offset: -8 }}
                />
                <YAxis
                  type="number"
                  dataKey="impact"
                  name="Governance Impact"
                  domain={[0, 100]}
                  label={{ value: "Governance Impact", angle: -90, position: "insideLeft" }}
                />
                <ZAxis type="number" dataKey="criticality" range={[60, 280]} name="Criticality" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} content={chartTooltip} />
                <Scatter data={chartData} fill="#2563eb" />
              </ScatterChart>
            </ResponsiveContainer>
            <Paragraph style={{ marginTop: 10, marginBottom: 0, color: "#64748b" }}>
              Domains in the upper-left or upper-middle region need more governance attention.
            </Paragraph>
          </Card>

          <Card title="Recommended Governance Actions" style={{ marginBottom: 16 }}>
            <Paragraph style={{ marginBottom: 12, color: "#334155" }}>
              <strong>{actionStrategy} Strategy:</strong> {actionSummary}
            </Paragraph>
            {actions.length ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {actions.map((item) => (
                  <li key={item.domain_name} style={{ marginBottom: 10 }}>
                    <strong>{item.domain_name}</strong>: {item.recommended_action}
                  </li>
                ))}
              </ul>
            ) : (
              <div>{noActionMessage}</div>
            )}
          </Card>

          <Card title="Prioritization Explanations">
            {ranked.map((item) => (
              <div key={`${item.domain_name}-explain`} style={{ marginBottom: 10 }}>
                <strong>{item.domain_name}</strong>: {item.explanation}
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}
