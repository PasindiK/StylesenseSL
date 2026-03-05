import { useEffect, useMemo, useState } from "react";
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

  function generateAnswer(question) {
    const q = question.toLowerCase();

    if (q.includes("today") || q.includes("latest") || q.includes("how was") || q.includes("pipeline run")) {
      return `Latest run summary: ${metrics.success}/${metrics.totalPipelines} pipelines successful, ${metrics.failed} failed, ${metrics.delayed} delayed. Total execution time is ${metrics.totalExecution.toFixed(1)}s. Overall health is ${metrics.health}.`;
    }
    if (q.includes("fail") || q.includes("error")) {
      return metrics.failed > 0
        ? `${metrics.failed} pipeline(s) failed in the latest cycle. Please review pipeline logs and retry failed jobs.`
        : "No pipeline failures detected in the latest cycle.";
    }
    if (q.includes("how many") || q.includes("rows") || q.includes("records")) {
      return `Estimated rows processed from current mesh overview: ${metrics.rowsProcessed.toLocaleString()} records.`;
    }
    if (q.includes("time") || q.includes("duration") || q.includes("execution")) {
      return `Total execution time for current monitored pipelines is ${metrics.totalExecution.toFixed(1)} seconds.`;
    }
    if (q.includes("health") || q.includes("status")) {
      return `Pipeline health is ${metrics.health}. Success: ${metrics.success}, Failed: ${metrics.failed}, Delayed: ${metrics.delayed}.`;
    }

    return "I can help with run status, failures, rows processed, execution time, and health summary. Try: 'How was today's pipeline run?'";
  }

  function sendQuestion(text) {
    const cleaned = text.trim();
    if (!cleaned) return;

    const userMsg = { role: "user", text: cleaned, at: nowText() };
    const agentMsg = { role: "agent", text: generateAnswer(cleaned), at: nowText() };
    setMessages((prev) => [...prev, userMsg, agentMsg]);
    setInput("");
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
        </div>

        <div className="dm-pm-card dm-pm-chat">
          <div className="dm-pm-card-title">Pipeline Chat Interface</div>

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
            <button type="submit">Send</button>
          </form>
        </div>
      </div>
    </div>
  );
}
