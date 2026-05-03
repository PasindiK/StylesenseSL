import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Space, Table, Tag, Typography, Upload } from "antd";
import axios from "axios";
import { API_BASE } from "../config";

const { Title, Paragraph, Text } = Typography;

function formatTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function formatTimeShort(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  const date = parsed.toISOString().slice(0, 10);
  const time = parsed.toTimeString().slice(0, 5);
  return `${date} ${time}`;
}

function actionColor(action) {
  if (action === "AUTO_ASSIGN") return "green";
  if (action === "PROVISIONAL_ASSIGN") return "orange";
  if (String(action || "").includes("NEW_DOMAIN_CANDIDATE")) return "magenta";
  return "red";
}

function confidenceText(value) {
  const num = Number(value || 0);
  return `${(num * 100).toFixed(1)}%`;
}

export default function SilverToDomainLoader() {
  const [datasetRows, setDatasetRows] = useState([]);
  const [resultRows, setResultRows] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [createdDomains, setCreatedDomains] = useState([]);
  const [historyRows, setHistoryRows] = useState([]);
  const [latestRunId, setLatestRunId] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [runningDetection, setRunningDetection] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [resettingDemo, setResettingDemo] = useState(false);
  const [selectedUploadFile, setSelectedUploadFile] = useState(null);
  const [reviewSubmitting, setReviewSubmitting] = useState("");
  const [deletingDomain, setDeletingDomain] = useState("");
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const loadDatasets = async () => {
    setLoadingDatasets(true);
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/silver-datasets`);
      setDatasetRows(Array.isArray(res?.data?.datasets) ? res.data.datasets : []);
    } catch (_err) {
      setError("Unable to load Silver datasets.");
    } finally {
      setLoadingDatasets(false);
    }
  };

  const loadResults = async () => {
    setLoadingResults(true);
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-detect/results?limit=50`);
      const rows = Array.isArray(res?.data?.results) ? res.data.results : [];
      applyLatestRunRows(rows);
    } catch (_err) {
      setError("Unable to load detection results.");
    } finally {
      setLoadingResults(false);
    }
  };

  const loadReviewDecisions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-review/decisions`);
      setDecisions(Array.isArray(res?.data?.decisions) ? res.data.decisions : []);
    } catch (_err) {
      setDecisions([]);
    }
  };

  const loadCreatedDomains = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/created-domains`);
      setCreatedDomains(Array.isArray(res?.data?.created_domains) ? res.data.created_domains : []);
    } catch (_err) {
      setCreatedDomains([]);
    }
  };

  const dedupeByDataset = (rows) => {
    const seen = new Set();
    return rows.filter((row) => {
      const key = String(row?.dataset_name || "").toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };

  const applyLatestRunRows = (rows) => {
    if (!rows.length) {
      setLatestRunId("");
      setResultRows([]);
      setHistoryRows([]);
      return;
    }
    const latestId = rows[0]?.run_id || "";
    const latest = dedupeByDataset(rows.filter((row) => row?.run_id === latestId));
    const history = rows.filter((row) => row?.run_id !== latestId);
    setLatestRunId(String(latestId || ""));
    setResultRows(latest);
    setHistoryRows(history);
  };

  const runDetection = async () => {
    setRunningDetection(true);
    setError("");
    setSuccessMessage("");
    try {
      const res = await axios.post(`${API_BASE}/api/datamesh/domain-detect/run`);
      const runId = res?.data?.run_id || "latest";
      const count = Number(res?.data?.count || 0);
      setSuccessMessage(`Detection completed successfully. Run ID: ${runId}. Processed datasets: ${count}.`);
      const latestRows = Array.isArray(res?.data?.results) ? res.data.results : [];
      applyLatestRunRows(latestRows);
      await Promise.all([loadDatasets(), loadReviewDecisions(), loadCreatedDomains()]);
    } catch (_err) {
      setError("Failed to run auto domain detection.");
    } finally {
      setRunningDetection(false);
    }
  };

  const uploadDataset = async () => {
    if (!selectedUploadFile) {
      setError("Please select a CSV file to upload.");
      setSuccessMessage("");
      return;
    }

    setUploading(true);
    setError("");
    setSuccessMessage("");
    try {
      const formData = new FormData();
      formData.append("upload_file", selectedUploadFile);
      await axios.post(`${API_BASE}/api/datamesh/silver-datasets/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSuccessMessage("Dataset uploaded successfully. Click Run Auto Domain Detection to classify it.");
      setSelectedUploadFile(null);
      await loadDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to upload dataset.");
    } finally {
      setUploading(false);
    }
  };

  const resetDemoState = async () => {
    setResettingDemo(true);
    setError("");
    setSuccessMessage("");
    try {
      const res = await axios.post(`${API_BASE}/api/datamesh/domain-detect/reset`);
      const removedCount = Number(res?.data?.cleanup?.removed_count || 0);
      setSuccessMessage(`Demo reset complete. Removed ${removedCount} uploaded test file(s) and cleared detection history.`);
      setResultRows([]);
      setHistoryRows([]);
      setLatestRunId("");
      setDecisions([]);
      setCreatedDomains([]);
      await loadDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to reset demo state.");
    } finally {
      setResettingDemo(false);
    }
  };

  const submitReviewAction = async (record, reviewerAction) => {
    const submitKey = `${record.dataset_name}-${reviewerAction}`;
    setReviewSubmitting(submitKey);
    setError("");
    setSuccessMessage("");
    try {
      let approvedDomain = "";
      if (reviewerAction === "CHANGE_DOMAIN") {
        approvedDomain = window.prompt("Enter approved domain (e.g. sales_domain):", record.best_domain || "") || "";
      }
      if (reviewerAction === "CREATE_DOMAIN_AFTER_APPROVAL") {
        approvedDomain = record.candidate_domain_name || "";
      }
      const reviewerNote = window.prompt("Reviewer note (optional):", "") || "";
      await axios.post(`${API_BASE}/api/datamesh/domain-review/decision`, {
        detection_run_id: record.run_id,
        dataset_name: record.dataset_name,
        reviewer_action: reviewerAction,
        approved_domain: approvedDomain,
        reviewer_note: reviewerNote,
      });
      if (reviewerAction === "CREATE_DOMAIN_AFTER_APPROVAL") {
        setSuccessMessage("Domain candidate approved and created. Rerun detection to auto-route this dataset.");
      } else {
        setSuccessMessage(`Review decision submitted: ${reviewerAction} for ${record.dataset_name}.`);
      }
      await Promise.all([loadReviewDecisions(), loadCreatedDomains()]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to submit review decision.");
    } finally {
      setReviewSubmitting("");
    }
  };

  const deleteCreatedDomain = async (domainName) => {
    const normalized = String(domainName || "");
    if (!normalized) return;
    const confirmed = window.confirm(`Delete created domain '${normalized}'?`);
    if (!confirmed) return;
    setDeletingDomain(normalized);
    setError("");
    setSuccessMessage("");
    try {
      await axios.delete(`${API_BASE}/api/datamesh/created-domains/${encodeURIComponent(normalized)}`);
      setSuccessMessage(`Created domain '${normalized}' marked as deleted.`);
      await loadCreatedDomains();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to delete created domain.");
    } finally {
      setDeletingDomain("");
    }
  };

  const renderReviewActions = (record) => {
    const isProvisional = record.action === "PROVISIONAL_ASSIGN";
    const isCandidate = record.action === "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW";

    if (isProvisional) {
      return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, minWidth: 260 }}>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-APPROVE_ASSIGNMENT`}
            onClick={() => submitReviewAction(record, "APPROVE_ASSIGNMENT")}
          >
            Approve
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-CHANGE_DOMAIN`}
            onClick={() => submitReviewAction(record, "CHANGE_DOMAIN")}
          >
            Change
          </Button>
          <Button
            size="small"
            danger
            loading={reviewSubmitting === `${record.dataset_name}-REJECT`}
            onClick={() => submitReviewAction(record, "REJECT")}
          >
            Reject
          </Button>
        </div>
      );
    }

    if (isCandidate) {
      return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, minWidth: 260 }}>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-VALIDATE_CANDIDATE`}
            onClick={() => submitReviewAction(record, "VALIDATE_CANDIDATE")}
          >
            Validate
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-CREATE_DOMAIN_AFTER_APPROVAL`}
            onClick={() => submitReviewAction(record, "CREATE_DOMAIN_AFTER_APPROVAL")}
          >
            Create Domain
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-RAISE_TICKET`}
            onClick={() => submitReviewAction(record, "RAISE_TICKET")}
          >
            Raise Ticket
          </Button>
          <Button
            size="small"
            danger
            loading={reviewSubmitting === `${record.dataset_name}-REJECT`}
            onClick={() => submitReviewAction(record, "REJECT")}
          >
            Reject
          </Button>
        </div>
      );
    }

    return "-";
  };

  useEffect(() => {
    setError("");
    Promise.all([loadDatasets(), loadResults(), loadReviewDecisions(), loadCreatedDomains()]);
  }, []);

  const datasetTableData = useMemo(
    () =>
      datasetRows.map((item, index) => ({
        key: `${item.dataset_name || "dataset"}-${index}`,
        dataset_name: item.dataset_name || "-",
        row_count: Number(item.row_count || 0),
        column_count: Array.isArray(item.columns) ? item.columns.length : 0,
        timestamp: item.timestamp || "-",
      })),
    [datasetRows]
  );

  const detectionTableData = useMemo(
    () =>
      resultRows.map((item, index) => ({
        ...item,
        key: `${item.run_id || "run"}-${item.dataset_name || "dataset"}-${index}`,
      })),
    [resultRows]
  );

  const reviewQueueData = useMemo(
    () => detectionTableData.filter((item) => Boolean(item.review_required)),
    [detectionTableData]
  );

  const detectionColumns = [
    { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name", width: 200 },
    { title: "Best domain", dataIndex: "best_domain", key: "best_domain", width: 150, render: (v) => v || "-" },
    { title: "Confidence", dataIndex: "confidence_score", key: "confidence_score", width: 110, render: confidenceText },
    { title: "Second best domain", dataIndex: "second_best_domain", key: "second_best_domain", width: 170, render: (v) => v || "-" },
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
      width: 220,
      render: (value) => <Tag color={actionColor(value)}>{String(value || "-")}</Tag>,
    },
    {
      title: "Review required",
      dataIndex: "review_required",
      key: "review_required",
      width: 130,
      render: (value) => <Tag color={value ? "red" : "green"}>{value ? "YES" : "NO"}</Tag>,
    },
    { title: "Candidate domain", dataIndex: "candidate_domain_name", key: "candidate_domain_name", width: 180, render: (v) => v || "-" },
    { title: "Final domain", dataIndex: "final_domain", key: "final_domain", width: 140, render: (v) => v || "-" },
    { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", width: 150, render: formatTimeShort },
    { title: "Review actions", key: "review_actions", width: 320, render: (_, record) => renderReviewActions(record) },
  ];

  const reviewQueueColumns = [
    { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name", width: 200 },
    { title: "Best domain", dataIndex: "best_domain", key: "best_domain", width: 150, render: (v) => v || "-" },
    { title: "Confidence", dataIndex: "confidence_score", key: "confidence_score", width: 110, render: confidenceText },
    { title: "Action", dataIndex: "action", key: "action", width: 220, render: (value) => <Tag color={actionColor(value)}>{String(value || "-")}</Tag> },
    { title: "Candidate domain", dataIndex: "candidate_domain_name", key: "candidate_domain_name", width: 180, render: (v) => v || "-" },
    { title: "Final domain", dataIndex: "final_domain", key: "final_domain", width: 140, render: (v) => v || "-" },
    { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", width: 150, render: formatTimeShort },
    { title: "Review actions", key: "review_actions", width: 320, render: (_, record) => renderReviewActions(record) },
  ];

  return (
    <div style={{ padding: 16, maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <Title level={2} style={{ marginBottom: 8 }}>Silver to Domain Loader</Title>

      <Card style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginBottom: 8 }}>Adaptive Silver-to-Domain Loading</Title>
        <Paragraph style={{ marginBottom: 0, color: "#64748b" }}>
          This module reads Silver-layer dataset metadata, calculates domain confidence scores, and routes datasets
          into Data Mesh domains. Low-confidence datasets are flagged for review or created as new domain candidates.
        </Paragraph>
      </Card>
      <Card style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginBottom: 8 }}>Human-in-the-Loop Domain Governance</Title>
        <Paragraph style={{ marginBottom: 0, color: "#64748b" }}>
          New or uncertain domains are not created automatically in production. The system identifies candidate domains
          and sends them to a governance review process. Reviewers can approve, change, reject, or raise a governance
          ticket before any domain product is created.
        </Paragraph>
      </Card>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Decision guide: AUTO_ASSIGN = high confidence; PROVISIONAL_ASSIGN = medium confidence (review required); NEW_DOMAIN_CANDIDATE_PENDING_REVIEW = low confidence (human review required)."
      />
      <Card title="Upload Silver Dataset" style={{ marginBottom: 16 }}>
        <Paragraph style={{ color: "#64748b", marginBottom: 10 }}>
          Upload a new CSV dataset into the Silver layer and run domain detection to route it into a Data Mesh domain.
        </Paragraph>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Use this to demonstrate how the system handles newly arriving Silver-layer datasets."
        />
        <Space wrap>
          <Upload
            accept=".csv"
            maxCount={1}
            beforeUpload={(file) => {
              setSelectedUploadFile(file);
              return false;
            }}
            onRemove={() => {
              setSelectedUploadFile(null);
            }}
            fileList={selectedUploadFile ? [selectedUploadFile] : []}
          >
            <Button>Select CSV File</Button>
          </Upload>
          <Button type="primary" loading={uploading} onClick={uploadDataset}>
            Upload
          </Button>
          <Button danger loading={resettingDemo} onClick={resetDemoState}>
            Remove Uploaded Test Files
          </Button>
        </Space>
      </Card>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
      {successMessage ? <Alert type="success" showIcon message={successMessage} style={{ marginBottom: 16 }} /> : null}

      <Card
        title="Silver Dataset Overview"
        extra={
          <Button type="primary" loading={runningDetection} onClick={runDetection}>
            Run Auto Domain Detection
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <div style={{ width: "100%", overflowX: "auto" }}>
          <Table
            dataSource={datasetTableData}
            loading={loadingDatasets}
            pagination={{ pageSize: 8 }}
            scroll={{ x: 760 }}
            size="middle"
            columns={[
              { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name", width: 260 },
              { title: "Row count", dataIndex: "row_count", key: "row_count", width: 120 },
              { title: "Column count", dataIndex: "column_count", key: "column_count", width: 130 },
              { title: "Last modified / timestamp", dataIndex: "timestamp", key: "timestamp", width: 210, render: formatTimeShort },
            ]}
          />
        </div>
      </Card>

      <Card title="Detection Results" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 10, color: "#64748b" }}>
          Showing latest run only: <strong>{latestRunId || "-"}</strong>
        </div>
        <div style={{ width: "100%", overflowX: "auto" }}>
          <Table
            dataSource={detectionTableData}
            loading={loadingResults}
            pagination={{ pageSize: 10 }}
            columns={detectionColumns}
            scroll={{ x: 1800 }}
            size="middle"
            expandable={{
              expandedRowRender: (record) => (
                <div style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, background: "#fafcff" }}>
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    <div>
                      <Text strong>Matched columns:</Text>{" "}
                      <Text>{Array.isArray(record.columns_detected) ? record.columns_detected.join(", ") : "-"}</Text>
                    </div>
                    <div>
                      <Text strong>All domain scores:</Text>
                      <pre style={{ margin: "6px 0 0", background: "#f8fafc", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                        {JSON.stringify(record.all_domain_scores || {}, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <Text strong>Explanation:</Text> <Text>{record.explanation || "-"}</Text>
                    </div>
                  </Space>
                </div>
              ),
            }}
          />
        </div>
        <div style={{ marginTop: 12 }}>
          <Button onClick={() => setShowHistory((prev) => !prev)}>
            {showHistory ? "Hide History" : "View History"}
          </Button>
        </div>
      </Card>

      <Card title={`Review Queue (${reviewQueueData.length})`}>
        <div style={{ width: "100%", overflowX: "auto" }}>
          <Table
            dataSource={reviewQueueData}
            loading={loadingResults}
            pagination={{ pageSize: 10 }}
            columns={reviewQueueColumns}
            scroll={{ x: 1500 }}
            size="middle"
            locale={{ emptyText: "No datasets currently require review." }}
          />
        </div>
      </Card>

      <Card title={`Review Decisions (${decisions.length})`} style={{ marginTop: 16 }}>
        <div style={{ width: "100%", overflowX: "auto" }}>
          <Table
            dataSource={decisions.map((item, index) => ({ ...item, key: `${item.decision_id || "decision"}-${index}` }))}
            pagination={{ pageSize: 8 }}
            scroll={{ x: 1200 }}
            size="middle"
            columns={[
              { title: "Decision ID", dataIndex: "decision_id", key: "decision_id", width: 140 },
              { title: "Run ID", dataIndex: "detection_run_id", key: "detection_run_id", width: 140 },
              { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", width: 210 },
              { title: "Original Action", dataIndex: "original_action", key: "original_action", width: 230 },
              { title: "Reviewer Action", dataIndex: "reviewer_action", key: "reviewer_action", width: 220 },
              { title: "Approved Domain", dataIndex: "approved_domain", key: "approved_domain", width: 170, render: (v) => v || "-" },
              { title: "Ticket", dataIndex: "ticket_status", key: "ticket_status", width: 110 },
              { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", width: 180, render: formatTimeShort },
            ]}
          />
        </div>
      </Card>

      <Card title={`Created Domains (${createdDomains.length})`} style={{ marginTop: 16 }}>
        <Table
          dataSource={createdDomains.map((item, index) => ({ ...item, key: `${item.domain_id || item.domain_name || "domain"}-${index}` }))}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Domain name", dataIndex: "domain_name", key: "domain_name" },
            { title: "Source dataset", dataIndex: "source_dataset_name", key: "source_dataset_name", render: (v) => v || "-" },
            {
              title: "Status",
              dataIndex: "status",
              key: "status",
              render: (value) => <Tag color={String(value || "").toUpperCase() === "ACTIVE" ? "green" : "default"}>{String(value || "-")}</Tag>,
            },
            { title: "Created at", dataIndex: "created_at", key: "created_at", render: formatTimeShort },
            {
              title: "Actions",
              key: "actions",
              render: (_, record) => (
                record?.is_system_domain ? (
                  <Text type="secondary">System domain</Text>
                ) : String(record?.status || "").toUpperCase() === "ACTIVE" ? (
                  <Button
                    size="small"
                    danger
                    loading={deletingDomain === record.domain_name}
                    onClick={() => deleteCreatedDomain(record.domain_name)}
                  >
                    Delete Created Domain
                  </Button>
                ) : (
                  <Text type="secondary">-</Text>
                )
              ),
            },
          ]}
        />
      </Card>

      {showHistory ? (
        <Card title="Detection History (Past Runs)" style={{ marginTop: 16 }}>
          <div style={{ width: "100%", overflowX: "auto" }}>
            <Table
              dataSource={historyRows.map((item, index) => ({ ...item, key: `history-${item.run_id || "run"}-${index}` }))}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 900 }}
              size="middle"
              columns={[
                { title: "Run ID", dataIndex: "run_id", key: "run_id", width: 150 },
                { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name", width: 240 },
                { title: "Best domain", dataIndex: "best_domain", key: "best_domain", width: 170, render: (v) => v || "-" },
                { title: "Action", dataIndex: "action", key: "action", width: 250, render: (value) => <Tag color={actionColor(value)}>{String(value || "-")}</Tag> },
                { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", width: 180, render: formatTimeShort },
              ]}
            />
          </div>
        </Card>
      ) : null}
    </div>
  );
}
