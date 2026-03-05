"""Conversational monitoring assistant for Data Mesh pipelines.

This agent combines:
- Structured pipeline metadata context from execution logs
- Lightweight tokenization + embedding similarity for intent routing
- Gemini LLM responses for flexible natural-language queries
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional, Tuple

import requests


class PipelineConversationalAgent:
    """LLM-backed conversational assistant for pipeline monitoring."""

    def __init__(
        self,
        data_root: Optional[Path] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-1.5-flash",
        rerun_trigger: Optional[Callable[[], Dict[str, object]]] = None,
        rerun_status_provider: Optional[Callable[[], Dict[str, object]]] = None,
        rerun_authorizer: Optional[Callable[[str, str, str, str, str], bool]] = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.data_root = data_root or (base_dir / "data")
        self.log_path = self.data_root / "monitoring" / "logs" / "pipeline_log.json"
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = gemini_model
        self.ollama_model = os.getenv("OLLAMA_MODEL", "")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.rerun_trigger = rerun_trigger
        self.rerun_status_provider = rerun_status_provider
        self.rerun_authorizer = rerun_authorizer

        self._token_dim = 256
        self._pipeline_keywords = {
            "pipeline",
            "run",
            "runs",
            "job",
            "jobs",
            "domain",
            "domains",
            "status",
            "failed",
            "failure",
            "slowest",
            "latency",
            "duration",
            "execution",
            "rows",
            "processed",
            "monitor",
            "monitoring",
            "etl",
            "ingest",
            "summary",
            "anomaly",
            "alerts",
            "snapshot",
            "info",
            "latest",
            "fastest",
            "performance",
            "health",
        }
        self._greeting_tokens = {"hi", "hello", "hey", "yo", "hola", "sup", "morning", "afternoon", "evening"}
        self._gratitude_tokens = {"thanks", "thank", "thx", "appreciate", "grateful"}
        self._farewell_tokens = {"bye", "goodbye", "cya", "later", "farewell", "see", "soon"}
        self._ack_tokens = {"ok", "okay", "yes", "sure", "alright", "fine", "got", "it", "cool"}
        self._confirmation_tokens = {
            "yes",
            "yeah",
            "yep",
            "sure",
            "ok",
            "okay",
            "please",
            "go",
            "ahead",
            "do",
            "it",
        }
        self._response_cursor: Dict[str, int] = {}
        self._session_state: Dict[str, Dict[str, str]] = {}
        self._smalltalk_responses = {
            "greeting": [
                "Hi there. I can help with pipeline run summaries, failures, slowest pipelines, and execution timing.",
                "Hello. I’m your pipeline monitoring assistant—ask me about latest run status, alerts, or anomalies.",
                "Hey. I can quickly summarize pipeline health, failed domains, rows processed, and run durations.",
            ],
            "gratitude": [
                "You’re welcome.",
                "Happy to help.",
                "Anytime.",
            ],
            "acknowledgement": [
                "Got it.",
                "Okay.",
                "Understood.",
            ],
            "farewell": [
                "Bye. I’m here whenever you need a pipeline monitoring update.",
                "See you. Come back anytime for run status, failures, or performance checks.",
                "Goodbye. I can help again when you need a quick pipeline snapshot.",
            ],
            "out_of_scope": [
                "I’m focused on Data Mesh pipeline monitoring. Ask about run status, failures, slowest pipelines, or alerts.",
                "I can best help with pipeline monitoring questions—try asking for a latest run summary or failed domains.",
                "I’m specialized for monitoring pipelines. You can ask about execution time, rows processed, and anomalies.",
            ],
        }

        self._synonyms = {
            "pipelines": "pipeline",
            "jobs": "job",
            "running": "run",
            "executed": "execution",
            "executions": "execution",
            "failed": "failure",
            "errors": "error",
            "records": "rows",
            "row": "rows",
            "today's": "today",
            "todays": "today",
            "latest": "recent",
        }

        self._intent_examples = {
            "latest_summary": [
                "how did todays pipelines run",
                "give me a summary of latest runs",
                "pipeline status summary",
                "how is the latest run",
            ],
            "failed_pipeline": [
                "which pipeline failed",
                "show failures",
                "any failed domain",
                "failed jobs in latest run",
            ],
            "slowest_pipeline": [
                "what is the slowest pipeline",
                "which job took longest",
                "highest execution time",
                "slow pipeline",
            ],
            "fastest_pipeline": [
                "what is the fastest pipeline",
                "which pipeline finished first",
                "lowest execution time",
                "quickest job",
                "fastest run",
                "which pipeline was fastest",
            ],
            "execution_time": [
                "what was execution time",
                "pipeline duration",
                "how long did run take",
            ],
            "rows_processed": [
                "how many rows processed",
                "records processed in latest run",
                "rows count",
            ],
            "alerts_summary": [
                "what alerts do we have",
                "show anomalies",
                "any monitoring alert",
                "alert summary",
            ],
            "rerun_pipeline": [
                "rerun pipeline",
                "restart todays pipeline",
                "trigger reload",
                "run pipeline again",
                "start pipeline rerun",
            ],
            "rerun_status": [
                "rerun status",
                "is rerun done",
                "pipeline rerun update",
                "show rerun progress",
            ],
        }

        self._non_monitoring_examples = [
            "hi",
            "hello",
            "what is your name",
            "tell me a joke",
            "weather today",
            "help with fashion",
        ]
        self._fallback_prompts = [
            "You can ask for a latest run snapshot, failed pipelines, slowest or fastest pipeline, or execution timings.",
            "Try asking: latest run summary, failures, alerts, rows processed, or fastest/slowest pipeline.",
            "Ask about pipeline status, anomalies, run duration, row counts, or a full monitoring summary.",
        ]

    def load_logs(self) -> List[Dict[str, object]]:
        """Load pipeline logs from JSON."""
        if not self.log_path.exists():
            return []
        content = self.log_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def build_context(self) -> Dict[str, object]:
        """Build structured monitoring context for LLM and fallback responder."""
        logs = self.load_logs()
        runs = self._aggregate_runs(logs)

        if not runs:
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "run_count": 0,
                "latest_run": None,
                "latest_runs": [],
                "pipeline_latest": {},
                "alerts": ["No pipeline runs found in monitoring logs."],
            }

        latest_run = runs[-1]
        latest_runs = runs[-5:]
        pipeline_latest = self._latest_by_pipeline(logs)
        slowest = self._slowest_pipeline(latest_run["pipelines"]) if latest_run.get("pipelines") else None

        alerts: List[str] = []
        if latest_run["failed_pipelines"]:
            alerts.append(
                f"Latest run has failures in: {', '.join(latest_run['failed_pipelines'])}."
            )
        if slowest and slowest.get("execution_time_seconds", 0) > 60:
            alerts.append(
                f"Slowest pipeline is {slowest['pipeline_name']} at {slowest['execution_time_seconds']:.2f}s."
            )
        if not alerts:
            alerts.append("No critical alerts in the latest run.")

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "run_count": len(runs),
            "latest_run": {
                "run_id": latest_run["run_id"],
                "timestamp": latest_run["timestamp"],
                "status": latest_run["status"],
                "pipelines_total": latest_run["pipelines_total"],
                "pipelines_success": latest_run["pipelines_success"],
                "pipelines_failed": len(latest_run["failed_pipelines"]),
                "failed_pipelines": latest_run["failed_pipelines"],
                "rows_processed": latest_run["rows_processed"],
                "execution_time_seconds": latest_run["execution_time_seconds"],
                "slowest_pipeline": slowest,
            },
            "latest_runs": [
                {
                    "run_id": item["run_id"],
                    "timestamp": item["timestamp"],
                    "status": item["status"],
                    "rows_processed": item["rows_processed"],
                    "execution_time_seconds": item["execution_time_seconds"],
                    "pipelines_failed": len(item["failed_pipelines"]),
                }
                for item in latest_runs
            ],
            "pipeline_latest": pipeline_latest,
            "alerts": alerts,
        }

    def pipeline_status_snapshot(self) -> Dict[str, Dict[str, object]]:
        """Return latest status per pipeline/domain for dashboard cards."""
        logs = self.load_logs()
        latest_by_pipeline = self._latest_by_pipeline(logs)
        response: Dict[str, Dict[str, object]] = {}

        for pipeline_name, item in latest_by_pipeline.items():
            status_upper = str(item.get("status", "UNKNOWN")).upper()
            if status_upper == "SUCCESS":
                status = "success"
            elif status_upper == "FAILED":
                status = "failed"
            else:
                status = "delayed"

            response[pipeline_name] = {
                "last_run": item.get("timestamp"),
                "status": status,
                "duration": float(item.get("execution_time_seconds", 0.0) or 0.0),
                "error": item.get("error"),
                "rows_processed": int(item.get("rows_processed", 0) or 0),
                "pipeline_name": pipeline_name,
                "domain": pipeline_name,
            }

        return response

    def answer(
        self,
        question: str,
        session_id: str = "default",
        user_id: str = "",
        auth_token: str = "",
        auth_username: str = "",
        auth_password: str = "",
    ) -> Dict[str, object]:
        """Return conversational answer using embeddings + LLM."""
        cleaned = (question or "").strip()
        if not cleaned:
            return {
                "answer": "Please ask a pipeline monitoring question, for example: 'How did today's pipelines run?'",
                "intent": "empty",
                "used_llm": False,
            }

        state = self._session_state.setdefault(session_id, {})

        if self._is_confirmation(cleaned):
            pending_intent = state.get("pending_intent")
            if pending_intent:
                context = self.build_context()
                state.pop("pending_intent", None)
                state["last_intent"] = pending_intent
                return {
                    "answer": self._generate_fallback_answer(pending_intent, context),
                    "intent": f"confirm_{pending_intent}",
                    "confidence": 1.0,
                    "used_llm": False,
                    "context": context,
                }
            return {
                "answer": self._next_smalltalk_response("acknowledgement"),
                "intent": "acknowledgement",
                "confidence": 1.0,
                "used_llm": False,
            }

        smalltalk_intent = self._classify_smalltalk(cleaned)
        if smalltalk_intent:
            if smalltalk_intent == "farewell":
                state.pop("pending_intent", None)
            else:
                state.pop("pending_intent", None)
            return {
                "answer": self._next_smalltalk_response(smalltalk_intent),
                "intent": smalltalk_intent,
                "confidence": 1.0,
                "used_llm": False,
            }

        context = self.build_context()
        intent, confidence = self._classify_intent(cleaned)
        pipeline_related = self._is_pipeline_related(cleaned, intent, confidence)

        if intent == "rerun_pipeline":
            if not self._is_rerun_authorized(
                session_id=session_id,
                user_id=user_id,
                auth_token=auth_token,
                auth_username=auth_username,
                auth_password=auth_password,
            ):
                return {
                    "answer": (
                        "You are not authorized to rerun pipelines. "
                        "Please provide valid rerun credentials to continue."
                    ),
                    "intent": "rerun_pipeline_denied",
                    "confidence": round(confidence, 3),
                    "used_llm": False,
                }

            if not self.rerun_trigger:
                return {
                    "answer": "Pipeline rerun trigger is not configured on this service.",
                    "intent": "rerun_pipeline_unavailable",
                    "confidence": round(confidence, 3),
                    "used_llm": False,
                }

            trigger_result = self.rerun_trigger()
            trigger_status = str(trigger_result.get("status", "")).lower()

            if trigger_status == "started":
                state["pending_intent"] = "rerun_status"
                state["last_intent"] = "rerun_pipeline"
                return {
                    "answer": "Pipeline rerun started! I can share progress if you ask for rerun status.",
                    "intent": "rerun_pipeline",
                    "confidence": round(confidence, 3),
                    "used_llm": False,
                    "rerun": trigger_result,
                }

            if trigger_status == "already_running":
                return {
                    "answer": "A pipeline rerun is already in progress. Ask for rerun status to get live progress.",
                    "intent": "rerun_pipeline",
                    "confidence": round(confidence, 3),
                    "used_llm": False,
                    "rerun": trigger_result,
                }

            return {
                "answer": "Unable to start pipeline rerun at the moment.",
                "intent": "rerun_pipeline_error",
                "confidence": round(confidence, 3),
                "used_llm": False,
                "rerun": trigger_result,
            }

        if intent == "rerun_status":
            rerun_state = self.rerun_status_provider() if self.rerun_status_provider else {"status": "unknown"}
            return {
                "answer": self._format_rerun_status(rerun_state),
                "intent": "rerun_status",
                "confidence": round(confidence, 3),
                "used_llm": False,
                "rerun": rerun_state,
            }

        if not pipeline_related:
            return {
                "answer": self._dynamic_out_of_scope_guidance(),
                "intent": "out_of_scope",
                "confidence": round(confidence, 3),
                "used_llm": False,
            }

        state.pop("pending_intent", None)
        state["last_intent"] = intent

        llm_answer = self._generate_llm_response(cleaned, context)
        if llm_answer:
            return {
                "answer": llm_answer,
                "intent": intent,
                "confidence": round(confidence, 3),
                "used_llm": True,
                "context": context,
            }

        return {
            "answer": self._generate_fallback_answer(intent, context),
            "intent": intent,
            "confidence": round(confidence, 3),
            "used_llm": False,
            "context": context,
        }

    def _aggregate_runs(self, logs: List[Dict[str, object]]) -> List[Dict[str, object]]:
        grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for record in logs:
            run_id = str(record.get("run_id") or "")
            if not run_id:
                run_id = str(record.get("timestamp", "unknown"))[:19]
            grouped[run_id].append(record)

        runs: List[Dict[str, object]] = []
        for run_id, records in grouped.items():
            pipelines_total = len(records)
            pipelines_success = sum(1 for item in records if str(item.get("status", "")).upper() == "SUCCESS")
            failed_pipelines = [
                str(item.get("domain", "unknown"))
                for item in records
                if str(item.get("status", "")).upper() != "SUCCESS"
            ]
            rows_processed = sum(int(item.get("rows_processed", 0) or 0) for item in records)
            execution_time_seconds = sum(float(item.get("execution_time_seconds", 0.0) or 0.0) for item in records)
            timestamp = max(str(item.get("timestamp", "")) for item in records)

            if not failed_pipelines:
                status = "SUCCESS"
            elif len(failed_pipelines) == pipelines_total:
                status = "FAILED"
            else:
                status = "PARTIAL_FAILURE"

            runs.append(
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "status": status,
                    "pipelines_total": pipelines_total,
                    "pipelines_success": pipelines_success,
                    "failed_pipelines": failed_pipelines,
                    "rows_processed": rows_processed,
                    "execution_time_seconds": round(execution_time_seconds, 4),
                    "pipelines": [
                        {
                            "pipeline_name": str(item.get("domain", "unknown")),
                            "domain": str(item.get("domain", "unknown")),
                            "status": str(item.get("status", "UNKNOWN")).upper(),
                            "rows_processed": int(item.get("rows_processed", 0) or 0),
                            "execution_time_seconds": float(item.get("execution_time_seconds", 0.0) or 0.0),
                            "start_time": item.get("start_time"),
                            "end_time": item.get("end_time"),
                            "timestamp": item.get("timestamp"),
                            "error": item.get("error"),
                        }
                        for item in records
                    ],
                }
            )

        runs.sort(key=lambda item: item.get("timestamp", ""))
        return runs

    def _latest_by_pipeline(self, logs: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
        latest: Dict[str, Dict[str, object]] = {}
        for item in logs:
            pipeline_name = str(item.get("domain", "unknown"))
            current = latest.get(pipeline_name)
            item_ts = str(item.get("timestamp", ""))
            if current is None or item_ts >= str(current.get("timestamp", "")):
                latest[pipeline_name] = {
                    "timestamp": item.get("timestamp"),
                    "status": str(item.get("status", "UNKNOWN")).upper(),
                    "rows_processed": int(item.get("rows_processed", 0) or 0),
                    "execution_time_seconds": float(item.get("execution_time_seconds", 0.0) or 0.0),
                    "error": item.get("error"),
                }
        return latest

    def _slowest_pipeline(self, pipelines: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
        if not pipelines:
            return None
        return max(pipelines, key=lambda p: float(p.get("execution_time_seconds", 0.0) or 0.0))

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r"[a-zA-Z0-9_']+", text.lower())
        normalized = [self._synonyms.get(word, word) for word in words]
        return [token for token in normalized if len(token) > 1]

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self._token_dim
        for token in self._tokenize(text):
            index = hash(token) % self._token_dim
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        return float(sum(a * b for a, b in zip(left, right)))

    def _classify_intent(self, question: str) -> Tuple[str, float]:
        q_vec = self._embed(question)
        best_intent = "latest_summary"
        best_score = 0.0

        for intent, examples in self._intent_examples.items():
            for example in examples:
                score = self._cosine_similarity(q_vec, self._embed(example))
                if score > best_score:
                    best_score = score
                    best_intent = intent

        # Suppress obvious non-monitoring chitchat
        for phrase in self._non_monitoring_examples:
            score = self._cosine_similarity(q_vec, self._embed(phrase))
            if score > 0.82:
                return "out_of_scope", score

        return best_intent, best_score

    def _is_pipeline_related(self, question: str, intent: str, confidence: float) -> bool:
        if intent == "out_of_scope":
            return False
        tokens = set(self._tokenize(question))
        if tokens and tokens.issubset(self._greeting_tokens):
            return False
        has_keyword = len(tokens.intersection(self._pipeline_keywords)) > 0
        if has_keyword:
            return True
        return confidence >= 0.45

    def _classify_smalltalk(self, question: str) -> Optional[str]:
        tokens = set(self._tokenize(question))
        if not tokens:
            return None

        if tokens.issubset(self._greeting_tokens):
            return "greeting"

        if tokens.intersection(self._gratitude_tokens):
            monitoring_tokens = tokens.intersection(self._pipeline_keywords)
            if not monitoring_tokens:
                return "gratitude"

        if tokens.issubset(self._farewell_tokens):
            return "farewell"

        if tokens.issubset(self._ack_tokens):
            return "acknowledgement"

        return None

    def _is_confirmation(self, question: str) -> bool:
        tokens = set(self._tokenize(question))
        if not tokens:
            return False
        if len(tokens.intersection(self._pipeline_keywords)) > 0:
            return False
        return tokens.issubset(self._confirmation_tokens)

    def _is_rerun_authorized(
        self,
        session_id: str,
        user_id: str,
        auth_token: str,
        auth_username: str,
        auth_password: str,
    ) -> bool:
        if not self.rerun_authorizer:
            return False
        try:
            return bool(self.rerun_authorizer(session_id, user_id, auth_token, auth_username, auth_password))
        except Exception:
            return False

    def _format_rerun_status(self, rerun_state: Dict[str, object]) -> str:
        status = str(rerun_state.get("status", "unknown")).lower()
        if status in {"idle", "unknown"}:
            return "No pipeline rerun is currently active."
        if status == "running":
            started_at = rerun_state.get("started_at") or "-"
            job_id = rerun_state.get("job_id") or "-"
            return f"Pipeline rerun is in progress (job {job_id}, started {started_at})."
        if status == "completed":
            summary = rerun_state.get("summary") or {}
            rows = summary.get("total_rows_processed", "-")
            duration = summary.get("total_execution_time_seconds", "-")
            failed = summary.get("failed_domains", []) or []
            failures_text = "none" if not failed else ", ".join(failed)
            return (
                f"Pipeline rerun completed. Rows processed: {rows}. "
                f"Execution time: {duration}s. Failed domains: {failures_text}."
            )
        if status == "failed":
            error = rerun_state.get("error") or "Unknown error"
            return f"Pipeline rerun failed: {error}"
        return "Rerun status is currently unavailable."

    def _next_smalltalk_response(self, intent: str) -> str:
        options = self._smalltalk_responses.get(intent)
        if not options:
            return "I can help with pipeline monitoring queries."
        cursor = self._response_cursor.get(intent, 0)
        response = options[cursor % len(options)]
        self._response_cursor[intent] = cursor + 1
        return response

    def _dynamic_out_of_scope_guidance(self) -> str:
        base = self._next_smalltalk_response("out_of_scope")
        cursor = self._response_cursor.get("fallback_prompts", 0)
        suggestion = self._fallback_prompts[cursor % len(self._fallback_prompts)]
        self._response_cursor["fallback_prompts"] = cursor + 1
        return f"{base} {suggestion}"

    def _generate_llm_response(self, question: str, context: Dict[str, object]) -> str:
        llm_answer = self._generate_ollama_response(question, context)
        if llm_answer:
            return llm_answer

        if not self.gemini_api_key:
            return ""

        prompt = (
            "You are a Data Mesh Pipeline Monitoring Assistant. "
            "Answer using ONLY the provided monitoring context. "
            "If context lacks data, say so clearly. "
            "Use concise monitoring style with: status summary, alerts, anomalies, and key timings. "
            "If user asks unrelated question, politely redirect to monitoring topics.\n\n"
            f"Monitoring context JSON:\n{json.dumps(context, indent=2)}\n\n"
            f"User question: {question}\n\n"
            "Respond in 4-8 lines, clear and operational."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 300,
            },
        }

        try:
            response = requests.post(
                f"{url}?key={self.gemini_api_key}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return ""
            return str(parts[0].get("text", "")).strip()
        except Exception:
            return ""

    def _generate_ollama_response(self, question: str, context: Dict[str, object]) -> str:
        if not self.ollama_model:
            return ""

        prompt = (
            "You are a pipeline monitoring assistant. "
            "Use only the given context and answer concisely with status, alerts, and key timings.\n\n"
            f"Context:\n{json.dumps(context, indent=2)}\n\n"
            f"Question: {question}\n"
            "Answer in 3-6 lines."
        )

        try:
            response = requests.post(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            text = str(data.get("response", "")).strip()
            return text
        except Exception:
            return ""

    def _generate_fallback_answer(self, intent: str, context: Dict[str, object]) -> str:
        latest = context.get("latest_run") or {}
        alerts = context.get("alerts") or []

        if not latest:
            return "No pipeline run data is available yet. Run the reload pipeline and ask again for status, failures, or execution summary."

        if intent == "failed_pipeline":
            failed = latest.get("failed_pipelines") or []
            if not failed:
                return "Latest run completed with no failed pipelines. Alert status: clear."
            return (
                f"Latest run has {len(failed)} failed pipeline(s): {', '.join(failed)}. "
                f"Primary alert: {alerts[0]}"
            )

        if intent == "slowest_pipeline":
            slowest = latest.get("slowest_pipeline") or {}
            if not slowest:
                return "No slowest pipeline could be determined from the current run data."
            return (
                f"Slowest pipeline in latest run: {slowest.get('pipeline_name')} "
                f"at {float(slowest.get('execution_time_seconds', 0.0)):.2f}s. "
                f"Status: {slowest.get('status', 'UNKNOWN')}."
            )

        if intent == "fastest_pipeline":
            fastest = self._fastest_pipeline_from_context(context)
            if not fastest:
                return "No fastest pipeline could be determined from the current run data."
            return (
                f"Fastest pipeline in latest run: {fastest.get('pipeline_name')} "
                f"at {float(fastest.get('execution_time_seconds', 0.0)):.2f}s. "
                f"Status: {fastest.get('status', 'UNKNOWN')}."
            )

        if intent == "rows_processed":
            return (
                f"Latest run processed {latest.get('rows_processed', 0)} rows across "
                f"{latest.get('pipelines_total', 0)} pipeline(s)."
            )

        if intent == "execution_time":
            return (
                f"Latest run execution time: {float(latest.get('execution_time_seconds', 0.0)):.2f}s. "
                f"Alerts: {alerts[0] if alerts else 'None'}"
            )

        if intent == "alerts_summary":
            slowest = latest.get("slowest_pipeline") or {}
            fastest = self._fastest_pipeline_from_context(context) or {}
            return (
                f"Alert summary: {alerts[0] if alerts else 'No active alerts'}. "
                f"Rows processed: {latest.get('rows_processed', 0)}. "
                f"Slowest: {slowest.get('pipeline_name', '-')}, fastest: {fastest.get('pipeline_name', '-')}."
            )

        fastest = self._fastest_pipeline_from_context(context) or {}
        slowest = latest.get("slowest_pipeline") or {}

        return (
            f"Latest run {latest.get('run_id')} status: {latest.get('status')}. "
            f"Pipelines: {latest.get('pipelines_success', 0)}/{latest.get('pipelines_total', 0)} successful, "
            f"failures: {latest.get('pipelines_failed', 0)}. "
            f"Rows: {latest.get('rows_processed', 0)}, execution: {float(latest.get('execution_time_seconds', 0.0)):.2f}s. "
            f"Fastest: {fastest.get('pipeline_name', '-')}, slowest: {slowest.get('pipeline_name', '-')}. "
            f"Alerts: {alerts[0] if alerts else 'None'}"
        )

    def _fastest_pipeline_from_context(self, context: Dict[str, object]) -> Optional[Dict[str, object]]:
        pipeline_latest = context.get("pipeline_latest") or {}
        if not pipeline_latest:
            return None
        named = []
        for pipeline_name, item in pipeline_latest.items():
            named.append(
                {
                    "pipeline_name": pipeline_name,
                    "status": item.get("status", "UNKNOWN"),
                    "execution_time_seconds": float(item.get("execution_time_seconds", 0.0) or 0.0),
                }
            )
        if not named:
            return None
        return min(named, key=lambda p: p["execution_time_seconds"])
