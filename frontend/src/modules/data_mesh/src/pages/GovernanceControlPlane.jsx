import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Col, Row, Select, Spin, Statistic, Table, Typography, Tag, Upload } from "antd";
import axios from "axios";
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from "recharts";
import { API_BASE } from "../config";

const { Title, Paragraph, Text } = Typography;
const { Option } = Select;

/** Business-priority labels for panel narrative (same ADGRI equation; importance differs by domain). */
const DOMAIN_BUSINESS_PRIORITIES = {
  sales_domain: { freshness: "High", volume: "Medium", distribution: "Medium" },
  users_domain: { freshness: "Low", volume: "Medium", distribution: "High" },
  interaction_domain: { freshness: "Medium", volume: "Medium", distribution: "High" },
  product_domain: { freshness: "Medium", volume: "Medium", distribution: "High" },
  shop_domain: { freshness: "Medium", volume: "Medium", distribution: "Medium" },
  engagement_domain: { freshness: "Medium", volume: "Medium", distribution: "High" },
  user_preferences_domain: { freshness: "Low", volume: "Medium", distribution: "High" },
};

const DEFAULT_BUSINESS_PRIORITY = { freshness: "Medium", volume: "Medium", distribution: "Medium" };

function getBusinessPriorities(domainName) {
  const key = String(domainName || "").trim();
  return DOMAIN_BUSINESS_PRIORITIES[key] || DEFAULT_BUSINESS_PRIORITY;
}

function priorityTierColor(tier) {
  const t = String(tier || "").toLowerCase();
  if (t === "high") return "red";
  if (t === "medium") return "gold";
  return "blue";
}

function formatEffectiveWeights(weights) {
  if (!weights || typeof weights !== "object") return null;
  const f = Number(weights.freshness);
  const v = Number(weights.volume);
  const d = Number(weights.distribution);
  if ([f, v, d].some((x) => Number.isNaN(x))) return null;
  const pct = (x) => `${Math.round(x * 100)}%`;
  return `This run: Fresh ${pct(f)} · Vol ${pct(v)} · Dist ${pct(d)}`;
}

function inferMainRiskDriver(item) {
  const breakdown = item?.contribution_breakdown;
  if (breakdown && typeof breakdown === "object") {
    const scores = ["volume", "freshness", "distribution"].map((k) => ({
      key: k,
      impact: Number((breakdown[k] || {}).score_impact || 0),
    }));
    const best = scores.reduce((a, b) => (b.impact > a.impact ? b : a), scores[0]);
    if (best && best.impact > 0) {
      return best.key.charAt(0).toUpperCase() + best.key.slice(1);
    }
  }
  const tr = String(item?.top_reason || "").toLowerCase();
  if (tr.includes("volume")) return "Volume";
  if (tr.includes("freshness")) return "Freshness";
  if (tr.includes("distribution")) return "Distribution";
  return "Mixed";
}

function mainDriverBadgeColor(driver) {
  const d = String(driver || "").toLowerCase();
  if (d === "freshness") return "volcano";
  if (d === "volume") return "geekblue";
  if (d === "distribution") return "purple";
  return "default";
}

function recommendedTableAction(adgri, mainDriver) {
  const score = Number(adgri || 0);
  if (score >= 85) return "Routine monitoring";
  const d = String(mainDriver || "").toLowerCase();
  if (d === "freshness") return "Refresh data pipeline";
  if (d === "volume") return "Check missing/duplicate ingestion";
  if (d === "distribution") return "Inspect anomaly/drift";
  return "Inspect anomaly/drift";
}

function governanceHealthStatus(adgri) {
  const score = Number(adgri || 0);
  if (score >= 85) return "Healthy";
  if (score >= 65) return "Monitor";
  return "Action needed";
}

function healthStatusColor(status) {
  if (status === "Healthy") return "success";
  if (status === "Monitor") return "warning";
  return "error";
}

