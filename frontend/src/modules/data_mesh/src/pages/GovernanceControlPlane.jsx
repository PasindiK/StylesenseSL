import React, { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Row, Select, Spin, Statistic, Table, Typography, Progress, Tag } from "antd";
import axios from "axios";
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from "recharts";
import { API_BASE } from "../config";

const { Title, Paragraph } = Typography;
const { Option } = Select;

function formatTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function relativeTime(value) {
  if (!value) return "unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  const mins = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 60000));
  if (mins < 1) return "Live";
  if (mins < 60) return `Updated ${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
}

export default function GovernanceControlPlane() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState({ domains: [] });
  const [selectedDomain, setSelectedDomain] = useState("");
  const [domainDetails, setDomainDetails] = useState(null);
  const [domainLoading, setDomainLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    axios
      .get(`${API_BASE}/governance/summary`)
      .then((res) => {
        const payload = res.data || { domains: [] };
        setSummary(payload);
        if (payload.domains?.length) {
          setSelectedDomain((prev) => prev || payload.domains[0].domain_name);
        }
      })
      .catch(() => {
        setError("Unable to load Governance Control Plane summary.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedDomain) return;
    setDomainLoading(true);
    axios
      .get(`${API_BASE}/governance/domain/${encodeURIComponent(selectedDomain)}`)
      .then((res) => {
        setDomainDetails(res.data || null);
      })
      .catch(() => {
        setDomainDetails(null);
      })
      .finally(() => {
        setDomainLoading(false);
      });
  }, [selectedDomain]);

  const tableRows = useMemo(
    () =>
      (summary.domains || []).map((item) => ({
        key: item.domain_name,
        domain_name: item.domain_name,
        adgri_score: item.adgri_score || item.governance_score,
        confidence_level: item?.confidence?.level || "low",
        volume_risk: item?.volume_stability?.risk,
        freshness_risk: item?.freshness_stability?.risk,
        distribution_risk: item?.distribution_stability?.risk,
        top_reason: item?.top_reason,
      })),
    [summary]
  );

  const statusText = relativeTime(domainDetails?.latest_governance_evaluation_time || summary?.as_of);

  const confidenceColor = (level) => {
    if (level === "high") return "green";
    if (level === "medium") return "orange";
    return "red";
  };

  return (
    <div style={{ padding: 16, maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <Title level={2} style={{ marginBottom: 8 }}>Governance Control Plane</Title>
      <Paragraph style={{ color: "#64748b", marginBottom: 16 }}>
        Adaptive computational governance across domains using statistical stability modeling for volume, freshness, and distribution behaviour.
      </Paragraph>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col>
          <Tag color={statusText === "Live" ? "green" : "blue"}>{statusText}</Tag>
        </Col>
        <Col>
          <Tag color="geekblue">As of: {formatTime(summary?.as_of || summary?.generated_at)}</Tag>
        </Col>
        {domainDetails?.latest_business_data_date ? (
          <Col>
            <Tag color="purple">Latest business data date: {formatTime(domainDetails.latest_business_data_date)}</Tag>
          </Col>
        ) : null}
      </Row>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}

      {loading ? (
        <Spin />
      ) : (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={8}>
              <Card>
                <Statistic title="Domains Evaluated" value={(summary.domains || []).length} />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card>
                <Statistic
                  title="Average ADGRI"
                  value={
                    (summary.domains || []).length
                      ? (summary.domains || []).reduce((acc, item) => acc + ((item.adgri_score || item.governance_score) || 0), 0) / (summary.domains || []).length
                      : 0
                  }
                  precision={2}
                />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card>
                <Statistic
                  title="Lowest Domain ADGRI"
                  value={
                    (summary.domains || []).length
                      ? Math.min(...(summary.domains || []).map((item) => (item.adgri_score || item.governance_score || 0)))
                      : 0
                  }
                  precision={2}
                />
              </Card>
            </Col>
          </Row>

          <Card title="ADGRI Reliability by Domain" style={{ marginBottom: 16 }}>
            <Table
              pagination={false}
              dataSource={tableRows}
              columns={[
                { title: "Domain", dataIndex: "domain_name" },
                {
                  title: "ADGRI",
                  dataIndex: "adgri_score",
                  render: (value) => (
                    <div style={{ minWidth: 180 }}>
                      <div style={{ marginBottom: 4 }}>{Number(value || 0).toFixed(2)}</div>
                      <Progress percent={Math.round(value || 0)} size="small" status="active" />
                    </div>
                  ),
                },
                {
                  title: "Confidence",
                  dataIndex: "confidence_level",
                  render: (value) => <Tag color={confidenceColor(value)}>{String(value || "low").toUpperCase()}</Tag>,
                },
                {
                  title: "Volume Stability Risk",
                  dataIndex: "volume_risk",
                  render: (value) => Number((value || 0) * 100).toFixed(1) + "%",
                },
                {
                  title: "Freshness Deviation Risk",
                  dataIndex: "freshness_risk",
                  render: (value) => Number((value || 0) * 100).toFixed(1) + "%",
                },
                {
                  title: "Distribution Stability Risk",
                  dataIndex: "distribution_risk",
                  render: (value) => Number((value || 0) * 100).toFixed(1) + "%",
                },
                {
                  title: "Top Reason",
                  dataIndex: "top_reason",
                  render: (value) => value || "-",
                },
              ]}
            />
          </Card>

          <Card title="Domain Governance Detail">
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} md={10}>
                <div style={{ marginBottom: 8, fontWeight: 600 }}>Select Domain</div>
                <Select value={selectedDomain} style={{ width: "100%" }} onChange={setSelectedDomain}>
                  {(summary.domains || []).map((item) => (
                    <Option key={item.domain_name} value={item.domain_name}>
                      {item.domain_name}
                    </Option>
                  ))}
                </Select>
              </Col>
            </Row>

            {domainLoading ? (
              <Spin />
            ) : domainDetails ? (
              <>
                <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                  <Col xs={24} md={6}><Card><Statistic title="ADGRI" value={domainDetails.adgri_score || domainDetails.governance_score || 0} precision={2} /></Card></Col>
                  <Col xs={24} md={6}><Card><Statistic title="Volume Instability" value={(domainDetails?.volume_stability?.risk || 0) * 100} suffix="%" precision={2} /></Card></Col>
                  <Col xs={24} md={6}><Card><Statistic title="Freshness Instability" value={(domainDetails?.freshness_stability?.risk || 0) * 100} suffix="%" precision={2} /></Card></Col>
                  <Col xs={24} md={6}><Card><Statistic title="Distribution Instability" value={(domainDetails?.distribution_stability?.risk || 0) * 100} suffix="%" precision={2} /></Card></Col>
                </Row>

                <Card title="Explainability" style={{ marginBottom: 16 }}>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Latest Evaluation Time</div>
                      <div>{formatTime(domainDetails?.latest_governance_evaluation_time)}</div>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Latest Domain Refresh Time</div>
                      <div>{formatTime(domainDetails?.latest_domain_refresh_time)}</div>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Latest Business Data Date</div>
                      <div>{formatTime(domainDetails?.latest_business_data_date)}</div>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Confidence</div>
                      <Tag color={confidenceColor(domainDetails?.confidence?.level)}>
                        {String(domainDetails?.confidence?.level || "low").toUpperCase()} ({Number((domainDetails?.confidence?.score || 0) * 100).toFixed(1)}%)
                      </Tag>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Trend Direction</div>
                      <Tag color={domainDetails?.trend_direction === "improving" ? "green" : domainDetails?.trend_direction === "deteriorating" ? "red" : "blue"}>
                        {String(domainDetails?.trend_direction || "stable").toUpperCase()}
                      </Tag>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Trend Slope</div>
                      <div>{Number(domainDetails?.trend_slope || 0).toFixed(4)}</div>
                    </Col>
                  </Row>

                  <div style={{ marginTop: 12, marginBottom: 8 }}>
                    <div style={{ fontWeight: 600 }}>Top Reason</div>
                    <div>{domainDetails?.top_reason || "-"}</div>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600 }}>Explanation</div>
                    <div>{domainDetails?.explanation || "-"}</div>
                  </div>

                  <Table
                    size="small"
                    pagination={false}
                    dataSource={[
                      {
                        key: "contrib",
                        volume: domainDetails?.contribution_breakdown?.volume?.score_impact,
                        freshness: domainDetails?.contribution_breakdown?.freshness?.score_impact,
                        distribution: domainDetails?.contribution_breakdown?.distribution?.score_impact,
                      },
                    ]}
                    columns={[
                      {
                        title: "Volume Contribution",
                        dataIndex: "volume",
                        render: (value) => `${Number(value || 0).toFixed(2)} score points`,
                      },
                      {
                        title: "Freshness Contribution",
                        dataIndex: "freshness",
                        render: (value) => `${Number(value || 0).toFixed(2)} score points`,
                      },
                      {
                        title: "Distribution Contribution",
                        dataIndex: "distribution",
                        render: (value) => `${Number(value || 0).toFixed(2)} score points`,
                      },
                    ]}
                  />
                </Card>

                <Card title={`${domainDetails?.trend_label || "Governance Evaluation Trend"} (Latest 7 points)`}>
                  {domainDetails.risk_trend?.length ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={domainDetails.risk_trend}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tickFormatter={(value) => formatTime(value)} />
                        <YAxis domain={[0, 100]} />
                        <Tooltip labelFormatter={(label) => formatTime(label)} />
                        <Line type="monotone" dataKey="governance_score" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div>No trend points available.</div>
                  )}
                </Card>
              </>
            ) : (
              <div>No governance details available.</div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
