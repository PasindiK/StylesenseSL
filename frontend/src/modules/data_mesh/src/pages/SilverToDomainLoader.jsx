import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Collapse, Col, Empty, Form, Input, Modal, Row, Select, Space, Table, Tabs, Tag, Typography, Upload } from "antd";
import axios from "axios";
import { API_BASE } from "../config";

const { Title, Paragraph, Text } = Typography;

const ADMISSION_STATUS_LABELS = {
  AUTO_LOAD_ELIGIBLE: "Ready to load",
  AUTO_ASSIGN_CREATED_DOMAIN: "Ready to load",
  HUMAN_REVIEW_REQUIRED: "Review required",
  NEW_DOMAIN_CANDIDATE: "Orphan candidate",
  GOVERNANCE_TICKET_RECOMMENDED: "Ticket required",
};

const MATERIALIZATION_STATUS_LABELS = {
  ALREADY_GOVERNED: "Already in domain layer",
  NOT_LOADED: "Not loaded",
  LOADED_TO_DOMAIN: "Loaded to domain product",
  LOAD_FAILED: "Load failed",
};

const CORE_DATASETS = new Set([
  "interactions_clean.csv",
  "products_clean.csv",
  "shops_clean.csv",
  "transactions_clean.csv",
  "trends_clean.csv",
  "users_clean.csv",
  "users_preferences_clean.csv",
]);

const CORE_EXPECTED_DOMAIN = {
  "interactions_clean.csv": "interaction_domain",
  "products_clean.csv": "product_domain",
  "shops_clean.csv": "shop_domain",
  "transactions_clean.csv": "sales_domain",
  "trends_clean.csv": "engagement_domain",
  "users_clean.csv": "users_domain",
  "users_preferences_clean.csv": "user_preferences_domain",
};

