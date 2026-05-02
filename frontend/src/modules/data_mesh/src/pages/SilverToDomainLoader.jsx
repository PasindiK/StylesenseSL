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

function actionColor(action) {
  if (action === "AUTO_ASSIGN") return "green";
  if (action === "PROVISIONAL_ASSIGN") return "orange";
  if (action === "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW") return "purple";
  return "magenta";
}

function confidenceText(value) {
  const num = Number(value || 0);
  return `${num.toFixed(4)} (${(num * 100).toFixed(1)}%)`;
}

export default function SilverToDomainLoader() {
  const [datasetRows, setDatasetRows] = useState([]);
  const [resultRows, setResultRows] = useState([]);
  const [decisions, setDecisions] = useState([]);
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
      await Promise.all([loadDatasets(), loadReviewDecisions()]);
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
      if (reviewerAction === "CHANGE_DOMAIN" || reviewerAction === "CREATE_DOMAIN_AFTER_APPROVAL") {
        approvedDomain = window.prompt("Enter approved domain (e.g. sales_domain):", record.best_domain || "") || "";
      }
      const reviewerNote = window.prompt("Reviewer note (optional):", "") || "";
      await axios.post(`${API_BASE}/api/datamesh/domain-review/decision`, {
        detection_run_id: record.run_id,
        dataset_name: record.dataset_name,
        reviewer_action: reviewerAction,
        approved_domain: approvedDomain,
        reviewer_note: reviewerNote,
      });
      setSuccessMessage(`Review decision submitted: ${reviewerAction} for ${record.dataset_name}.`);
      await loadReviewDecisions();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to submit review decision.");
    } finally {
      setReviewSubmitting("");
    }
  };

  const renderReviewActions = (record) => {
    const isProvisional = record.action === "PROVISIONAL_ASSIGN";
    const isCandidate = record.action === "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW";

    if (isProvisional) {
      return (
        <Space wrap>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-APPROVE_ASSIGNMENT`}
            onClick={() => submitReviewAction(record, "APPROVE_ASSIGNMENT")}
          >
            Approve Assignment
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-CHANGE_DOMAIN`}
            onClick={() => submitReviewAction(record, "CHANGE_DOMAIN")}
          >
            Change Domain
          </Button>
          <Button
            size="small"
            danger
            loading={reviewSubmitting === `${record.dataset_name}-REJECT`}
            onClick={() => submitReviewAction(record, "REJECT")}
          >
            Reject
          </Button>
        </Space>
      );
    }

    if (isCandidate) {
      return (
        <Space wrap>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-VALIDATE_CANDIDATE`}
            onClick={() => submitReviewAction(record, "VALIDATE_CANDIDATE")}
          >
            Validate Candidate
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-CREATE_DOMAIN_AFTER_APPROVAL`}
            onClick={() => submitReviewAction(record, "CREATE_DOMAIN_AFTER_APPROVAL")}
          >
            Create Domain After Approval
          </Button>
          <Button
            size="small"
            loading={reviewSubmitting === `${record.dataset_name}-RAISE_TICKET`}
            onClick={() => submitReviewAction(record, "RAISE_TICKET")}
          >
            Raise Governance Ticket
          </Button>
          <Button
            size="small"
            danger
            loading={reviewSubmitting === `${record.dataset_name}-REJECT`}
            onClick={() => submitReviewAction(record, "REJECT")}
          >
            Reject Candidate
          </Button>
        </Space>
      );
    }

    return "-";
  };

  useEffect(() => {
    setError("");
    Promise.all([loadDatasets(), loadResults(), loadReviewDecisions()]);
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
    { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name" },
    { title: "Best domain", dataIndex: "best_domain", key: "best_domain", render: (v) => v || "-" },
    { title: "Confidence score", dataIndex: "confidence_score", key: "confidence_score", render: confidenceText },
    { title: "Second best domain", dataIndex: "second_best_domain", key: "second_best_domain", render: (v) => v || "-" },
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
      render: (value) => <Tag color={actionColor(value)}>{String(value || "-")}</Tag>,
    },
    {
      title: "Review required",
      dataIndex: "review_required",
      key: "review_required",
      render: (value) => <Tag color={value ? "red" : "green"}>{value ? "YES" : "NO"}</Tag>,
    },
    { title: "Candidate domain name", dataIndex: "candidate_domain_name", key: "candidate_domain_name", render: (v) => v || "-" },
    { title: "Final domain", dataIndex: "final_domain", key: "final_domain", render: (v) => v || "-" },
    { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", render: formatTime },
    { title: "Review Actions", key: "review_actions", render: (_, record) => renderReviewActions(record) },
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
        <Table
          dataSource={datasetTableData}
          loading={loadingDatasets}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name" },
            { title: "Row count", dataIndex: "row_count", key: "row_count" },
            { title: "Column count", dataIndex: "column_count", key: "column_count" },
            { title: "Last modified / timestamp", dataIndex: "timestamp", key: "timestamp", render: formatTime },
          ]}
        />
      </Card>

      <Card title="Detection Results" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 10, color: "#64748b" }}>
          Showing latest run only: <strong>{latestRunId || "-"}</strong>
        </div>
        <Table
          dataSource={detectionTableData}
          loading={loadingResults}
          pagination={{ pageSize: 10 }}
          columns={detectionColumns}
          expandable={{
            expandedRowRender: (record) => (
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <div>
                  <Text strong>all_domain_scores:</Text>
                  <pre style={{ margin: "6px 0 0", background: "#f8fafc", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                    {JSON.stringify(record.all_domain_scores || {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <Text strong>columns_detected:</Text>{" "}
                  <Text>{Array.isArray(record.columns_detected) ? record.columns_detected.join(", ") : "-"}</Text>
                </div>
                <div>
                  <Text strong>explanation:</Text> <Text>{record.explanation || "-"}</Text>
                </div>
              </Space>
            ),
          }}
        />
        <div style={{ marginTop: 12 }}>
          <Button onClick={() => setShowHistory((prev) => !prev)}>
            {showHistory ? "Hide History" : "View History"}
          </Button>
        </div>
      </Card>

      <Card title={`Review Queue (${reviewQueueData.length})`}>
        <Table
          dataSource={reviewQueueData}
          loading={loadingResults}
          pagination={{ pageSize: 10 }}
          columns={detectionColumns}
        />
      </Card>

      <Card title={`Review Decisions (${decisions.length})`} style={{ marginTop: 16 }}>
        <Table
          dataSource={decisions.map((item, index) => ({ ...item, key: `${item.decision_id || "decision"}-${index}` }))}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Decision ID", dataIndex: "decision_id", key: "decision_id" },
            { title: "Run ID", dataIndex: "detection_run_id", key: "detection_run_id" },
            { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name" },
            { title: "Original Action", dataIndex: "original_action", key: "original_action" },
            { title: "Reviewer Action", dataIndex: "reviewer_action", key: "reviewer_action" },
            { title: "Approved Domain", dataIndex: "approved_domain", key: "approved_domain", render: (v) => v || "-" },
            { title: "Ticket", dataIndex: "ticket_status", key: "ticket_status" },
            { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", render: formatTime },
          ]}
        />
      </Card>

      {showHistory ? (
        <Card title="Detection History (Past Runs)" style={{ marginTop: 16 }}>
          <Table
            dataSource={historyRows.map((item, index) => ({ ...item, key: `history-${item.run_id || "run"}-${index}` }))}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "Run ID", dataIndex: "run_id", key: "run_id" },
              { title: "Dataset name", dataIndex: "dataset_name", key: "dataset_name" },
              { title: "Best domain", dataIndex: "best_domain", key: "best_domain", render: (v) => v || "-" },
              { title: "Action", dataIndex: "action", key: "action", render: (value) => <Tag color={actionColor(value)}>{String(value || "-")}</Tag> },
              { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", render: formatTime },
            ]}
          />
        </Card>
      ) : null}
    </div>
  );
}
