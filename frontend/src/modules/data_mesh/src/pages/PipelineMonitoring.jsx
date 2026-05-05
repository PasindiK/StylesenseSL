import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API_BASE } from "../config";

function nowText() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function PipelineMonitoring() {
  const [pipelineStatus, setPipelineStatus] = useState({});
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([
    {
      role: "agent",
      text: "Pipeline Monitoring Agent is online. Ask about latest run status, failures, rows processed, or execution time.",
      at: nowText(),
    },
  ]);
  const [input, setInput] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [rerunStatus, setRerunStatus] = useState({ status: "idle" });
  const [showInlineAuth, setShowInlineAuth] = useState(false);
  const [authUsername, setAuthUsername] = useState(localStorage.getItem("dm_rerun_username") || "");
  const [authPassword, setAuthPassword] = useState("");
  const [pendingRerunQuestion, setPendingRerunQuestion] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [adminUsername, setAdminUsername] = useState(
    localStorage.getItem("dm_admin_username") || localStorage.getItem("dm_rerun_username") || ""
  );
  const [adminPassword, setAdminPassword] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [adminRunning, setAdminRunning] = useState(false);
  const [adminError, setAdminError] = useState("");
  const [adminResult, setAdminResult] = useState(null);
  const messagesEndRef = useRef(null);
  const sessionIdRef = useRef(`dm-pm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
  const prevRerunStatusRef = useRef((rerunStatus?.status || "idle").toLowerCase());

  function isRerunCommand(text) {
    const q = text.toLowerCase();
    return (
      q.includes("rerun") ||
      q.includes("restart") ||
      q.includes("trigger reload") ||
      q.includes("run pipeline")
    );
  }

  async function loadRerunStatus() {
    try {
      const response = await axios.get(`${API_BASE}/pipeline-monitoring/rerun-status`);
      setRerunStatus(response?.data || { status: "idle" });
    } catch {
      setRerunStatus((prev) => prev || { status: "unknown" });
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const [pipelineRes, overviewRes] = await Promise.all([
          axios.get(`${API_BASE}/pipeline-status`),
          axios.get(`${API_BASE}/overview`),
        ]);
        if (!mounted) return;
        setPipelineStatus(pipelineRes.data || {});
        setOverview(overviewRes.data || null);
      } catch {
        if (!mounted) return;
        setPipelineStatus({});
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    const timer = setInterval(load, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    loadRerunStatus();
  }, []);

  useEffect(() => {
    if ((rerunStatus?.status || "").toLowerCase() !== "running") return undefined;
    const timer = setInterval(() => {
      loadRerunStatus();
    }, 3000);
    return () => clearInterval(timer);
  }, [rerunStatus?.status]);

  useEffect(() => {
    const cur = (rerunStatus?.status || "idle").toLowerCase();
    const prev = prevRerunStatusRef.current;
    prevRerunStatusRef.current = cur;
    if (prev === "running" && cur === "completed") {
      window.dispatchEvent(new CustomEvent("dm-data-mesh-governance-refresh"));
    }
  }, [rerunStatus?.status]);

  const metrics = useMemo(() => {
    const entries = Object.entries(pipelineStatus || {});
    const totalPipelines = entries.length;
    const failed = entries.filter(([, info]) => info?.status === "failed").length;
    const delayed = entries.filter(([, info]) => info?.status === "delayed").length;
    const success = entries.filter(([, info]) => info?.status === "success").length;
    const totalExecution = entries.reduce((acc, [, info]) => acc + Number(info?.duration || 0), 0);
    const rowsProcessed = Number(overview?.user_count || 0) + Number(overview?.product_count || 0) + Number(overview?.sales_count || 0);
    const health = failed > 0 ? "Warning" : delayed > 0 ? "Warning" : totalPipelines > 0 ? "Healthy" : "Unknown";
    return {
      totalPipelines,
      failed,
      delayed,
      success,
      totalExecution,
      rowsProcessed,
      health,
    };
  }, [pipelineStatus, overview]);

  const rerunProgressPercent = Math.max(0, Math.min(100, Number(rerunStatus?.progress_percent || 0)));
  const rerunDomainsCompleted = Number(rerunStatus?.domains_completed || 0);
  const rerunTotalDomains = Number(rerunStatus?.total_domains || 0);
  const rerunRowsProcessed = Number(rerunStatus?.rows_processed_so_far || 0);
  const rawRerunState = (rerunStatus?.status || "idle").toLowerCase();
  const rerunState = rawRerunState === "started" ? "running" : rawRerunState;
  const rerunFailedCount = (rerunStatus?.summary?.failed_domains || []).length;
  const rerunSucceededCount = Math.max(0, Number(rerunStatus?.summary?.domains_processed || 0) - rerunFailedCount);

  async function requestAgent(question, extraPayload = {}, options = {}) {
    const { captureDenied = false } = options;
    try {
      setAgentBusy(true);
      const response = await axios.post(`${API_BASE}/pipeline-monitoring/chat`, {
        question,
        session_id: sessionIdRef.current,
        user_id: localStorage.getItem("dm_user_id") || "it22893970",
        auth_token: localStorage.getItem("dm_rerun_token") || "",
        ...extraPayload,
      });
      const payload = response?.data || {};

      if (captureDenied && payload.intent === "rerun_pipeline_denied") {
        setAuthError(payload.answer || "Invalid credentials.");
        return payload;
      }

      const answer = payload.answer || "No response from monitoring agent.";
      const agentMsg = { role: "agent", text: answer, at: nowText() };
      setMessages((prev) => [...prev, agentMsg]);
      if (payload.rerun) {
        setRerunStatus(payload.rerun);
      }
      return payload;
    } catch {
      const fallback = {
        role: "agent",
        text: "Monitoring assistant is temporarily unavailable. Please try again, or ask about latest run status/failures.",
        at: nowText(),
      };
      setMessages((prev) => [...prev, fallback]);
      return {};
    } finally {
      setAgentBusy(false);
    }
  }

  async function sendQuestion(text) {
    const cleaned = text.trim();
    if (!cleaned) return;

    const userMsg = { role: "user", text: cleaned, at: nowText() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    if (isRerunCommand(cleaned)) {
      setPendingRerunQuestion(cleaned);
      setAuthError("");
      setShowInlineAuth(true);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: "Please enter rerun credentials below to continue.",
          at: nowText(),
        },
      ]);
      return;
    }

    await requestAgent(cleaned);
  }

  async function submitRerunAuth(e) {
    e.preventDefault();
    if (!pendingRerunQuestion) return;
    setAuthSubmitting(true);
    localStorage.setItem("dm_rerun_username", authUsername.trim());

    const payload = await requestAgent(
      pendingRerunQuestion,
      {
        auth_username: authUsername.trim(),
        auth_password: authPassword,
      },
      { captureDenied: true }
    );

    if (payload?.intent !== "rerun_pipeline_denied") {
      setPendingRerunQuestion("");
      setAuthPassword("");
      setAuthError("");
      setShowInlineAuth(true);
      loadRerunStatus();
    }

    setAuthSubmitting(false);
  }

  function closeInlineRerunPopup() {
    if (rerunState === "running") return;
    setShowInlineAuth(false);
    setPendingRerunQuestion("");
    setAuthPassword("");
    setAuthError("");
  }

  async function runGovernanceUploadWorkflow() {
    setAdminError("");
    setAdminResult(null);

    const username = adminUsername.trim();
    if (!username || !adminPassword) {
      setAdminError("Admin username and password are required.");
      return;
    }

    if (!uploadFile) {
      setAdminError("Please choose a CSV file to upload.");
      return;
    }

    try {
      setAdminRunning(true);
      localStorage.setItem("dm_admin_username", username);

      const formData = new FormData();
      formData.append("upload_file", uploadFile);
      formData.append("session_id", sessionIdRef.current);
      formData.append("user_id", localStorage.getItem("dm_user_id") || "it22893970");
      formData.append("auth_username", username);
      formData.append("auth_password", adminPassword);

      const response = await axios.post(
        `${API_BASE}/admin/governance-test-cases/upload-and-rerun`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

      setAdminResult(response?.data || null);
      setAdminPassword("");
      setUploadFile(null);
      await loadRerunStatus();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setAdminError(typeof detail === "string" ? detail : "Governance evaluation workflow failed.");
    } finally {
      setAdminRunning(false);
    }
  }

  return (
    <div className="dm-pm-wrap">
      <div className="dm-pm-header">
        <h2>Pipeline Monitoring</h2>
        <p>Monitor pipeline health and ask questions through the integrated chat assistant.</p>
      </div>

      <div className="dm-pm-grid">
        <div className="dm-pm-card dm-pm-stats">
          <div className="dm-pm-card-title">Live Pipeline Status</div>
          {loading ? (
            <div className="dm-pm-muted">Loading metrics...</div>
          ) : (
            <>
              <div className="dm-pm-stat-row"><span>Total Pipelines</span><strong>{metrics.totalPipelines}</strong></div>
              <div className="dm-pm-stat-row"><span>Successful</span><strong>{metrics.success}</strong></div>
              <div className="dm-pm-stat-row"><span>Failed</span><strong>{metrics.failed}</strong></div>
              <div className="dm-pm-stat-row"><span>Delayed</span><strong>{metrics.delayed}</strong></div>
              <div className="dm-pm-stat-row"><span>Exec Time (s)</span><strong>{metrics.totalExecution.toFixed(1)}</strong></div>
              <div className="dm-pm-stat-row"><span>Rows Processed</span><strong>{metrics.rowsProcessed.toLocaleString()}</strong></div>
              <div className="dm-pm-health">Health: <b>{metrics.health}</b></div>
            </>
          )}

          <div className="dm-pm-admin-box">
            <div className="dm-pm-admin-title">Governance Evaluation Test Cases</div>
            <div className="dm-pm-admin-note">
              Upload a CSV to replace the mapped active Silver dataset, rerun the existing pipeline, and refresh governance outputs.
            </div>
            <div className="dm-pm-admin-controls">
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
              <input
                value={adminUsername}
                onChange={(e) => setAdminUsername(e.target.value)}
                placeholder="Admin username"
              />
              <input
                type="password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="Admin password"
              />
              <button type="button" onClick={runGovernanceUploadWorkflow} disabled={adminRunning}>
                {adminRunning ? "Running..." : "Load Test Dataset to Silver & Rerun Pipeline"}
              </button>
            </div>
            <div className="dm-pm-admin-note">
              Target domain is identified automatically from uploaded file name or mapped dataset name.
            </div>
            {adminError ? <div className="dm-pm-admin-error">{adminError}</div> : null}

            {adminResult ? (
              <div className="dm-pm-admin-summary">
                <div><b>Uploaded File:</b> {adminResult?.uploaded_file_name || "N/A"}</div>
                <div><b>Mapped Domain:</b> {adminResult?.mapped_domain || "N/A"}</div>
                <div><b>Replaced in Silver:</b> {adminResult?.replaced_in_silver ? "Yes" : "No"}</div>
                <div><b>Pipeline Rerun:</b> {adminResult?.pipeline_rerun?.succeeded ? "Success" : "Fail"}</div>
                <div><b>Latest Governance Refresh Time:</b> {adminResult?.governance_refresh?.latest_refresh_time || "N/A"}</div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="dm-pm-card dm-pm-chat">
          <div className="dm-pm-card-title-row">
            <div className="dm-pm-card-title">Pipeline Chat Interface</div>
            <div className={`dm-pm-rerun-indicator ${(rerunStatus?.status || "idle").toLowerCase()}`}>
              Rerun Status: {(rerunStatus?.status || "idle").toUpperCase()}
            </div>
          </div>

          <div className="dm-pm-quick-actions">
            <button type="button" onClick={() => sendQuestion("How was today's pipeline run?")}>How was today's pipeline run?</button>
            <button type="button" onClick={() => sendQuestion("Did any domain fail?")}>Did any domain fail?</button>
            <button type="button" onClick={() => sendQuestion("How many records were processed?")}>How many records were processed?</button>
            <button type="button" onClick={() => sendQuestion("What was the execution time?")}>What was the execution time?</button>
          </div>

          <div className="dm-pm-messages">
            {messages.map((msg, idx) => (
              <div key={`${msg.at}-${idx}`} className={`dm-pm-msg ${msg.role}`}>
                <div className="dm-pm-msg-role">{msg.role === "user" ? "You" : "Agent"}</div>
                <div className="dm-pm-msg-text">{msg.text}</div>
                <div className="dm-pm-msg-time">{msg.at}</div>
              </div>
            ))}

            {showInlineAuth && (
              <div className="dm-pm-inline-auth">
                {Boolean(pendingRerunQuestion) ? (
                  <>
                    <div className="dm-pm-inline-auth-title">Authenticate to rerun pipeline</div>
                    <form onSubmit={submitRerunAuth}>
                      <input
                        value={authUsername}
                        onChange={(e) => setAuthUsername(e.target.value)}
                        placeholder="Username"
                        required
                      />
                      <input
                        type="password"
                        value={authPassword}
                        onChange={(e) => setAuthPassword(e.target.value)}
                        placeholder="Password"
                        required
                      />
                      {authError ? <div className="dm-pm-inline-auth-error">{authError}</div> : null}
                      {authSubmitting ? (
                        <div className="dm-pm-inline-mini-status running">
                          <span className="dm-pm-spinner dm-pm-spinner-sm" />
                          <span>Authenticating...</span>
                        </div>
                      ) : null}
                      <div className="dm-pm-inline-auth-actions">
                        <button type="button" onClick={closeInlineRerunPopup}>Cancel</button>
                        <button type="submit" disabled={authSubmitting}>{authSubmitting ? "Authorizing..." : "Authorize & Rerun"}</button>
                      </div>
                    </form>
                  </>
                ) : rerunState === "running" ? (
                  <>
                    <div className="dm-pm-inline-auth-title">Pipeline rerun in progress</div>
                    <div className="dm-pm-inline-mini-status running">
                      <span className="dm-pm-spinner dm-pm-spinner-sm" />
                      <span>Running pipeline...</span>
                    </div>
                    <div className="dm-pm-inline-rerun running">
                      <div className="dm-pm-inline-running-head">
                        <span className="dm-pm-spinner" />
                        <span>Executing rerun asynchronously...</span>
                      </div>
                      <div className="dm-pm-inline-progress-track">
                        <div className="dm-pm-inline-progress-fill" style={{ width: `${rerunProgressPercent}%` }} />
                      </div>
                      <div className="dm-pm-inline-progress-meta">
                        <span>{rerunDomainsCompleted}/{rerunTotalDomains || "?"} domains</span>
                        <span>{rerunRowsProcessed.toLocaleString()} rows</span>
                        <span>{rerunProgressPercent.toFixed(0)}%</span>
                      </div>
                      {rerunStatus?.current_domain ? (
                        <div className="dm-pm-inline-current-domain">
                          Current: {rerunStatus.current_domain} ({(rerunStatus.current_domain_status || "IN_PROGRESS").toLowerCase()})
                        </div>
                      ) : null}
                    </div>
                  </>
                ) : rerunState === "completed" && rerunStatus?.summary ? (
                  <>
                    <div className="dm-pm-inline-auth-title">Pipeline rerun completed</div>
                    <div className="dm-pm-inline-mini-status completed">
                      <span className="dm-pm-check-dot">✓</span>
                      <span>Pipeline completed</span>
                    </div>
                    <div className="dm-pm-inline-summary">
                      <div><b>Rows Processed:</b> {rerunStatus.summary.total_rows_processed}</div>
                      <div><b>Pipelines Succeeded:</b> {rerunSucceededCount}</div>
                      <div><b>Pipelines Failed:</b> {rerunFailedCount}</div>
                      <div><b>Execution Time:</b> {rerunStatus.summary.total_execution_time_seconds}s</div>
                    </div>
                    <div className="dm-pm-inline-auth-actions">
                      <button type="button" onClick={closeInlineRerunPopup}>Close</button>
                    </div>
                  </>
                ) : rerunState === "failed" ? (
                  <>
                    <div className="dm-pm-inline-auth-title">Pipeline rerun failed</div>
                    <div className="dm-pm-inline-auth-error">{rerunStatus?.error || "Unknown error"}</div>
                    <div className="dm-pm-inline-auth-actions">
                      <button type="button" onClick={closeInlineRerunPopup}>Close</button>
                    </div>
                  </>
                ) : (
                  <div className="dm-pm-inline-auth-title">Type "rerun pipeline" to start a new rerun.</div>
                )}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <form
            className="dm-pm-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              sendQuestion(input);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about failures, rows processed, execution time..."
            />
            <button type="submit" disabled={agentBusy}>{agentBusy ? "Thinking..." : "Send"}</button>
          </form>
        </div>
      </div>

    </div>
  );
}
