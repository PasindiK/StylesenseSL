import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Col, Row, Select, Spin, Statistic, Table, Typography, Progress, Tag, Upload } from "antd";
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

function businessDateText(value) {
  if (!value) return "Not available for this domain";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not available for this domain";
  return parsed.toLocaleString();
}

function trendPresentation(direction, adgriScore) {
  const trend = String(direction || "stable").toLowerCase();
  const score = Number(adgriScore || 0);

  if (trend === "deteriorating") {
    if (score >= 85) return { label: "Healthy but declining", color: "gold" };
    if (score >= 80) return { label: "Slight downward trend", color: "orange" };
    return { label: "Mild deterioration", color: "volcano" };
  }

  if (trend === "improving") {
    if (score >= 85) return { label: "Healthy and improving", color: "green" };
    return { label: "Improving trend", color: "green" };
  }

  return { label: "Stable trend", color: "blue" };
}

function staleBusinessDateDays(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.max(0, (Date.now() - parsed.getTime()) / (1000 * 60 * 60 * 24));
}

function lowScoreReason(item) {
  const score = Number(item?.adgri_score || item?.governance_score || 0);
  const freshness = Number(item?.freshness_stability?.risk ?? item?.freshness_risk ?? 0);
  const distribution = Number(item?.distribution_stability?.risk ?? item?.distribution_risk ?? 0);
  const volume = Number(item?.volume_stability?.risk ?? item?.volume_risk ?? 0);
  const staleDays = staleBusinessDateDays(item?.latest_business_data_date);
  const staleDateLikely = staleDays !== null && staleDays > 30;

  if (score >= 80) return "Healthy score";

  const highFreshness = freshness >= 0.7;
  const highDistribution = distribution >= 0.7;
  const elevatedFreshness = freshness >= 0.35;
  const elevatedDistribution = distribution >= 0.35;
  const elevatedVolume = volume >= 0.35;

  if (staleDateLikely && (elevatedFreshness || highFreshness) && (elevatedDistribution || highDistribution)) {
    return "Low due to combined freshness + distribution instability";
  }
  if (staleDateLikely && (elevatedFreshness || highFreshness)) {
    return "Low due to stale business dates";
  }
  if (highDistribution || elevatedDistribution) {
    return "Low due to abnormal value distribution";
  }
  if (elevatedFreshness) {
    return "Low due to freshness instability";
  }
  if (elevatedVolume) {
    return "Low due to volume instability";
  }

  return "Low due to combined risk signals";
}