function formatTimeShort(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  const y = parsed.getFullYear();
  const m = String(parsed.getMonth() + 1).padStart(2, "0");
  const d = String(parsed.getDate()).padStart(2, "0");
  const hh = String(parsed.getHours()).padStart(2, "0");
  const mm = String(parsed.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${d} ${hh}:${mm}`;
}

function pct(value) {
  const num = Number(value || 0);
  return `${(num * 100).toFixed(1)}%`;
}

function admissionStatusColor(status) {
  if (status === "Known domain dataset") return "blue";
  if (status === "Ready to load") return "green";
  if (status === "Review required") return "orange";
  if (status === "Orphan candidate") return "magenta";
  if (status === "Ticket required") return "red";
  if (status === "Ticket Opened") return "orange";
  if (status === "Rejected") return "red";
  if (status === "Loaded") return "green";
  return "default";
}

function materializationStatusColor(status) {
  if (status === "Already in domain layer") return "blue";
  if (status === "Loaded to domain product") return "green";
  if (status === "Load failed") return "red";
  return "default";
}

function contractGateColor(gate) {
  const g = String(gate || "");
  if (g === "PASSED") return "green";
  if (g === "FAILED") return "red";
  if (g === "REVIEW") return "orange";
  return "default";
}

function decisionStatusColor(status) {
  const s = String(status || "");
  if (s === "APPROVED" || s === "DOMAIN_CREATED") return "green";
  if (s === "CHANGED") return "cyan";
  if (s === "REJECTED") return "red";
  if (s === "TICKET_OPENED") return "orange";
  return "default";
}

function reviewActionSelectOptions(record) {
  const d = String(record?.admission_decision || record?.action || "");
  const common = [
    { value: "APPROVE_PROVISIONAL", label: "Approve existing domain" },
    { value: "CHANGE_DOMAIN", label: "Change domain" },
    { value: "MARK_ORPHAN_CANDIDATE", label: "Mark as orphan candidate" },
    { value: "RAISE_TICKET", label: "Raise ticket" },
  ];
  if (d === "NEW_DOMAIN_CANDIDATE") {
    return [
      { value: "VALIDATE_CANDIDATE", label: "Approve existing domain" },
      { value: "CREATE_DOMAIN_AFTER_APPROVAL", label: "Create candidate domain" },
      { value: "MARK_ORPHAN_CANDIDATE", label: "Mark as orphan candidate" },
      { value: "RAISE_TICKET", label: "Raise ticket" },
      { value: "REJECT_CANDIDATE", label: "Reject" },
    ];
  }
  return [...common, { value: "REJECT_PROVISIONAL", label: "Reject" }];
}

function passportMemoryLabel(record, passport) {
  const mode = passport.memory_display_mode || record.memory_display_mode;
  if (mode === "no_bank") return "No domain review memory entries yet.";
  if (mode === "neutral") return "No direct feedback entries for this suggested domain.";
  if (mode === "registry") return "Created-domain registry evidence.";
  if (mode === "scored" && (passport.memory_score_for_display != null || record.memory_feedback_score != null)) {
    return pct(passport.memory_score_for_display ?? record.memory_feedback_score);
  }
  return "—";
}

export default function SilverToDomainLoader() {
  const [datasetRows, setDatasetRows] = useState([]);
  const [resultRows, setResultRows] = useState([]);
  const [latestRunId, setLatestRunId] = useState("");
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [runningDetection, setRunningDetection] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [resettingDemo, setResettingDemo] = useState(false);
  const [loadingDemoList, setLoadingDemoList] = useState(false);
  const [loadingDemoCopy, setLoadingDemoCopy] = useState(false);
  const [demoFileNames, setDemoFileNames] = useState([]);
  const [selectedDemoFile, setSelectedDemoFile] = useState(null);
  const [selectedUploadFile, setSelectedUploadFile] = useState(null);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [memoryBank, setMemoryBank] = useState({ entries: [], count: 0 });
  const [reviewDecisions, setReviewDecisions] = useState([]);
  const [materializationRows, setMaterializationRows] = useState([]);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [applyingKey, setApplyingKey] = useState(null);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewRecord, setReviewRecord] = useState(null);
  const [selectedPassportRow, setSelectedPassportRow] = useState(null);
  const [reviewForm] = Form.useForm();
  const watchedReviewAction = Form.useWatch("review_action", reviewForm);

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
      return;
    }
    const latestId = rows[0]?.run_id || "";
    const latest = dedupeByDataset(rows.filter((row) => row?.run_id === latestId));
    setLatestRunId(String(latestId || ""));
    setResultRows(latest);
  };

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
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-detect/results?limit=80`);
      const rows = Array.isArray(res?.data?.results) ? res.data.results : [];
      applyLatestRunRows(rows);
    } catch (_err) {
      setError("Unable to load admission assessment results.");
    } finally {
      setLoadingResults(false);
    }
  };

  const loadDemoFileList = async () => {
    setLoadingDemoList(true);
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/silver-datasets/demo-files`);
      const files = Array.isArray(res?.data?.files) ? res.data.files : [];
      setDemoFileNames(files);
      if (files.length && !selectedDemoFile) setSelectedDemoFile(files[0]);
    } catch (_err) {
      setDemoFileNames([]);
    } finally {
      setLoadingDemoList(false);
    }
  };

  const loadMemoryBank = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-memory-bank`);
      setMemoryBank({
        entries: res?.data?.entries || [],
        count: res?.data?.count ?? 0,
      });
    } catch (_err) {
      /* optional */
    }
  };

  const loadReviewDecisions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-review/decisions`);
      setReviewDecisions(Array.isArray(res?.data?.decisions) ? res.data.decisions : []);
    } catch (_err) {
      /* optional */
    }
  };

  const loadMaterializations = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/datamesh/domain-admission/materializations`);
      setMaterializationRows(Array.isArray(res?.data?.records) ? res.data.records : []);
    } catch (_err) {
      setMaterializationRows([]);
    }
  };

  const refreshAux = async () => {
    await Promise.all([loadMemoryBank(), loadReviewDecisions(), loadMaterializations()]);
  };

  useEffect(() => {
    setError("");
    Promise.all([loadDatasets(), loadResults(), refreshAux(), loadDemoFileList()]);
  }, []);

  const runDetection = async () => {
    setRunningDetection(true);
    setError("");
    setSuccessMessage("");
    try {
      const res = await axios.post(`${API_BASE}/api/datamesh/domain-detect/run`);
      const runId = res?.data?.run_id || "latest";
      const count = Number(res?.data?.count || 0);
      setSuccessMessage(`Admission assessment completed. Run ${runId}. Datasets evaluated: ${count}.`);
      await Promise.all([loadDatasets(), refreshAux(), loadResults()]);
    } catch (_err) {
      setError("Failed to run admission assessment.");
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
      setSuccessMessage("Dataset registered in Silver. Run admission assessment to classify.");
      setSelectedUploadFile(null);
      await loadDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to upload dataset.");
    } finally {
      setUploading(false);
    }
  };

  const loadDemoDataset = async () => {
    if (!selectedDemoFile) {
      setError("Select a sample file.");
      return;
    }
    setLoadingDemoCopy(true);
    setError("");
    setSuccessMessage("");
    try {
      await axios.post(`${API_BASE}/api/datamesh/silver-datasets/load-demo`, {
        dataset_name: selectedDemoFile,
        demo_type: "demo_load",
      });
      setSuccessMessage("Sample dataset copied to Silver.");
      await loadDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load sample dataset.");
    } finally {
      setLoadingDemoCopy(false);
    }
  };

  const resetDemoState = async () => {
    setResettingDemo(true);
    setError("");
    setSuccessMessage("");
    try {
      await axios.post(`${API_BASE}/api/datamesh/demo/reset`);
      setSuccessMessage("Core Silver state restored. Only canonical Silver datasets remain.");
      setLatestRunId("");
      setResultRows([]);
      await Promise.all([loadDatasets(), loadResults(), refreshAux(), loadDemoFileList()]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to restore core Silver state.");
    } finally {
      setResettingDemo(false);
    }
  };

  const openReviewModal = (record) => {
    setReviewRecord(record);
    const opts = reviewActionSelectOptions(record);
    reviewForm.setFieldsValue({
      review_action: opts[0]?.value,
      reviewer_note: "",
      approved_domain: record.best_domain || "",
      candidate_domain_name: record.candidate_domain_name || "",
    });
    setReviewModalOpen(true);
  };

  const submitReviewModal = async () => {
    if (!reviewRecord) return;
    const runId = latestRunId || reviewRecord.run_id || "";
    setReviewSubmitting(true);
    setError("");
    try {
      const values = await reviewForm.validateFields();
      const rawAction = values.review_action;
      const mappedAction = rawAction;
      const payload = {
        dataset_name: reviewRecord.dataset_name,
        detection_run_id: runId,
        reviewer_action: mappedAction,
        reviewer_note: values.reviewer_note || "",
      };
      const approvedDomain = (values.approved_domain || "").trim();
      if (approvedDomain) payload.approved_domain = approvedDomain;
      const candidateName = (values.candidate_domain_name || "").trim();
      if (candidateName) payload.candidate_domain_name = candidateName;

      const res = await axios.post(`${API_BASE}/api/datamesh/domain-review/decision`, payload);
      const status = res?.data?.decision_status || "";
      setSuccessMessage(status ? `Decision recorded: ${status}.` : "Decision recorded.");
      setReviewModalOpen(false);
      reviewForm.resetFields();
      await Promise.all([loadResults(), refreshAux()]);
    } catch (err) {
      if (err?.errorFields || err?.name === "ValidationError") return;
      setError(err?.response?.data?.detail || "Review submission failed.");
    } finally {
      setReviewSubmitting(false);
    }
  };

  const applyToDomainProduct = async (record) => {
    const passportId = record?.admission_passport?.passport_id;
    const ds = record?.dataset_name;
    const domain = record?.target_domain_for_load || record?.best_domain;
    if (!passportId || !ds || !domain) {
      setError("Missing passport or domain for materialization.");
      return;
    }
    setApplyingKey(record.key);
    setError("");
    try {
      const res = await axios.post(`${API_BASE}/api/datamesh/domain-admission/apply`, {
        passport_id: passportId,
        dataset_name: ds,
        target_domain: domain,
      });
      setSuccessMessage(res?.data?.message || "Dataset materialized into domain product.");
      await Promise.all([loadResults(), loadMaterializations()]);
    } catch (err) {
      setError(err?.response?.data?.detail || "Materialization failed.");
    } finally {
      setApplyingKey(null);
    }
  };

  const latestDecisionByDataset = useMemo(() => {
    const sorted = [...(reviewDecisions || [])].sort((a, b) =>
      String(b.timestamp || "").localeCompare(String(a.timestamp || ""))
    );
    const m = new Map();
    sorted.forEach((d) => {
      const ds = d.dataset_name;
      if (ds && !m.has(ds)) m.set(ds, d);
    });
    return m;
  }, [reviewDecisions]);

  const enrichedRows = useMemo(
    () =>
      resultRows.map((row, index) => {
        const admissionRaw = String(row.admission_decision || row.action || "");
        const latestDecision = latestDecisionByDataset.get(row.dataset_name);
        let admissionStatus =
          row.dataset_origin === "CORE"
            ? "Known domain dataset"
            : ADMISSION_STATUS_LABELS[admissionRaw] || "Review required";
        let targetDomainForLoad = String(row.best_domain || "");

        const decisionStatus = String(latestDecision?.decision_status || "");
        if (decisionStatus === "APPROVED" || decisionStatus === "CHANGED" || decisionStatus === "DOMAIN_CREATED") {
          admissionStatus = "Ready to load";
          targetDomainForLoad = String(latestDecision?.approved_domain || latestDecision?.candidate_domain_name || row.best_domain || "");
        } else if (decisionStatus === "ORPHAN_CANDIDATE") {
          admissionStatus = "Orphan candidate";
        } else if (decisionStatus === "TICKET_OPENED") {
          admissionStatus = "Ticket Opened";
        } else if (decisionStatus === "REJECTED") {
          admissionStatus = "Rejected";
        }

        const materializationStatus = MATERIALIZATION_STATUS_LABELS[row.loading_status] || "Not loaded";
        if (materializationStatus === "Loaded to domain product") {
          admissionStatus = "Loaded";
        }

        const isReady = admissionStatus === "Ready to load" && row.dataset_origin !== "CORE";
        return {
          ...row,
          key: `${row.run_id || "run"}-${row.dataset_name || "dataset"}-${index}`,
          admission_status_ui: admissionStatus,
          materialization_status_ui: materializationStatus,
          target_domain_for_load: targetDomainForLoad,
          can_materialize_ui: isReady && Boolean(targetDomainForLoad),
        };
      }),
    [resultRows, latestDecisionByDataset]
  );

  const groupedResults = useMemo(() => {
    const existing = enrichedRows.filter((r) => r.admission_status_ui === "Known domain dataset");
    const ready = enrichedRows.filter((r) => r.admission_status_ui === "Ready to load" && r.dataset_origin !== "CORE");
    const reviewRequired = enrichedRows.filter((r) => r.admission_status_ui === "Review required");
    const orphanCandidates = enrichedRows.filter((r) => ["Orphan candidate", "Ticket required", "Ticket Opened"].includes(r.admission_status_ui));
    return { existing, ready, reviewRequired, orphanCandidates };
  }, [enrichedRows]);

  const gatewaySummary = useMemo(() => {
    return {
      silverDatasets: datasetRows.length,
      coreDatasets: datasetRows.filter((r) => String(r.dataset_origin || "").toUpperCase() === "CORE").length,
      ready: enrichedRows.filter((r) => r.admission_status_ui === "Ready to load" && r.dataset_origin !== "CORE").length,
      review: enrichedRows.filter((r) => r.admission_status_ui === "Review required").length,
      orphan: enrichedRows.filter((r) => ["Orphan candidate", "Ticket required", "Ticket Opened"].includes(r.admission_status_ui)).length,
      loadedProducts: enrichedRows.filter((r) => r.materialization_status_ui === "Loaded to domain product").length,
    };
  }, [datasetRows, enrichedRows]);

  const reviewQueueRows = useMemo(
    () => enrichedRows.filter((r) => ["Review required", "Orphan candidate", "Ticket required"].includes(r.admission_status_ui)),
    [enrichedRows]
  );

  const assessedDatasetSet = useMemo(() => new Set(enrichedRows.map((r) => r.dataset_name)), [enrichedRows]);
  const latestAssessmentByDataset = useMemo(() => {
    const m = new Map();
    enrichedRows.forEach((row) => {
      if (row?.dataset_name) m.set(row.dataset_name, row);
    });
    return m;
  }, [enrichedRows]);

  const intakeRows = useMemo(
    () =>
      datasetRows.map((item, index) => ({
        key: `${item.dataset_name || "dataset"}-${index}`,
        dataset_name: item.dataset_name || "-",
        origin:
          item.dataset_origin === "CORE" ? "Core" : item.dataset_origin === "DEMO" ? "Sample" : "Uploaded",
        rows: Number(item.row_count || 0),
        cols: Array.isArray(item.columns) ? item.columns.length : 0,
        intake_status:
          item.dataset_origin === "CORE"
            ? "Core dataset"
            : assessedDatasetSet.has(item.dataset_name)
            ? "Assessed"
            : "Awaiting assessment",
        core_validation: (() => {
          if (item.dataset_origin !== "CORE") return "-";
          const assessed = latestAssessmentByDataset.get(item.dataset_name);
          if (!assessed) return "-";
          const expectedDomain = CORE_EXPECTED_DOMAIN[item.dataset_name];
          const suggested = String(assessed.best_domain || "").toLowerCase();
          const gate = String(assessed.contract_gate || "").toUpperCase();
          if (expectedDomain && suggested === expectedDomain.toLowerCase() && gate === "PASSED") {
            return "Passed";
          }
          return "Warning";
        })(),
        core_validation_reason: (() => {
          if (item.dataset_origin !== "CORE") return "";
          const assessed = latestAssessmentByDataset.get(item.dataset_name);
          if (!assessed) return "";
          const expectedDomain = CORE_EXPECTED_DOMAIN[item.dataset_name];
          const suggested = String(assessed.best_domain || "").toLowerCase();
          const gate = String(assessed.contract_gate || "").toUpperCase();
          if (expectedDomain && suggested === expectedDomain.toLowerCase() && gate === "PASSED") return "";
          return "Core dataset does not match expected domain profile.";
        })(),
      })),
    [datasetRows, assessedDatasetSet, latestAssessmentByDataset]
  );

  const memoryRows = useMemo(
    () =>
      (memoryBank.entries || []).map((entry, i) => ({
        key: `${entry.memory_id || "memory"}-${i}`,
        dataset_name: entry.dataset_name || "-",
        domain: entry.approved_domain || entry.domain_name || "-",
        decision: entry.reviewer_action || "-",
        timestamp: entry.timestamp || "-",
      })),
    [memoryBank.entries]
  );

  const loadedProductRows = useMemo(
    () =>
      (materializationRows || [])
        .filter((r) => !CORE_DATASETS.has(String(r.dataset_name || "").toLowerCase()))
        .map((r, i) => ({ ...r, key: `${r.materialization_id || "mat"}-${i}` })),
    [materializationRows]
  );

  const renderNextAction = (record) => {
    if (record.can_materialize_ui) {
      return (
        <Button type="primary" size="small" loading={applyingKey === record.key} onClick={() => applyToDomainProduct(record)}>
          Load to Domain Product
        </Button>
      );
    }
    if (["Review required", "Orphan candidate", "Ticket required"].includes(record.admission_status_ui)) {
      return (
        <Button type="primary" size="small" onClick={() => openReviewModal(record)}>
          Review
        </Button>
      );
    }
    return <Text type="secondary">—</Text>;
  };

  const admissionTableColumns = [
    { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true, width: 180 },
    { title: "Origin", dataIndex: "dataset_origin_display", key: "origin", width: 90 },
    { title: "Suggested domain", dataIndex: "best_domain", key: "best_domain", width: 150, render: (v) => v || "—", ellipsis: true },
    { title: "Trust score", key: "trust", width: 100, render: (_, row) => pct(row.final_admission_score ?? row.confidence_score) },
    {
      title: "Admission status",
      key: "admission_status_ui",
      width: 196,
      render: (_, row) => <Tag color={admissionStatusColor(row.admission_status_ui)}>{row.admission_status_ui}</Tag>,
    },
    {
      title: "Materialization status",
      key: "materialization_status_ui",
      width: 176,
      render: (_, row) => <Tag color={materializationStatusColor(row.materialization_status_ui)}>{row.materialization_status_ui}</Tag>,
    },
    { title: "Next action", key: "next_action", width: 220, fixed: "right", render: (_, row) => renderNextAction(row) },
  ];

  const reviewQueueColumns = [
    { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", width: 180, ellipsis: true },
    { title: "Suggested domain", dataIndex: "best_domain", key: "best_domain", width: 150, ellipsis: true, render: (v) => v || "—" },
    { title: "Reason", key: "reason", render: (_, row) => row.primary_reason_code_display || row.primary_reason_code || "—", ellipsis: true },
    {
      title: "Status",
      key: "status",
      width: 170,
      render: (_, row) => <Tag color={admissionStatusColor(row.admission_status_ui)}>{row.admission_status_ui}</Tag>,
    },
    {
      title: "Action",
      key: "action",
      width: 120,
      render: (_, row) => (
        <Button type="primary" size="small" onClick={() => openReviewModal(row)}>
          Review
        </Button>
      ),
    },
  ];

  const renderAdmissionPassport = (record) => {
    const p = record.admission_passport || {};
    const semSuggested =
      record.semantic_similarity_for_suggested_domain ??
      p.semantic_similarity_for_suggested_domain ??
      record.semantic_similarity_score ??
      p.semantic_similarity_score;
    const profileText = record.dataset_profile_text || p.dataset_profile_text || "—";
    return (
      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        <Title level={5} style={{ marginTop: 0 }}>
          Admission Passport
        </Title>
        <Row gutter={[16, 12]}>
          <Col span={24}>
            <Text strong>Dataset profile text</Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, whiteSpace: "pre-wrap" }}>{profileText}</Paragraph>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Suggested domain</Text>
            <div>{record.best_domain || p.suggested_domain || "—"}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Contract fit</Text>
            <div>{pct(p.contract_coverage_score ?? record.contract_coverage_score)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Semantic/profile similarity</Text>
            <div>{pct(semSuggested)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Memory evidence</Text>
            <div>{passportMemoryLabel(record, p)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Ambiguity gap</Text>
            <div>{Number(p.ambiguity_gap ?? record.semantic_ambiguity_gap ?? 0).toFixed(3)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Reason</Text>
            <div>{record.primary_reason_code_display || record.primary_reason_code || "—"}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Recommended action</Text>
            <div>{p.recommended_action || record.recommended_action || "—"}</div>
          </Col>
          <Col xs={24}>
            <Text strong>Contract gate</Text>
            <div>
              <Tag color={contractGateColor(record.contract_gate || p.contract_gate)}>
                {record.contract_gate_display || record.contract_gate || p.contract_gate || "—"}
              </Tag>
            </div>
          </Col>
          <Col span={24}>
            <Text strong>Explanation</Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4 }}>{p.explanation || record.explanation || "—"}</Paragraph>
          </Col>
        </Row>
      </div>
    );
  };

  return (
    <div style={{ padding: 16, maxWidth: 1440, margin: "0 auto", width: "100%" }}>
      <header style={{ marginBottom: 20 }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          Semantic Domain Admission Console
        </Title>
        <Paragraph style={{ marginBottom: 0, color: "#64748b", fontSize: 15, maxWidth: 980 }}>
          Assess Silver-layer datasets against Data Mesh domain profiles before loading them into domain products.
        </Paragraph>
      </header>

      <Card title="Operational Summary" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {[
            { label: "Silver datasets", value: gatewaySummary.silverDatasets },
            { label: "Core datasets", value: gatewaySummary.coreDatasets },
            { label: "Ready to load", value: gatewaySummary.ready },
            { label: "Review required", value: gatewaySummary.review },
            { label: "Orphan candidates", value: gatewaySummary.orphan },
            { label: "Loaded products", value: gatewaySummary.loadedProducts },
          ].map((kpi) => (
            <Col key={kpi.label} xs={12} sm={8} md={8} lg={4}>
              <Card size="small" styles={{ body: { padding: "10px 12px" } }}>
                <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.04em" }}>{kpi.label}</div>
                <div style={{ fontSize: 24, fontWeight: 600, color: "#0f172a", marginTop: 4 }}>{kpi.value}</div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card
        title="Silver Dataset Intake"
        extra={
          <Button type="primary" loading={runningDetection} onClick={runDetection}>
            Run Admission Assessment
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text strong>Upload CSV</Text>
            <Paragraph type="secondary" style={{ marginBottom: 8, marginTop: 4, fontSize: 13 }}>
              Register a new Silver-layer CSV for admission assessment.
            </Paragraph>
            <Space wrap align="center">
              <Upload
                accept=".csv"
                maxCount={1}
                beforeUpload={(file) => {
                  setSelectedUploadFile(file);
                  return false;
                }}
                onRemove={() => setSelectedUploadFile(null)}
                fileList={selectedUploadFile ? [selectedUploadFile] : []}
              >
                <Button>Select CSV</Button>
              </Upload>
              <Button type="primary" loading={uploading} onClick={uploadDataset}>
                Upload CSV
              </Button>
            </Space>
          </div>
          <div>
            <Button danger loading={resettingDemo} onClick={resetDemoState}>
              Restore Core Silver State
            </Button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <Table
              size="small"
              rowKey="key"
              dataSource={intakeRows}
              loading={loadingDatasets}
              pagination={{ pageSize: 8 }}
              columns={[
                { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true },
                { title: "Origin", dataIndex: "origin", key: "origin", width: 100 },
                { title: "Rows", dataIndex: "rows", key: "rows", width: 90 },
                { title: "Columns", dataIndex: "cols", key: "cols", width: 90 },
                { title: "Status", dataIndex: "intake_status", key: "intake_status", width: 170 },
                {
                  title: "Core validation",
                  key: "core_validation",
                  width: 170,
                  render: (_, row) => {
                    if (row.core_validation === "-") return "-";
                    if (row.core_validation === "Passed") return <Tag color="green">Passed</Tag>;
                    return (
                      <div>
                        <Tag color="orange">Warning</Tag>
                        {row.core_validation_reason ? (
                          <div style={{ fontSize: 11, color: "#92400e", marginTop: 2 }}>{row.core_validation_reason}</div>
                        ) : null}
                      </div>
                    );
                  },
                },
              ]}
            />
          </div>
        </Space>
      </Card>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
      {successMessage ? <Alert type="success" showIcon message={successMessage} style={{ marginBottom: 16 }} /> : null}

      <Card title="Semantic Admission Results" style={{ marginBottom: 16 }}>
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          Admission status determines whether a dataset can proceed to domain product materialization. Materialization status indicates whether the
          dataset has actually been copied into a domain product.
        </Paragraph>
        <Tabs
          size="small"
          items={[
            {
              key: "existing",
              label: `Known Domain Datasets (${groupedResults.existing.length})`,
              children:
                groupedResults.existing.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.existing} loading={loadingResults} pagination={false} scroll={{ x: 1120 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No known domain datasets in latest run." />
                ),
            },
            {
              key: "ready",
              label: `Ready to Load (${groupedResults.ready.length})`,
              children:
                groupedResults.ready.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.ready} loading={loadingResults} pagination={false} scroll={{ x: 1120 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No datasets currently ready to load." />
                ),
            },
            {
              key: "review",
              label: `Review Required (${groupedResults.reviewRequired.length})`,
              children:
                groupedResults.reviewRequired.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.reviewRequired} loading={loadingResults} pagination={false} scroll={{ x: 1120 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No review-required datasets in latest run." />
                ),
            },
            {
              key: "orphan",
              label: `Orphan Domain Candidates (${groupedResults.orphanCandidates.length})`,
              children:
                groupedResults.orphanCandidates.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.orphanCandidates} loading={loadingResults} pagination={false} scroll={{ x: 1120 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No orphan domain candidates in latest run." />
                ),
            },
          ]}
        />
      </Card>

      <Card title="Admission Passport" style={{ marginBottom: 16 }}>
        {selectedPassportRow ? (
          <>
            <Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 10 }}>
              Semantic profile generated from filename, column names, data types, and safe sample summaries.
            </Paragraph>
            {renderAdmissionPassport(selectedPassportRow)}
          </>
        ) : (
          <Empty description="Select a dataset to inspect its admission passport." />
        )}
      </Card>

      <Card title="Review Queue" style={{ marginBottom: 16 }}>
        {reviewQueueRows.length === 0 ? (
          <Empty description="No datasets currently require review." />
        ) : (
          <Table rowKey="key" size="small" dataSource={reviewQueueRows} loading={loadingResults} pagination={{ pageSize: 8 }} scroll={{ x: 1080 }} columns={reviewQueueColumns} />
        )}
      </Card>

      <Card title="Domain Product Loading" style={{ marginBottom: 16 }}>
        {loadedProductRows.length === 0 ? (
          <Empty description="No datasets have been loaded through this console yet." />
        ) : (
          <Table
            rowKey="key"
            size="small"
            dataSource={loadedProductRows}
            pagination={{ pageSize: 8 }}
            scroll={{ x: 1080 }}
            columns={[
              { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true },
              { title: "Target domain", dataIndex: "target_domain", key: "target_domain", width: 180 },
              { title: "Target path", dataIndex: "target_path", key: "target_path", ellipsis: true },
              { title: "Load status", dataIndex: "loading_status", key: "loading_status", width: 170, render: (v) => <Tag color={materializationStatusColor(MATERIALIZATION_STATUS_LABELS[v] || v)}>{MATERIALIZATION_STATUS_LABELS[v] || v}</Tag> },
              { title: "Time", dataIndex: "timestamp", key: "timestamp", width: 160, render: formatTimeShort },
            ]}
          />
        )}
      </Card>

      <Card title="Reviewer Feedback Memory" style={{ marginBottom: 16 }}>
        <Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 12 }}>
          Approved and rejected domain admission decisions are stored as feedback to support future similar datasets.
        </Paragraph>
        {memoryRows.length === 0 ? (
          <Empty description="No reviewer feedback has been recorded yet." />
        ) : (
          <Table
            rowKey="key"
            size="small"
            dataSource={memoryRows}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: "Source dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true },
              { title: "Approved/rejected domain", dataIndex: "domain", key: "domain", ellipsis: true },
              { title: "Decision", dataIndex: "decision", key: "decision", width: 220 },
              { title: "Time", dataIndex: "timestamp", key: "timestamp", width: 170, render: formatTimeShort },
            ]}
          />
        )}
      </Card>

      <Collapse
        style={{ marginBottom: 16 }}
        items={[
          {
            key: "admin",
            label: "System State Controls",
            children: (
              <Space direction="vertical" size={10}>
                <Text strong style={{ fontSize: 13 }}>
                  Test / Admin Controls
                </Text>
                <Space wrap align="center">
                  <Select
                    style={{ minWidth: 260 }}
                    loading={loadingDemoList}
                    placeholder={demoFileNames.length ? "Select sample CSV" : "No sample files available"}
                    options={demoFileNames.map((f) => ({ label: f, value: f }))}
                    value={selectedDemoFile}
                    onChange={setSelectedDemoFile}
                    allowClear
                    showSearch
                    optionFilterProp="value"
                  />
                  <Button type="primary" ghost loading={loadingDemoCopy} onClick={loadDemoDataset} disabled={!selectedDemoFile}>
                    Load selected sample
                  </Button>
                </Space>
                <Button danger loading={resettingDemo} onClick={resetDemoState}>
                  Restore Core Silver State
                </Button>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Restores the Silver layer to canonical datasets and clears temporary sample/uploaded admission artifacts.
                </Text>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={
          reviewRecord
            ? `Domain admission review — ${String(watchedReviewAction || "").replace(/_/g, " ")} — ${reviewRecord.dataset_name}`
            : "Domain admission review"
        }
        open={reviewModalOpen}
        onCancel={() => {
          setReviewModalOpen(false);
          reviewForm.resetFields();
        }}
        onOk={submitReviewModal}
        confirmLoading={reviewSubmitting}
        destroyOnClose
        width={560}
      >
        <Form form={reviewForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="review_action" label="Action" rules={[{ required: true, message: "Select a review action." }]}>
            <Select placeholder="Choose action" options={reviewRecord ? reviewActionSelectOptions(reviewRecord) : []} />
          </Form.Item>
          <Form.Item
            name="reviewer_note"
            label="Reviewer note"
            rules={[{ required: true, message: "A reviewer note is required for domain review." }]}
          >
            <Input.TextArea rows={4} placeholder="Decision rationale, caveats, and follow-up." />
          </Form.Item>
          {watchedReviewAction === "CHANGE_DOMAIN" ? (
            <Form.Item name="approved_domain" label="Approved domain" rules={[{ required: true, message: "Provide target domain." }]}>
              <Input placeholder="sales_domain" />
            </Form.Item>
          ) : null}
          {watchedReviewAction === "CREATE_DOMAIN_AFTER_APPROVAL" ? (
            <Form.Item
              name="candidate_domain_name"
              label="Candidate domain name"
              rules={[{ required: true, message: "Provide candidate domain name." }]}
            >
              <Input placeholder="candidate_supplier_domain" />
            </Form.Item>
          ) : null}
          {watchedReviewAction !== "CHANGE_DOMAIN" && watchedReviewAction !== "CREATE_DOMAIN_AFTER_APPROVAL" ? (
            <Form.Item name="approved_domain" label="Approved domain (optional override)">
              <Input placeholder={reviewRecord?.best_domain || ""} />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
}
