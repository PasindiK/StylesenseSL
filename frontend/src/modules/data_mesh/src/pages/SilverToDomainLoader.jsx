import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Collapse, Col, Empty, Form, Input, Modal, Row, Select, Space, Table, Tabs, Tag, Typography, Upload } from "antd";
import axios from "axios";
import { API_BASE } from "../config";

const { Title, Paragraph, Text } = Typography;

const ADMISSION_STATUS_LABELS = {
  AUTO_LOAD_ELIGIBLE: "Ready to load",
  AUTO_ASSIGN_CREATED_DOMAIN: "Ready to load",
  HUMAN_REVIEW_REQUIRED: "Needs review",
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

function semanticBackendUiLabel(backend) {
  const b = String(backend || "");
  if (b === "sentence_embedding") return "Sentence embedding model";
  if (b === "tfidf_fallback") return "TF-IDF fallback";
  if (b === "tfidf") return "TF-IDF profile similarity";
  return b || "—";
}

function shortEmbeddingModelId(modelId) {
  const s = String(modelId || "");
  if (!s) return "—";
  if (s.includes("MiniLM") || s.includes("miniLM")) return "all-MiniLM-L6-v2";
  const parts = s.split("/");
  return parts[parts.length - 1] || s;
}

function formatActiveWeightLine(weights, semanticBackend) {
  if (!weights || typeof weights !== "object") return "—";
  const w1 = Number(weights.w1_semantic);
  const w2 = Number(weights.w2_ontology);
  const w3 = Number(weights.w3_contract);
  const w4 = Number(weights.w4_memory);
  const l1 = semanticBackend === "sentence_embedding" ? "Embedding" : "Semantic";
  return `${l1} ${w1.toFixed(2)} | Ontology ${w2.toFixed(2)} | Contract ${w3.toFixed(2)} | Memory ${w4.toFixed(2)}`;
}

function isOrphanAssessment(row) {
  return (
    row?.admission_status_ui === "Orphan candidate" ||
    String(row?.admission_decision || row?.action || "") === "NEW_DOMAIN_CANDIDATE"
  );
}

function orphanCandidateLabel(row) {
  const c = String(row?.candidate_domain_name || "").trim();
  if (c) return c;
  const stem = String(row?.dataset_name || "")
    .replace(/\.csv$/i, "")
    .replace(/[^a-zA-Z0-9]+/g, "_");
  const tok = stem.split("_").filter(Boolean)[0];
  return tok ? `candidate_${tok}` : "—";
}

function admissionStatusColor(status) {
  if (status === "Known domain dataset") return "blue";
  if (status === "Ready to load") return "green";
  if (status === "Needs review") return "orange";
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

function domainSimilarityValue(row) {
  const p = row?.admission_passport || {};
  const direct = row?.domain_similarity_score ?? p.domain_similarity_score;
  if (direct != null && Number(direct) > 0) return Number(direct);
  const emb =
    row?.embedding_similarity ??
    p.embedding_similarity ??
    row?.embedding_similarity_for_suggested_domain ??
    p.embedding_similarity_for_suggested_domain ??
    row?.embedding_similarity_score ??
    p.embedding_similarity_score;
  const ont =
    row?.ontology_concept_match ??
    p.ontology_concept_match ??
    row?.ontology_concept_match_score ??
    p.ontology_concept_match_score ??
    row?.ontology_concept_match_for_suggested_domain ??
    p.ontology_concept_match_for_suggested_domain;
  if (emb != null && ont != null) {
    const fallback = 0.5 * Number(emb) + 0.5 * Number(ont);
    if (Number.isFinite(fallback) && fallback > 0) return fallback;
  }
  return Number(direct || 0);
}

function readinessScoreValue(row) {
  const p = row?.admission_passport || {};
  return (
    p.domain_readiness_score ??
    row?.domain_readiness_score ??
    p.final_score ??
    row?.final_score ??
    p.final_admission_score ??
    row?.final_admission_score
  );
}

function coreValidationStatus(row) {
  if (row?.dataset_origin !== "CORE") return null;
  const p = row?.admission_passport || {};
  const explicit = p.core_validation_status || row?.core_validation_status;
  if (explicit) return explicit;
  const name = String(row?.dataset_name || "").toLowerCase();
  const expected = CORE_EXPECTED_DOMAIN[name];
  if (!expected) return "WARNING";
  return String(row?.best_domain || "") === expected ? "PASSED" : "WARNING";
}

function coreValidationTag(row) {
  if (row?.dataset_origin !== "CORE") return <Text type="secondary">—</Text>;
  const s = coreValidationStatus(row);
  if (s === "PASSED") return <Tag color="green">Passed</Tag>;
  return <Tag color="orange">Warning</Tag>;
}

export default function SilverToDomainLoader() {
  const [datasetRows, setDatasetRows] = useState([]);
  const [resultRows, setResultRows] = useState([]);
  const [historyRows, setHistoryRows] = useState([]);
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
  const [lastAssessmentStack, setLastAssessmentStack] = useState(null);
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
      setHistoryRows([]);
      return;
    }
    const latestId = rows[0]?.run_id || "";
    const latest = dedupeByDataset(rows.filter((row) => row?.run_id === latestId));
    const history = rows.filter((row) => row?.run_id && row.run_id !== latestId);
    setLatestRunId(String(latestId || ""));
    setResultRows(latest);
    setHistoryRows(history);
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
      setError("Unable to load assessment results.");
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
      const stack = semanticBackendUiLabel(res?.data?.semantic_backend);
      const warn = res?.data?.semantic_scoring_warning ? ` ${String(res.data.semantic_scoring_warning)}` : "";
      setLastAssessmentStack({
        semantic_backend: res?.data?.semantic_backend,
        scoring_backend_effective: res?.data?.scoring_backend_effective,
        semantic_scoring_warning: res?.data?.semantic_scoring_warning || "",
        embedding_weights_source: res?.data?.embedding_weights_source,
        embedding_model_id: res?.data?.embedding_model_id,
        admission_score_weights: res?.data?.admission_score_weights,
      });
      setSuccessMessage(
        `Semantic domain assessment completed. Run ${runId}. Datasets evaluated: ${count}. Engine: ${stack}.${warn}`
      );
      await Promise.all([loadDatasets(), refreshAux(), loadResults()]);
    } catch (_err) {
      setError("Failed to run semantic domain assessment.");
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
      setSuccessMessage("Dataset registered in Silver. Run semantic domain assessment to classify.");
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
    const defaultApproved =
      isOrphanAssessment(record) || String(record.admission_decision || record.action) === "NEW_DOMAIN_CANDIDATE"
        ? record.candidate_domain_name || ""
        : record.best_domain || "";
    reviewForm.setFieldsValue({
      review_action: opts[0]?.value,
      reviewer_note: "",
      approved_domain: defaultApproved,
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
            : ADMISSION_STATUS_LABELS[admissionRaw] || "Needs review";
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
    const reviewRequired = enrichedRows.filter((r) => r.admission_status_ui === "Needs review");
    const orphanCandidates = enrichedRows.filter((r) => ["Orphan candidate", "Ticket required", "Ticket Opened"].includes(r.admission_status_ui));
    return { existing, ready, reviewRequired, orphanCandidates };
  }, [enrichedRows]);

  const gatewaySummary = useMemo(() => {
    return {
      silverDatasets: datasetRows.length,
      coreDatasets: datasetRows.filter((r) => String(r.dataset_origin || "").toUpperCase() === "CORE").length,
      ready: enrichedRows.filter((r) => r.admission_status_ui === "Ready to load" && r.dataset_origin !== "CORE").length,
      review: enrichedRows.filter((r) => r.admission_status_ui === "Needs review").length,
      orphan: enrichedRows.filter((r) => ["Orphan candidate", "Ticket required", "Ticket Opened"].includes(r.admission_status_ui)).length,
      loadedProducts: enrichedRows.filter((r) => r.materialization_status_ui === "Loaded to domain product").length,
    };
  }, [datasetRows, enrichedRows]);

  const assessmentStackFromRows = useMemo(() => {
    const r = resultRows[0];
    if (!r) return null;
    const p = r.admission_passport || {};
    return {
      semantic_backend: r.semantic_backend || p.semantic_backend,
      scoring_backend_effective: r.scoring_backend_effective || p.scoring_backend_effective,
      semantic_scoring_warning: r.semantic_scoring_warning || p.semantic_scoring_warning || "",
      embedding_weights_source: r.embedding_weights_source ?? p.embedding_weights_source,
      embedding_model_id: r.embedding_model_id ?? p.embedding_model_id,
      admission_score_weights: r.admission_passport?.admission_score_weights || r.admission_score_weights,
    };
  }, [resultRows]);

  const activeAssessmentStack = lastAssessmentStack || assessmentStackFromRows;

  const engineWeightSource = useMemo(() => {
    const w =
      lastAssessmentStack?.admission_score_weights ||
      resultRows[0]?.admission_passport?.admission_score_weights ||
      resultRows[0]?.admission_score_weights;
    return w;
  }, [lastAssessmentStack, resultRows]);

  const reviewQueueRows = useMemo(
    () => enrichedRows.filter((r) => ["Needs review", "Orphan candidate", "Ticket required"].includes(r.admission_status_ui)),
    [enrichedRows]
  );

  const historyAssessmentRows = useMemo(
    () =>
      historyRows.map((row, index) => {
        const admissionRaw = String(row?.admission_decision || row?.action || "");
        let admissionStatus =
          row?.dataset_origin === "CORE"
            ? "Known domain dataset"
            : ADMISSION_STATUS_LABELS[admissionRaw] || "Needs review";
        const mat = MATERIALIZATION_STATUS_LABELS[row?.loading_status] || "Not loaded";
        if (mat === "Loaded to domain product") admissionStatus = "Loaded";
        return {
          ...row,
          key: `history-${row?.run_id || "run"}-${row?.dataset_name || "dataset"}-${index}`,
          admission_status_ui: admissionStatus,
        };
      }),
    [historyRows]
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

  const renderDomainPrimaryCell = (_, row) => {
    if (isOrphanAssessment(row)) {
      const cand = orphanCandidateLabel(row);
      return (
        <div>
          <div style={{ fontSize: 12, color: "#64748b" }}>No existing domain fit</div>
          <div style={{ fontWeight: 600 }}>Candidate: {cand}</div>
        </div>
      );
    }
    return row.best_domain || "—";
  };

  const renderNextAction = (record) => {
    if (record.dataset_origin === "CORE") {
      return <Text type="secondary">—</Text>;
    }
    if (record.can_materialize_ui) {
      return (
        <Button type="primary" size="small" loading={applyingKey === record.key} onClick={() => applyToDomainProduct(record)}>
          Load to Domain Product
        </Button>
      );
    }
    if (record.admission_status_ui === "Orphan candidate") {
      return (
        <Button type="primary" size="small" onClick={() => openReviewModal(record)}>
          Review Candidate
        </Button>
      );
    }
    if (["Needs review", "Ticket required", "Ticket Opened"].includes(record.admission_status_ui)) {
      return (
        <Button type="primary" size="small" onClick={() => openReviewModal(record)}>
          Open Review
        </Button>
      );
    }
    return <Text type="secondary">—</Text>;
  };

  const admissionTableColumns = [
    { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true, width: 200 },
    { title: "Origin", dataIndex: "dataset_origin_display", key: "origin", width: 88 },
    {
      title: "Matched / Candidate domain",
      key: "domain_display",
      width: 220,
      ellipsis: true,
      render: renderDomainPrimaryCell,
    },
    {
      title: "Domain similarity",
      key: "domain_similarity",
      width: 120,
      render: (_, row) => pct(domainSimilarityValue(row)),
    },
    {
      title: "Core validation",
      key: "core_validation",
      width: 132,
      render: (_, row) => coreValidationTag(row),
    },
    {
      title: "Assessment status",
      key: "admission_status_ui",
      width: 168,
      render: (_, row) => <Tag color={admissionStatusColor(row.admission_status_ui)}>{row.admission_status_ui}</Tag>,
    },
    { title: "Next action", key: "next_action", width: 200, fixed: "right", render: (_, row) => renderNextAction(row) },
  ];

  const reviewQueueColumns = [
    { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", width: 180, ellipsis: true },
    {
      title: "Matched / Candidate domain",
      key: "domain_display",
      width: 200,
      ellipsis: true,
      render: renderDomainPrimaryCell,
    },
    { title: "Reason", key: "reason", render: (_, row) => row.primary_reason_code_display || row.primary_reason_code || "—", ellipsis: true },
    {
      title: "Assessment status",
      key: "status",
      width: 170,
      render: (_, row) => <Tag color={admissionStatusColor(row.admission_status_ui)}>{row.admission_status_ui}</Tag>,
    },
    {
      title: "Next action",
      key: "action",
      width: 140,
      render: (_, row) => renderNextAction(row),
    },
  ];

  const renderAssessmentDetails = (record) => {
    const p = record.admission_passport || {};
    const embeddingSim =
      p.embedding_similarity_for_suggested_domain ??
      record.embedding_similarity_for_suggested_domain ??
      p.embedding_similarity_score ??
      record.embedding_similarity_score ??
      p.profile_similarity_for_suggested_domain ??
      record.semantic_similarity_for_suggested_domain ??
      p.semantic_similarity_for_suggested_domain ??
      record.semantic_similarity_score ??
      p.semantic_similarity_score;
    const ontologyMatch =
      p.ontology_concept_match_score ??
      record.ontology_concept_match_score ??
      p.ontology_concept_match_for_suggested_domain ??
      record.ontology_concept_match_for_suggested_domain;
    const contractFit = p.contract_fit_score ?? record.contract_fit_score ?? p.contract_coverage_score ?? record.contract_coverage_score;
    const domainSimilarity = domainSimilarityValue(record);
    const readinessScore = readinessScoreValue(record);
    const datasetBiz = p.dataset_business_sentence || record.dataset_business_sentence || "—";
    const domainBiz = p.domain_business_sentence || record.domain_business_sentence || "—";
    const admissionMargin = p.ambiguity_gap ?? record.admission_score_ambiguity_gap;
    const profileMargin = p.profile_similarity_ambiguity_gap ?? record.semantic_ambiguity_gap;
    const orphan = isOrphanAssessment(record);
    return (
      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        <Title level={5} style={{ marginTop: 0 }}>
          Assessment Details
        </Title>
        <Row gutter={[16, 12]}>
          {orphan ? (
            <Col span={24}>
              <Text strong>Matched domain</Text>
              <Paragraph style={{ marginBottom: 4, marginTop: 4 }}>No existing domain fit</Paragraph>
              <Text strong>Candidate domain</Text>
              <Paragraph style={{ marginBottom: 0, marginTop: 4 }}>{orphanCandidateLabel(record)}</Paragraph>
            </Col>
          ) : null}
          <Col span={24}>
            <Text strong>Dataset business sentence</Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 13, whiteSpace: "pre-wrap" }}>{datasetBiz}</Paragraph>
          </Col>
          <Col span={24}>
            <Text strong>Domain business sentence</Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 13, whiteSpace: "pre-wrap" }}>{domainBiz}</Paragraph>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Embedding similarity</Text>
            <div style={{ marginTop: 4 }}>{pct(embeddingSim)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Ontology concept match</Text>
            <div style={{ marginTop: 4 }}>{ontologyMatch != null ? pct(ontologyMatch) : "—"}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Contract fit</Text>
            <div style={{ marginTop: 4 }}>{contractFit != null ? pct(contractFit) : pct(p.contract_coverage_score ?? record.contract_coverage_score)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Domain similarity score</Text>
            <div style={{ marginTop: 4 }}>{pct(domainSimilarity)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Reviewer memory</Text>
            <div style={{ marginTop: 4 }}>{passportMemoryLabel(record, p)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Readiness score</Text>
            <div style={{ marginTop: 4 }}>{pct(readinessScore)}</div>
          </Col>
          <Col xs={24} md={12}>
            <Text strong>Ambiguity gap</Text>
            <div style={{ marginTop: 4 }}>{Number(admissionMargin ?? 0).toFixed(3)}</div>
            <Text type="secondary" style={{ fontSize: 11, display: "block", marginTop: 4 }}>
              Semantic channel gap: {Number(profileMargin ?? 0).toFixed(3)}
            </Text>
          </Col>
          <Col span={24}>
            <Text strong>Explanation</Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 13 }}>{p.explanation || record.explanation || "—"}</Paragraph>
          </Col>
        </Row>
      </div>
    );
  };

  const sb = activeAssessmentStack?.semantic_backend;
  const engineHeadline =
    sb === "sentence_embedding" ? "Sentence embedding model" : sb === "tfidf_fallback" ? "TF-IDF fallback active" : sb ? semanticBackendUiLabel(sb) : "—";

  return (
    <div style={{ padding: 16, maxWidth: 1440, margin: "0 auto", width: "100%" }}>
      <header style={{ marginBottom: 20 }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          Semantic Domain Assignment Console
        </Title>
        <Paragraph style={{ marginBottom: 0, color: "#64748b", fontSize: 15, maxWidth: 900, lineHeight: 1.55 }}>
          Silver-layer datasets are converted into business meaning profiles and matched against Data Mesh domain profiles using sentence embeddings,
          ontology concepts, and contract fit.
        </Paragraph>
      </header>

      <Card size="small" bordered={false} style={{ marginBottom: 16, background: "#fafbfc", border: "1px solid #e5e7eb" }}>
        <Row gutter={[20, 12]} align="top">
          <Col xs={24} md={8}>
            <Text type="secondary" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Active semantic engine
            </Text>
            <div style={{ fontSize: 17, fontWeight: 600, color: "#0f172a", marginTop: 6 }}>{engineHeadline}</div>
            {activeAssessmentStack?.semantic_scoring_warning ? (
              <Alert type="warning" showIcon style={{ marginTop: 10, fontSize: 12 }} message={String(activeAssessmentStack.semantic_scoring_warning)} />
            ) : null}
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Model
            </Text>
            <div style={{ fontSize: 15, fontWeight: 500, marginTop: 6, color: "#334155" }}>
              {sb === "sentence_embedding" ? shortEmbeddingModelId(activeAssessmentStack?.embedding_model_id) : "—"}
            </div>
          </Col>
          <Col xs={24} md={8}>
            <Text type="secondary" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Weights
            </Text>
            <div style={{ fontSize: 13, marginTop: 6, color: "#334155", lineHeight: 1.45 }}>
              {formatActiveWeightLine(engineWeightSource, sb)}
            </div>
          </Col>
        </Row>
        {!activeAssessmentStack ? (
          <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 12, fontSize: 13 }}>
            Run a semantic domain assessment to show the active engine and weights.
          </Paragraph>
        ) : null}
      </Card>

      <Card title="Operational Summary" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {[
            { label: "Silver datasets", value: gatewaySummary.silverDatasets },
            { label: "Core datasets", value: gatewaySummary.coreDatasets },
            { label: "Ready to load", value: gatewaySummary.ready },
            { label: "Needs review", value: gatewaySummary.review },
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
            Run Semantic Domain Assessment
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text strong>Upload CSV</Text>
            <Paragraph type="secondary" style={{ marginBottom: 8, marginTop: 4, fontSize: 13 }}>
              Register a new Silver CSV for semantic domain assessment.
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

      <Card title="Semantic Domain Assessment Results" style={{ marginBottom: 16 }}>
        <Collapse
          ghost
          items={[
            {
              key: "method",
              label: "Method details",
              children: (
                <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 13 }}>
                  Each dataset gets a business-language profile. Scoring blends semantic similarity (sentence embeddings, or TF-IDF if the model is
                  unavailable), ontology concept overlap, contract column fit, and optional reviewer memory. Open <Text strong>Assessment Details</Text>{" "}
                  on a row for full signals and explanation.
                </Paragraph>
              ),
            },
          ]}
        />
        <Tabs
          size="small"
          items={[
            {
              key: "existing",
              label: `Known Domain Datasets (${groupedResults.existing.length})`,
              children:
                groupedResults.existing.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.existing} loading={loadingResults} pagination={false} scroll={{ x: 980 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No known domain datasets in latest run." />
                ),
            },
            {
              key: "ready",
              label: `Ready to Load (${groupedResults.ready.length})`,
              children:
                groupedResults.ready.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.ready} loading={loadingResults} pagination={false} scroll={{ x: 980 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No datasets currently ready to load." />
                ),
            },
            {
              key: "review",
              label: `Needs Review (${groupedResults.reviewRequired.length})`,
              children:
                groupedResults.reviewRequired.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.reviewRequired} loading={loadingResults} pagination={false} scroll={{ x: 980 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No datasets need review in the latest run." />
                ),
            },
            {
              key: "orphan",
              label: `Orphan Candidates (${groupedResults.orphanCandidates.length})`,
              children:
                groupedResults.orphanCandidates.length > 0 ? (
                  <Table rowKey="key" size="small" dataSource={groupedResults.orphanCandidates} loading={loadingResults} pagination={false} scroll={{ x: 980 }} columns={admissionTableColumns} onRow={(r) => ({ onClick: () => setSelectedPassportRow(r), style: { cursor: "pointer" } })} />
                ) : (
                  <Empty description="No orphan domain candidates in latest run." />
                ),
            },
          ]}
        />
      </Card>

      <Card title="Assessment Details" style={{ marginBottom: 16 }}>
        {selectedPassportRow ? (
          <>
            <Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 10 }}>
              Technical breakdown for the selected dataset. Choose a row from the tables above.
            </Paragraph>
            {renderAssessmentDetails(selectedPassportRow)}
          </>
        ) : (
          <Empty description="Select a dataset row to view assessment details." />
        )}
      </Card>

      <Card title="Review Queue" style={{ marginBottom: 16 }}>
        {reviewQueueRows.length === 0 ? (
          <Empty description="No datasets currently require review." />
        ) : (
          <Table rowKey="key" size="small" dataSource={reviewQueueRows} loading={loadingResults} pagination={{ pageSize: 8 }} scroll={{ x: 1080 }} columns={reviewQueueColumns} />
        )}
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Collapse
          ghost
          items={[
            {
              key: "assessment-history",
              label: `Assessment History (${historyAssessmentRows.length})`,
              children:
                historyAssessmentRows.length > 0 ? (
                  <Table
                    rowKey="key"
                    size="small"
                    dataSource={historyAssessmentRows}
                    pagination={{ pageSize: 8 }}
                    scroll={{ x: 980 }}
                    columns={[
                      { title: "Run ID", dataIndex: "run_id", key: "run_id", width: 110 },
                      { title: "Dataset", dataIndex: "dataset_name", key: "dataset_name", ellipsis: true, width: 200 },
                      {
                        title: "Matched / Candidate domain",
                        key: "domain_display",
                        width: 220,
                        ellipsis: true,
                        render: renderDomainPrimaryCell,
                      },
                      {
                        title: "Assessment status",
                        key: "admission_status_ui",
                        width: 170,
                        render: (_, row) => <Tag color={admissionStatusColor(row.admission_status_ui)}>{row.admission_status_ui}</Tag>,
                      },
                      { title: "Time", dataIndex: "timestamp", key: "timestamp", width: 170, render: formatTimeShort },
                    ]}
                  />
                ) : (
                  <Empty description="No previous assessment records in audit history." />
                ),
            },
          ]}
        />
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
          Prior reviewer decisions are stored as memory to support similar datasets.
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
            ? `Review — ${String(watchedReviewAction || "").replace(/_/g, " ")} — ${reviewRecord.dataset_name}`
            : "Domain review"
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