export default function GovernanceControlPlane() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState({ domains: [] });
  const [selectedDomain, setSelectedDomain] = useState("");
  const [domainDetails, setDomainDetails] = useState(null);
  const [domainLoading, setDomainLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);

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

  const refreshGovernanceViews = async (domainName) => {
    const [summaryRes, detailRes] = await Promise.all([
      axios.get(`${API_BASE}/governance/summary`),
      axios.get(`${API_BASE}/governance/domain/${encodeURIComponent(domainName)}`),
    ]);
    const summaryPayload = summaryRes?.data || { domains: [] };
    setSummary(summaryPayload);
    setSelectedDomain(domainName);
    setDomainDetails(detailRes?.data || null);
  };

  const uploadAndRerun = () => {
    if (!selectedFile) {
      setError("Please choose a CSV test-case file.");
      return;
    }

    setUploadLoading(true);
    setError("");
    setUploadResult(null);

    const formData = new FormData();
    formData.append("upload_file", selectedFile);
    formData.append("session_id", "ui-governance-upload");
    formData.append("user_id", "admin");
    formData.append("auth_username", "Admin");
    formData.append("auth_password", "1234");

    axios
      .post(`${API_BASE}/admin/governance-test-cases/upload-and-rerun`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then(async (res) => {
        const payload = res.data || {};
        setUploadResult(payload);
        const mappedDomain = payload?.mapped_domain || selectedDomain || "sales_domain";
        await refreshGovernanceViews(mappedDomain);
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail;
        setError(detail || "Unable to upload test-case and rerun pipeline.");
      })
      .finally(() => {
        setUploadLoading(false);
      });
  };

  const restoreBaseline = () => {
    setRestoreLoading(true);
    setError("");
    setUploadResult(null);

    const restoreDomain = selectedDomain || uploadResult?.mapped_domain || "sales_domain";

    axios
      .post(`${API_BASE}/admin/governance-demo/restore-baseline-rerun`, {
        session_id: "ui-governance-demo-restore",
        user_id: "admin",
        selected_domain: restoreDomain,
        auth_username: "Admin",
        auth_password: "1234",
      })
      .then(async (res) => {
        const payload = res.data || {};
        await refreshGovernanceViews(payload?.selected_domain || restoreDomain);
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail;
        setError(detail || "Unable to restore baseline and rerun pipeline.");
      })
      .finally(() => {
        setRestoreLoading(false);
      });
  };

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
        low_score_reason: item?.low_score_reason_label || lowScoreReason(item),
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
        Primary ADGRI reliability assessment across domains using statistical stability modeling for volume, freshness, and distribution behaviour.
      </Paragraph>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col>
          <Tag color={statusText === "Live" ? "green" : "blue"}>{statusText}</Tag>
        </Col>
        <Col>
          <Tag color="geekblue">As of: {formatTime(summary?.as_of || summary?.generated_at)}</Tag>
        </Col>
        <Col>
          <Tag color="purple">Latest business data date: {businessDateText(domainDetails?.latest_business_data_date)}</Tag>
        </Col>
      </Row>

      <Card title="Scenario/Test Case" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="bottom">
          <Col xs={24} md={14}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Upload CSV Test Case</div>
            <Upload
              accept=".csv"
              maxCount={1}
              beforeUpload={(file) => {
                setSelectedFile(file);
                return false;
              }}
              onRemove={() => {
                setSelectedFile(null);
              }}
              fileList={selectedFile ? [selectedFile] : []}
            >
              <Button>Select CSV File</Button>
            </Upload>
          </Col>
          <Col xs={24} md={10}>
            <div style={{ marginBottom: 6, color: "#64748b" }}>
              Uploaded file replaces mapped active Silver dataset, then pipeline reruns and governance refreshes.
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button type="primary" loading={uploadLoading} onClick={uploadAndRerun}>Upload Test Case & Rerun</Button>
              <Button loading={restoreLoading} onClick={restoreBaseline}>Restore Baseline & Rerun Pipeline</Button>
            </div>
          </Col>
        </Row>
      </Card>

      {uploadResult ? (
        <Card title="Upload Result Summary" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={[12, 12]}>
            <Col xs={24} md={12}><strong>Uploaded File Name:</strong> {uploadResult?.uploaded_file_name || "-"}</Col>
            <Col xs={24} md={12}><strong>Mapped Domain:</strong> {uploadResult?.mapped_domain || "-"}</Col>
            <Col xs={24} md={12}><strong>Replaced in Silver:</strong> {uploadResult?.replaced_in_silver ? "Yes" : "No"}</Col>
            <Col xs={24} md={12}><strong>Pipeline Rerun:</strong> {uploadResult?.pipeline_rerun?.succeeded ? "Success" : "Fail"}</Col>
            <Col xs={24} md={24}><strong>Latest Governance Refresh Time:</strong> {formatTime(uploadResult?.governance_refresh?.latest_refresh_time)}</Col>
          </Row>
        </Card>
      ) : null}

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
                {
                  title: "Low-Score Explanation",
                  dataIndex: "low_score_reason",
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
                      <div>{businessDateText(domainDetails?.latest_business_data_date)}</div>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Confidence</div>
                      <Tag color={confidenceColor(domainDetails?.confidence?.level)}>
                        {String(domainDetails?.confidence?.level || "low").toUpperCase()} ({Number((domainDetails?.confidence?.score || 0) * 100).toFixed(1)}%)
                      </Tag>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Trend Direction</div>
                      <Tag color={trendPresentation(domainDetails?.trend_direction, domainDetails?.adgri_score || domainDetails?.governance_score).color}>
                        {trendPresentation(domainDetails?.trend_direction, domainDetails?.adgri_score || domainDetails?.governance_score).label}
                      </Tag>
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Trend Slope</div>
                      <div>{Number(domainDetails?.trend_slope || 0).toFixed(4)}</div>
                    </Col>
                  </Row>

                  <div style={{ marginTop: 12, marginBottom: 8 }}>
                    <div style={{ color: "#64748b", marginBottom: 10 }}>
                      Current score reflects present reliability; trend shows recent movement over time and does not by itself indicate domain failure.
                    </div>
                    <div style={{ fontWeight: 600 }}>Top Reason</div>
                    <div>{domainDetails?.top_reason || "-"}</div>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600 }}>Low-Score Explanation</div>
                    <div>{domainDetails?.low_score_reason_label || lowScoreReason(domainDetails)}</div>
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