function actionCardStyleByStatus(status) {
  if (status === "Healthy") {
    return { border: "1px solid #16a34a", background: "#f0fdf4" };
  }
  if (status === "Monitor") {
    return { border: "1px solid #f59e0b", background: "#fffbeb" };
  }
  return { border: "1px solid #dc2626", background: "#fef2f2" };
}

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
  const [successMessage, setSuccessMessage] = useState("");
  const [summary, setSummary] = useState({ domains: [] });
  const [selectedDomain, setSelectedDomain] = useState("");
  const [domainDetails, setDomainDetails] = useState(null);
  const [domainLoading, setDomainLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [scenarioComparison, setScenarioComparison] = useState(null);
  const [liveTrendOverride, setLiveTrendOverride] = useState([]);
  const [demoAffectedDomain, setDemoAffectedDomain] = useState("");
  const [showAffectedOnly, setShowAffectedOnly] = useState(false);
  const selectedDomainRef = useRef("");

  useEffect(() => {
    selectedDomainRef.current = selectedDomain;
  }, [selectedDomain]);

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
    Promise.all([
      axios.get(`${API_BASE}/governance/domain/${encodeURIComponent(selectedDomain)}`),
      axios.get(`${API_BASE}/governance/test-case-comparison/${encodeURIComponent(selectedDomain)}`),
    ])
      .then(([detailRes, comparisonRes]) => {
        setDomainDetails(detailRes?.data || null);
        setScenarioComparison(comparisonRes?.data?.latest || null);
      })
      .catch(() => {
        setDomainDetails(null);
      })
      .finally(() => {
        setDomainLoading(false);
      });
  }, [selectedDomain]);

  const refreshGovernanceViews = useCallback(async (domainName) => {
    const [summaryRes, detailRes, comparisonRes] = await Promise.all([
      axios.get(`${API_BASE}/governance/summary`),
      axios.get(`${API_BASE}/governance/domain/${encodeURIComponent(domainName)}`),
      axios.get(`${API_BASE}/governance/test-case-comparison/${encodeURIComponent(domainName)}`),
    ]);
    const summaryPayload = summaryRes?.data || { domains: [] };
    setSummary(summaryPayload);
    setSelectedDomain(domainName);
    setDomainDetails(detailRes?.data || null);
    setScenarioComparison(comparisonRes?.data?.latest || null);
  }, []);

  useEffect(() => {
    const onPipelineGovernanceRefresh = () => {
      const fallback = summary.domains?.[0]?.domain_name || "";
      const target = selectedDomainRef.current || fallback;
      if (target) {
        refreshGovernanceViews(target).catch(() => {});
        return;
      }
      axios
        .get(`${API_BASE}/governance/summary`)
        .then((res) => {
          const payload = res.data || { domains: [] };
          setSummary(payload);
          const first = payload.domains?.[0]?.domain_name;
          if (first) {
            selectedDomainRef.current = first;
            setSelectedDomain(first);
          }
        })
        .catch(() => {});
    };
    window.addEventListener("dm-data-mesh-governance-refresh", onPipelineGovernanceRefresh);
    return () => window.removeEventListener("dm-data-mesh-governance-refresh", onPipelineGovernanceRefresh);
  }, [summary.domains, refreshGovernanceViews]);

  const uploadAndRerun = () => {
    if (!selectedFile) {
      setError("Please choose a CSV test-case file.");
      return;
    }

    setUploadLoading(true);
    setError("");
    setSuccessMessage("");
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
        setScenarioComparison(payload?.scenario_test_case_comparison || null);
        setLiveTrendOverride(payload?.live_governance_trend?.risk_trend || []);
        const mappedDomain = payload?.affected_domain || payload?.mapped_domain || selectedDomain || "sales_domain";
        setDemoAffectedDomain(mappedDomain);
        setShowAffectedOnly(true);
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
    setSuccessMessage("");

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
        setScenarioComparison(payload?.scenario_test_case_comparison || null);
        setLiveTrendOverride([]);
        setDemoAffectedDomain("");
        setShowAffectedOnly(false);
        await refreshGovernanceViews(payload?.selected_domain || restoreDomain);
        setSuccessMessage("Baseline restored and governance recomputed.");
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
      (summary.domains || []).map((item) => {
        const adgri = item.adgri_score || item.governance_score;
        const mainDriver = inferMainRiskDriver(item);
        return {
          key: item.domain_name,
          domain_name: item.domain_name,
          adgri_score: adgri,
          raw_item: item,
          confidence_level: item?.confidence?.level || "low",
          confidence_score: item?.confidence?.score,
          volume_risk: item?.volume_stability?.risk,
          freshness_risk: item?.freshness_stability?.risk,
          distribution_risk: item?.distribution_stability?.risk,
          weights: item?.weights,
          main_driver: mainDriver,
          recommended_action: recommendedTableAction(adgri, mainDriver),
          health_status: governanceHealthStatus(adgri),
          business_priorities: getBusinessPriorities(item.domain_name),
          is_demo_focus: demoAffectedDomain && item.domain_name === demoAffectedDomain,
        };
      }),
    [summary, demoAffectedDomain]
  );
  const visibleTableRows = useMemo(() => {
    if (!showAffectedOnly || !demoAffectedDomain) return tableRows;
    return tableRows.filter((row) => row.domain_name === demoAffectedDomain);
  }, [tableRows, showAffectedOnly, demoAffectedDomain]);

  const statusText = relativeTime(domainDetails?.latest_governance_evaluation_time || summary?.as_of);

  const confidenceColor = (level) => {
    if (level === "high") return "green";
    if (level === "medium") return "orange";
    return "red";
  };

  const comparisonValue = (value) => (value === null || value === undefined ? "-" : Number(value).toFixed(2));
  const trendPoints = (liveTrendOverride && liveTrendOverride.length)
    ? liveTrendOverride
    : (domainDetails?.risk_trend || []);
  const trendTitle = (liveTrendOverride && liveTrendOverride.length)
    ? "Live Governance Trend"
    : (domainDetails?.trend_label || "Live Governance Trend");
  const focusedDomainRow = tableRows.find((row) => row.domain_name === demoAffectedDomain) || null;
  const focusedDomainStatus = focusedDomainRow?.health_status || "Monitor";
  const focusedActionCardStyle = actionCardStyleByStatus(focusedDomainStatus);

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

      {scenarioComparison ? (
        <Card title="Scenario/Test-Case Comparison" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={[12, 12]}>
            <Col xs={24} md={6}><strong>Domain:</strong> {scenarioComparison?.selected_domain || "-"}</Col>
            <Col xs={24} md={6}><strong>Baseline Score:</strong> {comparisonValue(scenarioComparison?.baseline_score)}</Col>
            <Col xs={24} md={6}><strong>Scenario Score:</strong> {comparisonValue(scenarioComparison?.scenario_score)}</Col>
            <Col xs={24} md={6}><strong>Restored Score:</strong> {comparisonValue(scenarioComparison?.restored_score)}</Col>
            <Col xs={24} md={8}><strong>Scenario Delta:</strong> {comparisonValue(scenarioComparison?.scenario_delta)}</Col>
            <Col xs={24} md={8}><strong>Restore Delta:</strong> {comparisonValue(scenarioComparison?.restore_delta)}</Col>
            <Col xs={24} md={8}><strong>Recovery from Scenario:</strong> {comparisonValue(scenarioComparison?.recovery_from_scenario)}</Col>
            <Col xs={24} md={24}><strong>Status:</strong> {scenarioComparison?.status || "-"}</Col>
          </Row>
        </Card>
      ) : null}

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
      {successMessage ? <Alert type="success" showIcon message={successMessage} style={{ marginBottom: 16 }} /> : null}

      {loading ? (
        <Spin />
      ) : (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic title="Domains Evaluated" value={(summary.domains || []).length} />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card size="small">
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
              <Card size="small">
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

          <Card size="small" title="ADGRI formula" style={{ marginBottom: 12 }}>
            <Paragraph style={{ marginBottom: 6, fontFamily: "monospace", fontSize: 13 }}>
              ADGRI = 100 × (1 − weighted risk)
              <br />
              weighted risk = w<sub>f</sub>×Freshness + w<sub>v</sub>×Volume + w<sub>d</sub>×Distribution
            </Paragraph>
            <Text type="secondary" style={{ fontSize: 12 }}>
              w<sub>f</sub>, w<sub>v</sub>, w<sub>d</sub> are domain-aware effective weights (confidence-normalized per evaluation). Business priority chips below show how each domain type emphasizes factors for governance focus.
            </Text>
          </Card>

          <Card size="small" style={{ marginBottom: 16, background: "#f8fafc", borderColor: "#e2e8f0" }}>
            <Paragraph style={{ marginBottom: 0, color: "#334155", fontSize: 13 }}>
              ADGRI uses the same reliability equation across domains, but factor importance is adjusted using domain-specific business priorities. For example, freshness is more important for Sales, while distribution stability is more important for User and Preference domains.
            </Paragraph>
          </Card>

          <Card title="Domain-Aware ADGRI Reliability" style={{ marginBottom: 16 }}>
            {demoAffectedDomain ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message={`Focused governance assessment: ${demoAffectedDomain} updated. Other domains are recalculated globally.`}
                action={(
                  <Button size="small" onClick={() => setShowAffectedOnly((v) => !v)}>
                    {showAffectedOnly ? "View all domains" : "Show affected domain only"}
                  </Button>
                )}
              />
            ) : null}
            {focusedDomainRow ? (
              <Card
                size="small"
                title="Recommended Governance Action"
                style={{ marginBottom: 12, ...focusedActionCardStyle }}
              >
                <Row gutter={[12, 8]}>
                  <Col xs={24} md={8}><strong>Domain:</strong> {focusedDomainRow.domain_name}</Col>
                  <Col xs={24} md={8}><strong>Main risk:</strong> {focusedDomainRow.main_driver}</Col>
                  <Col xs={24} md={8}><strong>Status:</strong> {focusedDomainRow.health_status}</Col>
                  <Col xs={24}><strong>Action:</strong> {focusedDomainRow.recommended_action}</Col>
                </Row>
              </Card>
            ) : null}
            <Table
              size="small"
              pagination={false}
              scroll={{ x: 1280 }}
              dataSource={visibleTableRows}
              expandable={{
                expandedRowRender: (record) => {
                  const item = record.raw_item || {};
                  const eff = formatEffectiveWeights(record.weights);
                  return (
                    <div style={{ padding: "4px 0 8px", maxWidth: 720 }}>
                      <div style={{ marginBottom: 8 }}>
                        <Text strong style={{ marginRight: 8 }}>Signal confidence</Text>
                        <Tag color={confidenceColor(record.confidence_level)}>
                          {String(record.confidence_level || "low").toUpperCase()}
                        </Tag>
                        {record.confidence_score != null ? (
                          <Text type="secondary" style={{ marginLeft: 8 }}>
                            score {Number(record.confidence_score).toFixed(3)}
                          </Text>
                        ) : null}
                      </div>
                      {eff ? (
                        <div style={{ marginBottom: 8 }}>
                          <Text strong>Effective blend (API): </Text>
                          <Text type="secondary">{eff}</Text>
                        </div>
                      ) : null}
                      <div style={{ marginBottom: 4 }}>
                        <Text strong>Detail: </Text>
                        <Text type="secondary">{item.top_reason || "—"}</Text>
                      </div>
                    </div>
                  );
                },
                rowExpandable: () => true,
              }}
              columns={[
                {
                  title: "Domain",
                  dataIndex: "domain_name",
                  fixed: "left",
                  width: 140,
                  ellipsis: true,
                  render: (text, record) => (
                    <span style={{ whiteSpace: "nowrap", fontWeight: record?.is_demo_focus ? 700 : 400 }}>
                      {text}
                      {record?.is_demo_focus ? <Tag color="blue" style={{ marginLeft: 6 }}>Demo focus</Tag> : null}
                    </span>
                  ),
                },
                {
                  title: "ADGRI Score",
                  dataIndex: "adgri_score",
                  width: 100,
                  render: (value) => (
                    <Tag color={Number(value || 0) >= 85 ? "green" : Number(value || 0) >= 65 ? "gold" : "red"} style={{ margin: 0 }}>
                      {Number(value || 0).toFixed(1)}
                    </Tag>
                  ),
                },
                {
                  title: "Domain Priority Weights",
                  key: "priority_weights",
                  width: 320,
                  render: (_, record) => {
                    const bp = record.business_priorities || DEFAULT_BUSINESS_PRIORITY;
                    const chips = (
                      <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                        <Tag color={priorityTierColor(bp.freshness)} style={{ margin: 0 }}>Freshness {bp.freshness}</Tag>
                        <Tag color={priorityTierColor(bp.volume)} style={{ margin: 0 }}>Volume {bp.volume}</Tag>
                        <Tag color={priorityTierColor(bp.distribution)} style={{ margin: 0 }}>Distribution {bp.distribution}</Tag>
                      </span>
                    );
                    const eff = formatEffectiveWeights(record.weights);
                    return (
                      <div style={{ lineHeight: 1.5 }}>
                        {chips}
                        {eff ? (
                          <div style={{ marginTop: 4 }}>
                            <Text type="secondary" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{eff}</Text>
                          </div>
                        ) : null}
                      </div>
                    );
                  },
                },
                {
                  title: "Volume Risk",
                  dataIndex: "volume_risk",
                  width: 88,
                  align: "right",
                  render: (value) => <span style={{ whiteSpace: "nowrap" }}>{Number((value || 0) * 100).toFixed(1)}%</span>,
                },
                {
                  title: "Freshness Risk",
                  dataIndex: "freshness_risk",
                  width: 96,
                  align: "right",
                  render: (value) => <span style={{ whiteSpace: "nowrap" }}>{Number((value || 0) * 100).toFixed(1)}%</span>,
                },
                {
                  title: "Distribution Risk",
                  dataIndex: "distribution_risk",
                  width: 112,
                  align: "right",
                  render: (value) => <span style={{ whiteSpace: "nowrap" }}>{Number((value || 0) * 100).toFixed(1)}%</span>,
                },
                {
                  title: "Main Risk Driver",
                  dataIndex: "main_driver",
                  width: 120,
                  render: (value) => (
                    <Tag color={mainDriverBadgeColor(value)} style={{ margin: 0 }}>{String(value || "Mixed")}</Tag>
                  ),
                },
                {
                  title: "Status",
                  dataIndex: "health_status",
                  width: 110,
                  render: (value) => <Tag color={healthStatusColor(value)} style={{ margin: 0 }}>{value}</Tag>,
                },
                {
                  title: "Recommended Action",
                  dataIndex: "recommended_action",
                  width: 250,
                  ellipsis: true,
                  render: (text) => (
                    <span style={{ fontWeight: 700, whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.3 }}>
                      {text}
                    </span>
                  ),
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
                    <Col xs={24} md={24}>
                      <div style={{ fontWeight: 600, marginBottom: 6 }}>Domain business priorities (focus)</div>
                      {(() => {
                        const bp = getBusinessPriorities(domainDetails?.domain_name || selectedDomain);
                        return (
                          <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 6 }}>
                            <Tag color={priorityTierColor(bp.freshness)}>Freshness {bp.freshness}</Tag>
                            <Tag color={priorityTierColor(bp.volume)}>Volume {bp.volume}</Tag>
                            <Tag color={priorityTierColor(bp.distribution)}>Distribution {bp.distribution}</Tag>
                          </span>
                        );
                      })()}
                      {formatEffectiveWeights(domainDetails?.weights) ? (
                        <div style={{ marginTop: 8 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>{formatEffectiveWeights(domainDetails?.weights)}</Text>
                        </div>
                      ) : null}
                    </Col>
                    <Col xs={24} md={8}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Signal confidence (detail)</div>
                      <Tag color={confidenceColor(domainDetails?.confidence?.level)}>
                        {String(domainDetails?.confidence?.level || "low").toUpperCase()}
                      </Tag>
                      <span style={{ marginLeft: 8, color: "#64748b", fontSize: 12 }}>
                        score {Number(domainDetails?.confidence?.score || 0).toFixed(3)}
                      </span>
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
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Main risk driver</div>
                    <Tag color={mainDriverBadgeColor(inferMainRiskDriver(domainDetails))}>
                      {inferMainRiskDriver(domainDetails)}
                    </Tag>
                    <div style={{ marginTop: 10, fontWeight: 600, marginBottom: 4 }}>Governance status</div>
                    <Tag color={healthStatusColor(governanceHealthStatus(domainDetails?.adgri_score || domainDetails?.governance_score))}>
                      {governanceHealthStatus(domainDetails?.adgri_score || domainDetails?.governance_score)}
                    </Tag>
                    <div style={{ marginTop: 10, fontWeight: 600, marginBottom: 4 }}>Recommended action</div>
                    <div>{recommendedTableAction(domainDetails?.adgri_score || domainDetails?.governance_score, inferMainRiskDriver(domainDetails))}</div>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Narrative (API)</div>
                    <Text type="secondary" style={{ fontSize: 13 }}>{domainDetails?.top_reason || "—"}</Text>
                  </div>

                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Explanation</div>
                    <Text type="secondary" style={{ fontSize: 13 }}>{domainDetails?.explanation || "—"}</Text>
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

                <Card title={`${trendTitle} (Latest 7 points)`}>
                  {(liveTrendOverride && liveTrendOverride.length) ? (
                    <div style={{ color: "#64748b", marginBottom: 10 }}>
                      Scenario/test-case results are isolated in the comparison section; this trend remains focused on live governance history.
                    </div>
                  ) : null}
                  {trendPoints.length ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={trendPoints}>
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
