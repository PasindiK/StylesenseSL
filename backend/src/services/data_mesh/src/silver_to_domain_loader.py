from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SYSTEM_DOMAINS = frozenset(
    {
        "sales_domain",
        "users_domain",
        "product_domain",
        "shop_domain",
        "interaction_domain",
        "engagement_domain",
        "user_preferences_domain",
    }
)

# Canonical Silver CSV files retained after demo reset (allowlist — not suffix rules).
CORE_SILVER_CSV_ALLOWLIST = frozenset(
    {
        "interactions_clean.csv",
        "products_clean.csv",
        "shops_clean.csv",
        "transactions_clean.csv",
        "trends_clean.csv",
        "users_clean.csv",
        "users_preferences_clean.csv",
    }
)

# Expected domain mapping for canonical core datasets (used for UI validation messaging).
CORE_EXPECTED_DOMAIN_BY_DATASET: dict[str, str] = {
    "transactions_clean.csv": "sales_domain",
    "products_clean.csv": "product_domain",
    "users_clean.csv": "users_domain",
    "shops_clean.csv": "shop_domain",
    "interactions_clean.csv": "interaction_domain",
    "trends_clean.csv": "engagement_domain",
    "users_preferences_clean.csv": "user_preferences_domain",
}

# Human-readable labels for policy reason codes (UI / audit).
def _domain_pretty_name(domain: str | None) -> str:
    """interaction_domain -> 'Interaction'; user_preferences_domain -> 'User Preferences'."""
    if not domain:
        return "the suggested domain"
    raw = str(domain).strip()
    if raw.endswith("_domain"):
        raw = raw[: -len("_domain")]
    parts = [p for p in raw.split("_") if p]
    if not parts:
        return str(domain).strip()
    return " ".join(p.capitalize() for p in parts)


def _signal_qual_strength(value: float, hi: float = 0.55, mid: float = 0.35) -> str:
    if value >= hi:
        return "strong"
    if value >= mid:
        return "moderate"
    return "weak"


def _margin_qual(gap: float, low: float = 0.10, high: float = 0.15) -> str:
    if gap < low:
        return "low"
    if gap >= high:
        return "clear"
    return "moderate"


REASON_CODE_DISPLAY: dict[str, str] = {
    "CONTRACT_FIRST_GOVERNANCE_MATCH": "Contract-first governance match",
    "HYBRID_SCORE_AND_MARGIN_OK": "Hybrid trust score and margin OK",
    "LOW_SCORE_NEW_DOMAIN": "Low fit — new domain candidate",
    "LOW_COMPOSITE_AMBIGUOUS": "Low composite — ambiguous fit",
    "LOW_MARGIN_AMBIGUOUS": "Low leader margin — ambiguous",
    "SCORE_BAND_PROVISIONAL": "Provisional score band",
    "FALLBACK_REVIEW": "Fallback human review",
    "GOVERNANCE_RISK_HIGH": "Governance risk high",
    "NO_CONTRACTS": "No contracts available",
    "CREATED_DOMAIN_REGISTRY": "Created-domain registry routing",
}

# Business-concept keywords per domain (ontology signal — separate from contract column coverage).
# Column stems (from names like order_id → order, id) are matched against this vocabulary.
DOMAIN_ONTOLOGY_TERMS: dict[str, frozenset[str]] = {
    "sales_domain": frozenset(
        {
            "transaction",
            "order",
            "line",
            "price",
            "amount",
            "quantity",
            "payment",
            "invoice",
            "cart",
            "discount",
            "purchase",
            "revenue",
            "sku",
            "shipped",
            "tax",
            "total",
            "unit",
            "checkout",
            "refund",
            "fulfillment",
            "delivery",
        }
    ),
    "product_domain": frozenset(
        {
            "product",
            "item",
            "sku",
            "inventory",
            "category",
            "brand",
            "color",
            "size",
            "catalog",
            "vendor",
            "stock",
            "list",
            "warehouse",
            "attribute",
            "variant",
            "merchandising",
            "description",
            "style",
            "fabric",
        }
    ),
    "users_domain": frozenset(
        {
            "user",
            "customer",
            "email",
            "signup",
            "profile",
            "country",
            "loyalty",
            "tier",
            "name",
            "gender",
            "age",
            "segment",
            "location",
            "phone",
            "address",
            "account",
        }
    ),
    "shop_domain": frozenset(
        {
            "shop",
            "store",
            "branch",
            "outlet",
            "location",
            "region",
            "city",
            "district",
            "postal",
            "rating",
            "owner",
            "merchant",
            "hours",
            "opening",
            "operating",
        }
    ),
    "interaction_domain": frozenset(
        {
            "interaction",
            "click",
            "session",
            "channel",
            "dwell",
            "event",
            "event_time",
            "click_time",
            "interaction_event",
            "product_interaction",
            "view",
            "behavior",
            "activity",
            "timestamp",
            "feedback",
            "comment",
            "message",
            "rating",
            "user_id",
            "product_id",
            "interaction_type",
            "user_action",
            "action",
            "impression",
        }
    ),
    "engagement_domain": frozenset(
        {
            "trend",
            "score",
            "momentum",
            "metric",
            "rank",
            "delta",
            "engagement",
            "session",
            "visit",
            "page",
            "campaign",
            "impression",
            "dwell",
            "attention",
        }
    ),
    "user_preferences_domain": frozenset(
        {
            "preference",
            "preferred",
            "wishlist",
            "favorite",
            "rating",
            "interest",
            "style",
            "weight",
            "campaign",
            "reward",
            "personalization",
            "fabric",
            "color",
            "category",
            "brand",
            "sensitivity",
        }
    ),
}

# Alternative “shapes” that still count as strong contract alignment (OR across bundles, best wins).
REQUIRED_COVERAGE_BUNDLES: dict[str, tuple[frozenset[str], ...]] = {
    "sales_domain": (
        frozenset({"transaction_id", "user_id", "product_id", "transaction_date"}),
        frozenset({"order_id", "user_id", "product_id", "transaction_date"}),
        frozenset({"order_id", "line_id", "sku", "quantity", "unit_price"}),
        frozenset({"payment_id", "amount", "transaction_date"}),
    ),
    "product_domain": (
        frozenset({"product_id", "shop_id", "category", "price_lkr"}),
        frozenset({"product_id", "sku", "category", "stock_count"}),
        frozenset({"item_id", "sku", "brand", "stock_count"}),
    ),
    "users_domain": (
        frozenset({"user_id", "email", "signup_ts"}),
        frozenset({"customer_id", "email", "name"}),
        frozenset({"user_id", "name", "email", "phone"}),
    ),
    "shop_domain": (
        frozenset({"shop_id", "shop_name", "location"}),
        frozenset({"store_id", "branch", "city"}),
        frozenset({"shop_id", "district", "operating_hours_open"}),
    ),
    "interaction_domain": (
        frozenset({"interaction_id", "user_id", "product_id", "interaction_ts"}),
        frozenset({"click_id", "user_id", "product_id", "click_time"}),
        frozenset({"user_id", "product_id", "interaction_type", "interaction_ts"}),
        frozenset({"user_id", "product_id", "click_time"}),
        frozenset({"user_id", "interaction_type", "event_time"}),
        frozenset({"user_id", "product_id", "rating", "feedback"}),
    ),
    "engagement_domain": (
        frozenset({"trend_id", "trend_name", "trend_score"}),
        frozenset({"session_id", "page_view", "engagement_score", "event_time"}),
        frozenset({"session_id", "visit", "dwell_time", "campaign_id"}),
    ),
    "user_preferences_domain": (
        frozenset({"preference_id", "user_id", "updated_ts"}),
        frozenset({"user_id", "preferred_categories", "preferred_colors"}),
        frozenset({"wishlist_id", "user_id", "product_id"}),
    ),
}

DEFAULT_ADMISSION_SCORE_WEIGHTS: dict[str, float] = {
    "w1_semantic": 0.10,
    "w2_ontology": 0.50,
    "w3_contract": 0.40,
    "w4_memory": 0.00,
}

# Initial weights after switching w1 to sentence embeddings (re-tune with harness after validation grows).
DEFAULT_EMBEDDING_ADMISSION_WEIGHTS: dict[str, float] = {
    "w1_semantic": 0.40,
    "w2_ontology": 0.30,
    "w3_contract": 0.25,
    "w4_memory": 0.05,
}

SENTENCE_TRANSFORMER_MODEL_IDS: tuple[str, ...] = (
    "sentence-transformers/all-MiniLM-L6-v2",
    "all-MiniLM-L6-v2",
)

logger = logging.getLogger(__name__)


@dataclass
class DomainRankParts:
    domain: str
    contract_coverage_score: float
    filename_score: float
    column_score: float
    required_coverage: float
    optional_coverage: float
    matched_columns: list[str]


class SilverToDomainLoaderService:
    """
    Hybrid domain admission: sentence-embedding or TF-IDF similarity (w1), ontology concept match (w2),
    contract fit (w3), reviewer memory (w4). Weights and `scoring_backend` come from
    data/evaluation/optimal_domain_weights.json when present.
    """

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.silver_dir = self.data_root / "Data" / "Silver-data"
        self.contracts_dir = self.data_root / "Contracts"
        self.domain_products_dir = self.data_root / "Data_Mesh_Domains"
        self.logs_dir = self.data_root / "monitoring" / "logs"
        self.audit_log_path = self.logs_dir / "silver_domain_loader_audit.json"
        self.domain_memory_path = self.logs_dir / "domain_memory_bank.json"
        self.created_domain_registry_path = self.logs_dir / "created_domain_registry.json"
        self.review_decisions_path = self.logs_dir / "domain_review_decisions.json"
        self.review_tickets_path = self.logs_dir / "domain_review_tickets.json"
        self.materialization_log_path = self.logs_dir / "domain_admission_materialization.json"
        self.demo_manifest_path = self.logs_dir / "demo_loaded_files.json"
        self.test_upload_dir = self.data_root / "Data" / "Test-upload-data"
        # data_root is .../data_mesh/data (contains Data/, evaluation/, Contracts/, ...)
        self.weight_config_path = self.data_root / "evaluation" / "optimal_domain_weights.json"
        self.embedding_weight_config_path = self.data_root / "evaluation" / "optimal_embedding_domain_weights.json"
        self._sentence_transformer_model = None
        self._sentence_transformer_model_id: str | None = None
        self.embedding_model_id_config = os.getenv("EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2").strip()
        self.embedding_model_local_path = os.getenv("EMBEDDING_MODEL_LOCAL_PATH", "").strip()
        self.scoring_backend_requested = "sentence_embedding"
        self.scoring_backend_effective = "tfidf"
        self.semantic_backend = "tfidf"
        self.semantic_scoring_warning: str | None = None
        self.embedding_weights_source: str | None = None  # "file" | "default" | None when not embedding path
        self._apply_scoring_backend_and_weights()

    def _normalize_weight_dict(self, src: dict[str, Any] | None, fallback: dict[str, float]) -> dict[str, float]:
        if not isinstance(src, dict):
            return dict(fallback)
        w1 = float(src.get("w1_semantic", fallback["w1_semantic"]))
        w2 = float(src.get("w2_ontology", fallback["w2_ontology"]))
        w3 = float(src.get("w3_contract", fallback["w3_contract"]))
        w4 = float(src.get("w4_memory", src.get("w4_reviewer_memory", fallback["w4_memory"])))
        s = w1 + w2 + w3 + w4
        if s <= 0:
            return dict(fallback)
        return {"w1_semantic": w1 / s, "w2_ontology": w2 / s, "w3_contract": w3 / s, "w4_memory": w4 / s}

    def _read_weight_config_payload(self) -> dict[str, Any]:
        if not self.weight_config_path.is_file():
            return {}
        try:
            data = json.loads(self.weight_config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _read_embedding_weight_payload(self) -> dict[str, Any]:
        """Tuned weights for sentence-embedding path (separate file from TF-IDF tuning)."""
        if not self.embedding_weight_config_path.is_file():
            return {}
        try:
            data = json.loads(self.embedding_weight_config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _try_load_sentence_transformer(self) -> tuple[Any | None, str | None]:
        """Return (model, model_id) or (None, error)."""
        err_msgs: list[str] = []
        local_path = self.embedding_model_local_path
        model_ids: list[str] = []
        cfg_mid = self.embedding_model_id_config
        if cfg_mid:
            model_ids.append(cfg_mid)
            short = cfg_mid.split("/")[-1]
            if "/" in cfg_mid and short and short not in model_ids:
                model_ids.append(short)
        for mid in SENTENCE_TRANSFORMER_MODEL_IDS:
            if mid not in model_ids:
                model_ids.append(mid)
        if local_path:
            p = Path(local_path)
            if p.exists():
                try:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(str(p))
                    return model, f"local:{p}"
                except Exception as exc:  # noqa: BLE001
                    err_msgs.append(f"local_path={p}: {exc}")
            else:
                err_msgs.append(f"local_path={p}: path does not exist")
        for mid in model_ids:
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(mid)
                return model, mid
            except Exception as exc:  # noqa: BLE001 — optional dependency path
                err_msgs.append(f"{mid}: {exc}")
                continue
        return None, " | ".join(err_msgs) if err_msgs else "sentence-transformers model could not be loaded"

    def _apply_scoring_backend_and_weights(self) -> None:
        """Set scoring_backend_effective, semantic_backend, admission_score_weights, and optional ST model."""
        payload = self._read_weight_config_payload()
        requested = str(payload.get("scoring_backend") or "sentence_embedding").strip().lower()
        if requested not in {"sentence_embedding", "tfidf"}:
            requested = "sentence_embedding"
        self.scoring_backend_requested = requested

        tfidf_w = self._normalize_weight_dict(payload.get("best_weights"), DEFAULT_ADMISSION_SCORE_WEIGHTS)
        emb_payload = self._read_embedding_weight_payload()
        emb_file_weights = emb_payload.get("best_weights")
        emb_from_file = bool(isinstance(emb_file_weights, dict) and emb_file_weights)
        if emb_from_file:
            emb_w = self._normalize_weight_dict(emb_file_weights, DEFAULT_EMBEDDING_ADMISSION_WEIGHTS)
        else:
            emb_w = dict(DEFAULT_EMBEDDING_ADMISSION_WEIGHTS)

        if requested == "tfidf":
            self._sentence_transformer_model = None
            self._sentence_transformer_model_id = None
            self.scoring_backend_effective = "tfidf"
            self.semantic_backend = "tfidf"
            self.semantic_scoring_warning = None
            self.embedding_weights_source = None
            self.admission_score_weights = tfidf_w
            return

        model, mid_or_err = self._try_load_sentence_transformer()
        if model is not None:
            self._sentence_transformer_model = model
            self._sentence_transformer_model_id = mid_or_err
            self.scoring_backend_effective = "sentence_embedding"
            self.semantic_backend = "sentence_embedding"
            self.semantic_scoring_warning = None
            self.embedding_weights_source = "file" if emb_from_file else "default"
            self.admission_score_weights = emb_w
            logger.info("Loaded sentence-transformers model: %s", mid_or_err)
            return

        self._sentence_transformer_model = None
        self._sentence_transformer_model_id = None
        self.scoring_backend_effective = "tfidf_fallback"
        self.semantic_backend = "tfidf_fallback"
        self.embedding_weights_source = None
        self.admission_score_weights = tfidf_w
        self.semantic_scoring_warning = (
            f"sentence-transformers could not load ({mid_or_err}); using TF-IDF similarity with tfidf tuned weights. "
            "Re-tune weights after embeddings are available. "
            "Set EMBEDDING_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2 and optionally "
            "EMBEDDING_MODEL_LOCAL_PATH=/absolute/path/to/local/model."
        )
        logger.warning(self.semantic_scoring_warning)

    def _expand_column_token_stems(self, column_tokens: set[str]) -> set[str]:
        """Split underscore tokens so e.g. transaction_id contributes transaction."""
        stems: set[str] = set(column_tokens)
        for c in column_tokens:
            for part in str(c).split("_"):
                p = part.strip().lower()
                if len(p) > 2:
                    stems.add(p)
        return stems

    def _ontology_concept_match_score(self, domain: str, column_stems: set[str]) -> float:
        keys = DOMAIN_ONTOLOGY_TERMS.get(domain)
        if not keys:
            return 0.0
        hits = len(keys.intersection(column_stems))
        # Cap denominator so larger vocabularies do not require unrealistic hit counts for a strong score.
        denom = max(5.0, min(14.0, float(len(keys)) * 0.28))
        return float(min(1.0, hits / denom))

    def _ontology_concepts_readable(self, domain: str, limit: int = 36) -> str:
        terms = sorted(DOMAIN_ONTOLOGY_TERMS.get(domain, ()))
        return ", ".join(terms[:limit]) if terms else "general business attributes"

    def _load_contract_yaml(self, contract_file: Path) -> dict[str, Any]:
        try:
            data = yaml.safe_load(contract_file.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _domain_profile_rich_text(self, payload: dict[str, Any]) -> str:
        """Optional domain_profile block in contract YAML — improves embedding / TF-IDF domain profiles."""
        dp = payload.get("domain_profile")
        if not isinstance(dp, dict):
            return ""
        parts: list[str] = []
        bm = str(dp.get("business_meaning") or "").strip()
        if bm:
            parts.append(bm)
        for key in ("common_terms", "expected_entities", "typical_actions", "known_dataset_examples"):
            v = dp.get(key)
            if isinstance(v, list):
                flat = ", ".join(str(x).strip() for x in v if str(x).strip())
                if flat:
                    parts.append(f"{key.replace('_', ' ')}: {flat}")
            elif isinstance(v, str) and v.strip():
                parts.append(f"{key.replace('_', ' ')}: {v.strip()}")
        return " ".join(parts).strip()

    def _contract_columns_from_payload(self, payload: dict[str, Any]) -> list[str]:
        schema = payload.get("schema") if isinstance(payload, dict) else None
        if not isinstance(schema, list):
            return []
        cols: list[str] = []
        for item in schema:
            if isinstance(item, dict) and item.get("column"):
                cols.append(str(item.get("column")).strip().lower())
        return cols

    def _required_coverage_bundles_for_domain(self, domain: str, contract_cols: set[str]) -> list[frozenset[str]]:
        raw = REQUIRED_COVERAGE_BUNDLES.get(domain, ())
        out: list[frozenset[str]] = []
        for b in raw:
            bi = frozenset(c for c in b if c in contract_cols)
            if len(bi) >= 3:
                out.append(bi)
        if out:
            return out
        cols_list = sorted(contract_cols)
        req = self._required_columns(domain_name=domain, columns=cols_list)
        if req:
            return [frozenset(req)]
        return []

    def _business_concepts_from_stems(self, stems: set[str], limit: int = 36) -> str:
        hits: list[str] = []
        for _dom, terms in DOMAIN_ONTOLOGY_TERMS.items():
            for t in sorted(terms.intersection(stems)):
                if t not in hits:
                    hits.append(t)
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break
        return ", ".join(hits) if hits else "general tabular attributes"

    def _build_dataset_business_sentence(
        self, dataset_name: str, df: pd.DataFrame, columns_detected: list[str], column_stems: set[str]
    ) -> str:
        dtypes = [f"{c} ({str(df[c].dtype)})" for c in list(df.columns)[:18]]
        sample = self._safe_sample_summary(df)[:500]
        concepts = self._business_concepts_from_stems(column_stems)
        return (
            f"This dataset is named {dataset_name}. "
            f"It includes columns such as {', '.join(columns_detected[:28])}. "
            f"Column data types include: {', '.join(dtypes)}. "
            f"Ontology-aligned business concepts suggested by the schema include: {concepts}. "
            f"Safe statistical summaries: {sample}. "
            f"The table represents operational or analytical records suitable for semantic domain routing."
        ).strip()

    def _build_domain_business_sentence(
        self,
        domain: str,
        signatures: dict[str, dict[str, set[str]]],
        memory_entries: list[dict],
    ) -> str:
        sig = signatures.get(domain) or {}
        cols = sorted(sig.get("all", set()))
        ontology = self._ontology_concepts_readable(domain)
        mem_ds: list[str] = []
        for m in memory_entries:
            if not isinstance(m, dict):
                continue
            if str(m.get("domain_name") or "").strip().lower() != str(domain).strip().lower():
                continue
            if str(m.get("reviewer_action") or "").upper() == "REJECT":
                continue
            ds = str(m.get("dataset_name") or "").strip()
            if ds:
                mem_ds.append(ds)
        mem_part = ""
        if mem_ds:
            mem_part = f" Prior reviewer-approved datasets linked to this domain include: {', '.join(mem_ds[-8:])}."
        product_cols = ""
        domain_csv = self.domain_products_dir / domain / f"{domain}.csv"
        if domain_csv.is_file():
            try:
                ddf = pd.read_csv(domain_csv, nrows=5)
                product_cols = f" Example domain product columns: {', '.join([str(c).strip() for c in ddf.columns[:22]])}."
            except Exception:
                pass
        col_preview = ", ".join(cols[:40]) if cols else "(contract columns pending)"
        prof = str(sig.get("profile_rich_text") or "").strip()
        prof_part = f" Domain narrative: {prof}" if prof else ""
        return (
            f"The {domain.replace('_', ' ')} represents business concepts including: {ontology}. "
            f"Contract-aligned column expectations include: {col_preview}.{product_cols}{prof_part}"
            f"{mem_part}"
        ).strip()

    def _embedding_similarities(
        self, dataset_sentence: str, domain_sentences: dict[str, str], model: Any
    ) -> dict[str, float]:
        if not domain_sentences:
            return {}
        domains = list(domain_sentences.keys())
        texts = [dataset_sentence] + [domain_sentences[d] for d in domains]
        emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        q = np.asarray(emb[0], dtype=np.float64)
        out: dict[str, float] = {}
        for i, d in enumerate(domains):
            v = np.asarray(emb[i + 1], dtype=np.float64)
            sim = float(np.dot(q, v))
            out[d] = max(0.0, min(1.0, (sim + 1.0) / 2.0))
        return out

    def _semantic_channel_user_note(self) -> str:
        if self.semantic_backend == "sentence_embedding":
            mid = self._sentence_transformer_model_id or "sentence-transformers"
            return (
                f"Semantic similarity uses sentence embeddings ({mid}). "
                "Re-tune embedding_best_weights in optimal_domain_weights.json after collecting labeled production runs."
            )
        if self.semantic_backend == "tfidf_fallback":
            return self.semantic_scoring_warning or "TF-IDF fallback is active because the embedding model could not load."
        return "Semantic similarity uses TF-IDF cosine similarity over profile strings (not a deep embedding model)."

    def _dataset_origin_for_name(self, dataset_name: str) -> str:
        """CORE = canonical Silver files; DEMO = listed in demo_loaded_files.json manifest; else UPLOADED."""
        name = str(dataset_name or "")
        if name in CORE_SILVER_CSV_ALLOWLIST:
            return "CORE"
        for m in self._read_demo_manifest():
            if isinstance(m, dict) and str(m.get("dataset_name") or "") == name:
                return "DEMO"
        return "UPLOADED"

    def _dataset_origin_display(self, origin: str) -> str:
        return {"CORE": "Core", "DEMO": "Demo", "UPLOADED": "Upload"}.get(str(origin), str(origin or "—"))

    def _expected_core_domain(self, dataset_name: str) -> str | None:
        return CORE_EXPECTED_DOMAIN_BY_DATASET.get(str(dataset_name or "").strip().lower())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_silver_datasets(self) -> dict:
        datasets = []
        for csv_path in self._silver_csv_files():
            columns, row_count = self._dataset_schema(csv_path)
            origin = self._dataset_origin_for_name(csv_path.name)
            datasets.append(
                {
                    "dataset_name": csv_path.name,
                    "dataset_origin": origin,
                    "dataset_origin_display": self._dataset_origin_display(origin),
                    "columns": columns,
                    "row_count": row_count,
                    "timestamp": datetime.fromtimestamp(csv_path.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
        return {"datasets": datasets, "count": len(datasets)}

    def run_domain_detection(self) -> dict:
        run_id = str(uuid.uuid4())[:10]
        timestamp = datetime.now().isoformat(timespec="seconds")
        signatures = self._domain_signatures()
        self._merge_created_domain_signatures(signatures)
        domain_profile_texts = self._build_domain_profile_texts(signatures)
        memory_entries = self._read_memory_bank()

        rows: list[dict] = []
        for csv_path in self._silver_csv_files():
            row = self._evaluate_dataset(
                csv_path=csv_path,
                run_id=run_id,
                timestamp=timestamp,
                signatures=signatures,
                domain_profile_texts=domain_profile_texts,
                memory_entries=memory_entries,
            )
            rows.append(row)

        self._append_audit_rows(rows)
        for row in rows:
            self._enrich_admission_row(row)
        return {
            "run_id": run_id,
            "timestamp": timestamp,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "embedding_model_id": self._sentence_transformer_model_id,
            "embedding_weights_source": self.embedding_weights_source,
            "admission_score_weights": {k: round(float(v), 4) for k, v in self.admission_score_weights.items()},
            "results": rows,
            "count": len(rows),
        }

    def get_detection_results(self, limit: int = 50) -> dict:
        limit = max(1, min(int(limit), 500))
        all_rows = self._read_audit_rows()
        page = all_rows[:limit]
        for row in page:
            self._enrich_admission_row(row)
        return {"results": page, "count": min(limit, len(all_rows)), "total": len(all_rows)}

    def get_materialization_records(self, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit), 1000))
        rows = self._read_materialization_log()
        rows_sorted = sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda x: str(x.get("timestamp") or ""),
            reverse=True,
        )
        latest_by_dataset: dict[str, str] = {}
        for rec in rows_sorted:
            ds = str(rec.get("dataset_name") or "")
            if ds and ds not in latest_by_dataset:
                latest_by_dataset[ds] = str(rec.get("materialization_id") or "")
        for rec in rows_sorted:
            ds = str(rec.get("dataset_name") or "")
            rid = str(rec.get("materialization_id") or "")
            rec["record_scope"] = "current" if ds and latest_by_dataset.get(ds) == rid else "history"
        page = rows_sorted[:limit]
        return {"records": page, "count": len(page), "total": len(rows_sorted)}

    def apply_domain_admission(self, passport_id: str, dataset_name: str, target_domain: str) -> dict[str, Any]:
        pid = str(passport_id or "").strip()
        ds = str(dataset_name or "").strip()
        td_raw = str(target_domain or "").strip()
        if not pid or not ds or not td_raw:
            raise ValueError("passport_id, dataset_name, and target_domain are required.")

        target_norm = self._normalize_domain_name(td_raw)
        source = self.silver_dir / ds
        if not source.is_file():
            raise ValueError(f"Silver dataset not found: {ds}")

        if self._dataset_origin_for_name(ds) == "CORE":
            raise ValueError(
                "Canonical core Silver datasets are already governed by the domain pipeline. "
                "Apply is only for uploads or demo-loaded datasets."
            )

        latest_row = self._latest_audit_row_for_dataset(ds)
        if not latest_row:
            raise ValueError("No latest assessment found for this dataset. Run assessment first.")
        latest_pp = latest_row.get("admission_passport") if isinstance(latest_row.get("admission_passport"), dict) else {}
        latest_passport_id = str(latest_pp.get("passport_id") or "")
        if latest_passport_id != pid:
            raise ValueError("Cannot load: target domain does not match latest assessment.")
        audit_row = latest_row

        best = str(audit_row.get("best_domain") or "")
        best_norm = self._normalize_domain_name(best)
        if best_norm != target_norm:
            raise ValueError("Cannot load: target domain does not match latest assessment.")

        decision = str(audit_row.get("admission_decision") or audit_row.get("action") or "")
        allowed_direct = {"AUTO_LOAD_ELIGIBLE"}
        if decision not in allowed_direct:
            raise ValueError("Cannot load: target domain does not match latest assessment.")

        pp = audit_row.get("admission_passport") or {}
        passport_ref = str(pp.get("passport_id") or pid)

        dest_dir = self._resolve_domain_product_dir(target_norm)
        dest_file = dest_dir / f"{target_norm}.csv"
        ts = datetime.now().isoformat(timespec="seconds")
        mid = str(uuid.uuid4())[:14]

        try:
            shutil.copy2(source, dest_file)
            loading_status = "LOADED_TO_DOMAIN"
            message = "Dataset loaded into domain product."
        except OSError as exc:
            loading_status = "LOAD_FAILED"
            message = f"Copy failed: {exc}"
            self._append_materialization_record(
                {
                    "materialization_id": mid,
                    "passport_id": passport_ref,
                    "dataset_name": ds,
                    "source_path": str(source.resolve()),
                    "target_domain": target_norm,
                    "target_path": str(dest_file.resolve()),
                    "loading_status": loading_status,
                    "timestamp": ts,
                    "triggered_by": "dashboard_apply",
                    "error": str(exc),
                }
            )
            raise ValueError(message) from exc

        self._append_materialization_record(
            {
                "materialization_id": mid,
                "passport_id": passport_ref,
                "dataset_name": ds,
                "source_path": str(source.resolve()),
                "target_domain": target_norm,
                "target_path": str(dest_file.resolve()),
                "loading_status": loading_status,
                "timestamp": ts,
                "triggered_by": "dashboard_apply",
            }
        )

        return {
            "success": True,
            "message": message,
            "loading_status": loading_status,
            "target_path": str(dest_file.resolve()),
            "materialization_id": mid,
        }

    def get_domain_memory_bank(self) -> dict:
        entries = self._read_memory_bank()
        by_domain: dict[str, list[dict]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            d = str(item.get("domain_name") or "").strip().lower()
            if not d:
                continue
            by_domain.setdefault(d, []).append(item)

        summary = []
        for domain, items in sorted(by_domain.items()):
            approved = [x for x in items if str(x.get("reviewer_action") or "").upper() in {"APPROVE", "APPROVE_PROVISIONAL", "CHANGE_DOMAIN", "VALIDATE_CANDIDATE", "CREATE_DOMAIN_AFTER_APPROVAL"}]
            latest_ts = max((str(x.get("timestamp") or "") for x in items), default="")
            summary.append(
                {
                    "domain_name": domain,
                    "memory_count": len(items),
                    "approved_dataset_count": len(approved),
                    "latest_memory_update": latest_ts,
                }
            )

        return {"entries": entries, "summary_by_domain": summary, "count": len(entries)}

    def upload_silver_dataset(self, filename: str, raw_bytes: bytes) -> dict:
        name = Path(str(filename or "")).name
        if not name:
            raise ValueError("File name is missing.")
        if not name.lower().endswith(".csv"):
            raise ValueError("Invalid file type. Please upload a .csv file.")
        if not raw_bytes or len(raw_bytes.strip()) == 0:
            raise ValueError("Uploaded file is empty.")

        try:
            df = pd.read_csv(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise ValueError(f"Invalid CSV file: {exc}")

        columns = [str(col).strip() for col in list(df.columns)]
        if not columns or any(col == "" or col.lower().startswith("unnamed:") for col in columns):
            raise ValueError("CSV must include a valid header row with column names.")

        self.silver_dir.mkdir(parents=True, exist_ok=True)
        save_path = self.silver_dir / name
        save_path.write_bytes(raw_bytes)

        return {
            "success": True,
            "message": "Dataset uploaded successfully",
            "dataset_name": name,
            "row_count": int(len(df)),
            "column_count": int(len(columns)),
            "columns": columns,
        }

    def list_demo_source_files(self) -> dict[str, Any]:
        """CSV files available under Data/Test-upload-data for the demo loader."""
        self.test_upload_dir.mkdir(parents=True, exist_ok=True)
        names = sorted({p.name for p in self.test_upload_dir.glob("*.csv") if p.is_file()})
        return {"files": names, "count": len(names), "source_dir": str(self.test_upload_dir.resolve())}

    def load_demo_dataset(self, dataset_name: str, demo_type: str = "demo_load") -> dict[str, Any]:
        """Copy a CSV from Test-upload-data into Silver-data and record the demo manifest."""
        name = Path(str(dataset_name or "")).name
        if not name.lower().endswith(".csv"):
            raise ValueError("dataset_name must be a .csv file.")
        src = self.test_upload_dir / name
        if not src.is_file():
            raise ValueError(f"Demo file not found in Test-upload-data: {name}")

        self.silver_dir.mkdir(parents=True, exist_ok=True)
        dest = self.silver_dir / name
        shutil.copy2(src, dest)
        ts = datetime.now().isoformat(timespec="seconds")
        entry = {
            "dataset_name": name,
            "source_path": str(src.resolve()),
            "target_path": str(dest.resolve()),
            "loaded_at": ts,
            "demo_type": str(demo_type or "demo_load").strip() or "demo_load",
        }
        manifest = self._read_demo_manifest()
        manifest = [m for m in manifest if isinstance(m, dict) and str(m.get("dataset_name")) != name]
        manifest.append(entry)
        self._write_demo_manifest(manifest)

        return {
            "success": True,
            "message": "Demo dataset copied into Silver-data.",
            "dataset_name": name,
            "target_path": str(dest.resolve()),
            "manifest_entry": entry,
        }

    def remove_uploaded_test_files(self) -> dict:
        """Legacy: remove *_test.csv only. Prefer reset_demo_state() allowlist cleanup."""
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        removed: list[str] = []
        for path in self.silver_dir.glob("*_test.csv"):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed.append(path.name)
        return {
            "success": True,
            "message": "Uploaded test files removed from Silver-data.",
            "removed_files": sorted(removed),
            "removed_count": len(removed),
        }

    def clear_detection_history(self) -> dict:
        if self.audit_log_path.exists():
            self.audit_log_path.unlink(missing_ok=True)
        return {"success": True, "message": "Silver-to-domain detection history cleared."}

    def reset_demo_state(self) -> dict[str, Any]:
        """
        Full demo reset: keep only CORE_SILVER_CSV_ALLOWLIST in Silver-data; clear admission logs,
        materialization, memory, review decisions, tickets, demo manifest; retire loader-created domains.
        """
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        removed_files: list[str] = []
        for path in self.silver_dir.glob("*.csv"):
            if path.name not in CORE_SILVER_CSV_ALLOWLIST:
                path.unlink(missing_ok=True)
                removed_files.append(path.name)

        preserved_files = sorted(
            [p.name for p in self.silver_dir.glob("*.csv") if p.is_file() and p.name in CORE_SILVER_CSV_ALLOWLIST]
        )

        cleared_logs: list[str] = []

        def _clear(path: Path, label: str) -> None:
            if path.exists():
                path.unlink(missing_ok=True)
            cleared_logs.append(label)

        _clear(self.audit_log_path, "silver_domain_loader_audit.json")
        _clear(self.materialization_log_path, "domain_admission_materialization.json")
        _clear(self.domain_memory_path, "domain_memory_bank.json")
        _clear(self.review_decisions_path, "domain_review_decisions.json")
        _clear(self.review_tickets_path, "domain_review_tickets.json")
        _clear(self.demo_manifest_path, "demo_loaded_files.json")

        retired_domains = self._retire_loader_created_domains_on_demo_reset()

        return {
            "success": True,
            "message": "Demo state reset successfully",
            "removed_files": sorted(removed_files),
            "preserved_files": preserved_files,
            "cleared_logs": cleared_logs,
            "retired_created_domains": retired_domains,
        }

    def _retire_loader_created_domains_on_demo_reset(self) -> list[str]:
        """Mark non-system loader registry domains DELETED (does not remove contracts or system domains)."""
        reg = self._read_created_registry()
        retired: list[str] = []
        now = datetime.now().isoformat(timespec="seconds")
        for item in reg:
            if not isinstance(item, dict):
                continue
            if item.get("is_system_domain") is True:
                continue
            dom = str(item.get("domain_name") or "").strip().lower()
            if dom and dom in SYSTEM_DOMAINS:
                continue
            if str(item.get("status")) == "ACTIVE":
                item["status"] = "DELETED"
                item["deleted_at"] = now
                item["deleted_reason"] = "demo_reset"
                retired.append(str(item.get("domain_name")))
        self._write_created_registry(reg)
        return retired

    def _read_demo_manifest(self) -> list[dict]:
        if not self.demo_manifest_path.exists():
            return []
        try:
            data = json.loads(self.demo_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _write_demo_manifest(self, rows: list[dict]) -> None:
        self.demo_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.demo_manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def submit_review_decision(self, payload: dict[str, Any]) -> dict:
        dataset_name = str(payload.get("dataset_name") or "").strip()
        detection_run_id = str(payload.get("detection_run_id") or "").strip()
        reviewer_action = str(payload.get("reviewer_action") or "").strip().upper()
        approved_domain = self._normalize_domain_name(str(payload.get("approved_domain") or "").strip())
        candidate_domain_name = str(payload.get("candidate_domain_name") or "").strip()
        reviewer_note = str(payload.get("reviewer_note") or "").strip()

        if not dataset_name:
            raise ValueError("dataset_name is required.")

        csv_path = self.silver_dir / dataset_name
        if not csv_path.is_file():
            raise ValueError(f"Silver dataset not found: {dataset_name}")

        df = pd.read_csv(csv_path)
        cols = [str(c).strip().lower() for c in df.columns]
        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, cols)

        decision_type = reviewer_action
        memory_domain = approved_domain or self._normalize_domain_name(candidate_domain_name)

        positive_actions = {
            "APPROVE",
            "APPROVE_PROVISIONAL",
            "CHANGE_DOMAIN",
            "VALIDATE_CANDIDATE",
            "CREATE_DOMAIN_AFTER_APPROVAL",
        }
        negative_actions = {"REJECT", "REJECT_PROVISIONAL", "REJECT_CANDIDATE"}

        if reviewer_action in positive_actions:
            if reviewer_action == "CREATE_DOMAIN_AFTER_APPROVAL":
                target = self._normalize_domain_name(candidate_domain_name or approved_domain)
                if not target:
                    raise ValueError("candidate_domain_name is required for domain creation.")
                if target in SYSTEM_DOMAINS:
                    raise ValueError("Cannot create a domain that conflicts with a system domain name.")
                self._create_domain_folder(target, csv_path)
                self._upsert_created_domain_registry(
                    domain_name=target,
                    source_dataset_name=dataset_name,
                    source_columns=cols,
                    detection_run_id=detection_run_id,
                )
                memory_domain = target

            if memory_domain:
                self._append_memory_bank(
                    {
                        "memory_id": str(uuid.uuid4())[:12],
                        "domain_name": memory_domain,
                        "dataset_name": dataset_name,
                        "dataset_profile_text": dataset_profile_text,
                        "reviewer_action": reviewer_action,
                        "approved_domain": memory_domain,
                        "decision_type": decision_type,
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "source": "review_decision",
                    }
                )

        elif reviewer_action in negative_actions:
            reject_domain = approved_domain or memory_domain or candidate_domain_name
            if not reject_domain:
                reject_domain = str(payload.get("rejected_domain") or "").strip()
            reject_domain = self._normalize_domain_name(reject_domain) if reject_domain else ""
            self._append_memory_bank(
                {
                    "memory_id": str(uuid.uuid4())[:12],
                    "domain_name": reject_domain or "unknown",
                    "dataset_name": dataset_name,
                    "dataset_profile_text": dataset_profile_text,
                    "reviewer_action": "REJECT",
                    "approved_domain": reject_domain or "",
                    "decision_type": decision_type,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "source": "review_decision",
                }
            )

        ticket_id: str | None = None
        if reviewer_action == "RAISE_TICKET":
            ticket_id = str(uuid.uuid4())[:12]
            self._append_ticket(
                {
                    "ticket_id": ticket_id,
                    "dataset_name": dataset_name,
                    "candidate_domain_name": candidate_domain_name,
                    "reason": reviewer_note or "Governance review requested.",
                    "status": "OPEN",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

        decision_status = self._review_outcome_status(reviewer_action)
        ts_decision = datetime.now().isoformat(timespec="seconds")
        decision_record = {
            "decision_id": str(uuid.uuid4())[:12],
            "detection_run_id": detection_run_id,
            "dataset_name": dataset_name,
            "reviewer_action": reviewer_action,
            "approved_domain": approved_domain,
            "candidate_domain_name": candidate_domain_name,
            "reviewer_note": reviewer_note,
            "timestamp": ts_decision,
            "decision_status": decision_status,
            "ticket_id": ticket_id,
        }
        self._append_review_decision(decision_record)

        return {
            "success": True,
            "message": "Review decision recorded.",
            "decision": decision_record,
            "decision_status": decision_status,
            "ticket_id": ticket_id,
        }

    def get_review_decisions(self) -> dict:
        if not self.review_decisions_path.exists():
            return {"decisions": [], "count": 0}
        try:
            data = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
        except Exception:
            return {"decisions": [], "count": 0}
        rows = data if isinstance(data, list) else []
        return {"decisions": rows, "count": len(rows)}

    def list_created_domains(self) -> dict:
        reg = self._read_created_registry()
        active = [x for x in reg if isinstance(x, dict) and str(x.get("status") or "") == "ACTIVE"]
        return {"domains": active, "count": len(active)}

    def delete_created_domain(self, domain_name: str) -> dict:
        normalized = self._normalize_domain_name(domain_name)
        if not normalized:
            raise ValueError("domain_name is required.")
        if normalized in SYSTEM_DOMAINS:
            raise ValueError("System domains cannot be deleted.")

        reg = self._read_created_registry()
        found = False
        for entry in reg:
            if str(entry.get("domain_name") or "").lower() != normalized:
                continue
            if entry.get("is_system_domain") is True:
                raise ValueError("System-marked registry domains cannot be deleted.")
            if entry.get("status") == "ACTIVE":
                entry["status"] = "DELETED"
                entry["deleted_at"] = datetime.now().isoformat(timespec="seconds")
                found = True
        if found:
            self.created_domain_registry_path.parent.mkdir(parents=True, exist_ok=True)
            self.created_domain_registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")
        return {"success": True, "message": f"Created domain '{normalized}' marked DELETED in registry.", "domain_name": normalized}

    def _review_outcome_status(self, reviewer_action: str) -> str:
        m = {
            "APPROVE": "APPROVED",
            "APPROVE_PROVISIONAL": "APPROVED",
            "CHANGE_DOMAIN": "CHANGED",
            "REJECT": "REJECTED",
            "REJECT_PROVISIONAL": "REJECTED",
            "REJECT_CANDIDATE": "REJECTED",
            "VALIDATE_CANDIDATE": "APPROVED",
            "CREATE_DOMAIN_AFTER_APPROVAL": "DOMAIN_CREATED",
            "MARK_ORPHAN_CANDIDATE": "ORPHAN_CANDIDATE",
            "RAISE_TICKET": "TICKET_OPENED",
        }
        return m.get(str(reviewer_action or "").strip().upper(), "RECORDED")

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------
    def _fallback_row_no_contracts(
        self,
        csv_path: Path,
        run_id: str,
        timestamp: str,
        columns_detected: list[str],
        df: pd.DataFrame,
    ) -> dict:
        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, columns_detected)
        column_stems_fb = self._expand_column_token_stems(set(columns_detected))
        dataset_business_sentence_fb = self._build_dataset_business_sentence(
            csv_path.name, df, columns_detected, column_stems_fb
        )
        gov = self._governance_risk_preview(df)
        fp_origin = self._dataset_origin_for_name(csv_path.name)
        expected_core_domain = self._expected_core_domain(csv_path.name) if fp_origin == "CORE" else None
        core_validation_status = "WARNING" if expected_core_domain else None
        admission_decision = "GOVERNANCE_TICKET_RECOMMENDED" if gov == "HIGH" else "NEW_DOMAIN_CANDIDATE"
        passport = {
            "passport_id": str(uuid.uuid4())[:12],
            "dataset_name": csv_path.name,
            "dataset_origin": fp_origin,
            "dataset_origin_display": self._dataset_origin_display(fp_origin),
            "dataset_profile_text": dataset_profile_text,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "embedding_model_id": self._sentence_transformer_model_id,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "dataset_business_sentence": dataset_business_sentence_fb,
            "domain_business_sentence": "",
            "embedding_similarity_for_suggested_domain": 0.0,
            "embedding_similarity_score": 0.0,
            "embedding_similarity": 0.0,
            "contract_fit_score": 0.0,
            "ontology_concept_match_score": 0.0,
            "ontology_concept_match": 0.0,
            "domain_similarity_score": 0.0,
            "domain_readiness_score": 0.0,
            "reviewer_memory_score": 0.5,
            "final_score": 0.0,
            "suggested_domain": None,
            "semantic_best_domain": None,
            "semantic_similarity_score": 0.0,
            "semantic_similarity_for_suggested_domain": 0.0,
            "profile_similarity_for_suggested_domain": 0.0,
            "ontology_concept_match_for_suggested_domain": 0.0,
            "contract_coverage_score": 0.0,
            "memory_feedback_score": 0.5,
            "reviewer_memory_for_suggested_domain": 0.5,
            "filename_score": 0.0,
            "final_admission_score": 0.0,
            "contract_gate": "FAILED",
            "contract_gate_detail": "No domain contracts available to evaluate column fit.",
            "primary_reason_code": "NO_CONTRACTS",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "ambiguity_gap": 0.0,
            "admission_score_ambiguity_gap": 0.0,
            "profile_similarity_ambiguity_gap": 0.0,
            "matched_memory_entries": [],
            "governance_risk_preview": gov,
            "core_expected_domain": expected_core_domain,
            "core_validation_status": core_validation_status,
            "recommended_action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": True,
            "explanation": "No domain contracts available to score against; admission deferred.",
            "timestamp": timestamp,
            "policy_reason_codes": ["NO_CONTRACTS"],
            "admission_score_weights": {k: round(float(v), 4) for k, v in self.admission_score_weights.items()},
            "lexical_similarity_note": self._semantic_channel_user_note(),
            "memory_display_mode": "no_bank",
            "memory_score_for_display": None,
        }
        out_row = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_origin": fp_origin,
            "dataset_origin_display": self._dataset_origin_display(fp_origin),
            "dataset_profile_text": dataset_profile_text,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "embedding_model_id": self._sentence_transformer_model_id,
            "dataset_business_sentence": dataset_business_sentence_fb,
            "domain_business_sentence": "",
            "embedding_similarity_score": 0.0,
            "embedding_similarity": 0.0,
            "ontology_concept_match_score": 0.0,
            "ontology_concept_match": 0.0,
            "contract_fit_score": 0.0,
            "reviewer_memory_score": 0.5,
            "domain_similarity_score": 0.0,
            "domain_readiness_score": 0.0,
            "final_score": 0.0,
            "columns_detected": columns_detected,
            "best_domain": None,
            "confidence_score": 0.0,
            "semantic_similarity_score": 0.0,
            "semantic_similarity_for_suggested_domain": 0.0,
            "contract_coverage_score": 0.0,
            "memory_feedback_score": 0.5,
            "filename_score": 0.0,
            "final_admission_score": 0.0,
            "policy_reason_codes": passport.get("policy_reason_codes"),
            "contract_gate": "FAILED",
            "contract_gate_detail": passport.get("contract_gate_detail"),
            "primary_reason_code": "NO_CONTRACTS",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_best_domain": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "semantic_ambiguity_gap": 0.0,
            "all_domain_scores": {},
            "all_semantic_scores": {},
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": True,
            "candidate_domain_name": self._candidate_domain_name(csv_path.name, columns_detected, []),
            "final_domain": None,
            "timestamp": timestamp,
            "explanation": passport["explanation"],
            "governance_risk_preview": gov,
            "core_expected_domain": expected_core_domain,
            "core_validation_status": core_validation_status,
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": "no_bank",
            "memory_score_for_display": None,
            "memory_signal_active": False,
        }
        self._enrich_admission_row(out_row)
        return out_row

    def _evaluate_dataset(
        self,
        csv_path: Path,
        run_id: str,
        timestamp: str,
        signatures: dict[str, dict[str, set[str]]],
        domain_profile_texts: dict[str, str],
        memory_entries: list[dict],
        *,
        semantic_channel: str = "active",
        admission_weights: dict[str, float] | None = None,
    ) -> dict:
        df = pd.read_csv(csv_path)
        columns_detected = [str(c).strip().lower() for c in df.columns]
        origin = self._dataset_origin_for_name(csv_path.name)

        created_match = self._match_created_domain_for_dataset(csv_path.name)
        if created_match:
            passport = self._build_created_domain_passport(
                csv_path=csv_path,
                df=df,
                columns_detected=columns_detected,
                dataset_profile_text=self._build_dataset_profile_text(csv_path.name, df, columns_detected),
                domain_name=created_match["domain_name"],
                timestamp=timestamp,
                registry_entry=created_match,
                signatures=signatures,
                memory_entries=memory_entries,
            )
            dom = created_match["domain_name"]
            return self._audit_row_from_passport(
                run_id=run_id,
                csv_path=csv_path,
                columns_detected=columns_detected,
                passport=passport,
                admission_decision="AUTO_ASSIGN_CREATED_DOMAIN",
                review_required=False,
                candidate_domain_name=None,
                ranked_final={dom: 0.95},
                semantic_sims={dom: 0.95},
                extra_explanation="Assigned via governed created-domain registry and prior approval workflow.",
            )

        ranked_parts = self._rank_domain_contract_parts(csv_path, columns_detected, signatures)
        if not ranked_parts or not domain_profile_texts:
            return self._fallback_row_no_contracts(
                csv_path=csv_path,
                run_id=run_id,
                timestamp=timestamp,
                columns_detected=columns_detected,
                df=df,
            )

        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, columns_detected)
        column_stems = self._expand_column_token_stems(set(columns_detected))
        dataset_business_sentence = self._build_dataset_business_sentence(
            csv_path.name, df, columns_detected, column_stems
        )
        domain_business_sentences = {
            d: self._build_domain_business_sentence(d, signatures, memory_entries)
            for d in domain_profile_texts.keys()
        }

        ch = str(semantic_channel or "active").strip().lower()
        if ch == "tfidf":
            sem_sims = self._semantic_similarities(dataset_profile_text, domain_profile_texts)
        elif ch == "embedding":
            if self._sentence_transformer_model is not None:
                sem_sims = self._embedding_similarities(
                    dataset_business_sentence,
                    domain_business_sentences,
                    self._sentence_transformer_model,
                )
            else:
                sem_sims = self._semantic_similarities(dataset_profile_text, domain_profile_texts)
        elif self.semantic_backend == "sentence_embedding" and self._sentence_transformer_model is not None:
            sem_sims = self._embedding_similarities(
                dataset_business_sentence,
                domain_business_sentences,
                self._sentence_transformer_model,
            )
        else:
            sem_sims = self._semantic_similarities(dataset_profile_text, domain_profile_texts)

        memory_by_domain = self._memory_feedback_scores(
            dataset_profile=dataset_profile_text,
            memory_entries=memory_entries,
            domains=list(domain_profile_texts.keys()),
        )

        W = (
            self._normalize_weight_dict(admission_weights, self.admission_score_weights)
            if admission_weights is not None
            else self.admission_score_weights
        )
        w1, w2, w3, w4 = W["w1_semantic"], W["w2_ontology"], W["w3_contract"], W["w4_memory"]

        final_scores: dict[str, float] = {}
        detail_by_domain: dict[str, dict[str, float]] = {}
        for part in ranked_parts:
            sem = float(sem_sims.get(part.domain, 0.0))
            ont = self._ontology_concept_match_score(part.domain, column_stems)
            mem_raw = float(memory_by_domain.get(part.domain, 0.5))
            _mem_t = self._memory_for_trust_composite(mem_raw, memory_entries, part.domain)
            cfit = float(part.contract_coverage_score)
            fin = w1 * sem + w2 * ont + w3 * cfit + w4 * mem_raw
            fin = max(0.0, min(1.0, float(fin)))
            final_scores[part.domain] = fin
            detail_by_domain[part.domain] = {
                "semantic_similarity": sem,
                "embedding_similarity_score": sem,
                "ontology_concept_match_score": ont,
                "contract_coverage_score": cfit,
                "contract_fit_score": cfit,
                "memory_feedback_score_raw": mem_raw,
                "memory_feedback_score_trust": _mem_t,
                "memory_feedback_score": mem_raw,
                "reviewer_memory_score": mem_raw,
                "filename_score": part.filename_score,
                "final_admission_score": fin,
            }

        sorted_final = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
        best_domain = sorted_final[0][0] if sorted_final else None
        second_domain = sorted_final[1][0] if len(sorted_final) > 1 else None
        best_final = sorted_final[0][1] if sorted_final else 0.0
        second_final = sorted_final[1][1] if len(sorted_final) > 1 else 0.0
        final_leader_gap = max(0.0, float(best_final - second_final))

        sorted_sem = sorted(sem_sims.items(), key=lambda x: x[1], reverse=True)
        sem_best = sorted_sem[0][0] if sorted_sem else None
        sem_best_score = float(sorted_sem[0][1]) if sorted_sem else 0.0
        sem_second = sorted_sem[1][0] if len(sorted_sem) > 1 else None
        sem_second_score = float(sorted_sem[1][1]) if len(sorted_sem) > 1 else 0.0
        sem_gap = max(0.0, sem_best_score - sem_second_score)

        best_parts = next((p for p in ranked_parts if p.domain == best_domain), ranked_parts[0] if ranked_parts else None)
        required_ok = bool(best_parts and best_parts.required_coverage >= 0.35)

        sorted_by_contract = sorted(ranked_parts, key=lambda p: p.contract_coverage_score, reverse=True)
        contract_leader_gap = 1.0
        if len(sorted_by_contract) > 1:
            contract_leader_gap = float(
                sorted_by_contract[0].contract_coverage_score - sorted_by_contract[1].contract_coverage_score
            )

        gov_risk = self._governance_risk_preview(df)

        admission_decision, reason_codes = self._resolve_admission_policy(
            final_score_best=best_final,
            semantic_gap=sem_gap,
            admission_leader_gap=final_leader_gap,
            required_coverage_ok=required_ok,
            governance_risk=gov_risk,
            contract_coverage_best=float(best_parts.contract_coverage_score) if best_parts else 0.0,
            required_coverage_best=float(best_parts.required_coverage) if best_parts else 0.0,
            contract_leader_gap=contract_leader_gap,
        )

        cg_code, cg_detail = self._contract_gate_eval(
            float(best_parts.contract_coverage_score) if best_parts else 0.0,
            float(best_parts.required_coverage) if best_parts else 0.0,
            gov_risk,
        )
        bd0 = detail_by_domain.get(best_domain or "", {})
        sem_for_suggested = float(bd0.get("embedding_similarity_score", bd0.get("semantic_similarity", 0.0)))
        ont_for_suggested = float(bd0.get("ontology_concept_match_score", 0.0))
        cfit_for_suggested = float(bd0.get("contract_fit_score", bd0.get("contract_coverage_score", 0.0)))
        mem_for_suggested = float(bd0.get("reviewer_memory_score", bd0.get("memory_feedback_score", 0.5)))
        domain_similarity_score = max(0.0, min(1.0, 0.50 * sem_for_suggested + 0.50 * ont_for_suggested))
        domain_readiness_score = max(0.0, min(1.0, 0.40 * sem_for_suggested + 0.40 * ont_for_suggested + 0.20 * cfit_for_suggested))
        expected_core_domain = self._expected_core_domain(csv_path.name) if origin == "CORE" else None
        core_validation_status = None
        if expected_core_domain:
            core_validation_status = "PASSED" if (best_domain or "") == expected_core_domain else "WARNING"
        prc = self._primary_reason_code(reason_codes)
        trust_note = self._trust_eligibility_note(
            admission_decision, best_final, reason_codes, sem_for_suggested, self.semantic_backend
        )

        matched_memory = self._matched_memory_entries_for_dataset(
            dataset_profile=dataset_profile_text,
            memory_entries=memory_entries,
            top_domain=best_domain or "",
        )

        explanation = self._build_passport_explanation(
            admission_decision=admission_decision,
            reason_codes=reason_codes,
            best_domain=best_domain,
            detail=detail_by_domain.get(best_domain or "", {}),
            semantic_best=sem_best,
            sem_gap=sem_gap,
            admission_leader_gap=final_leader_gap,
            gov_risk=gov_risk,
            contract_cov=float(best_parts.contract_coverage_score) if best_parts else 0.0,
            req_cov=float(best_parts.required_coverage) if best_parts else 0.0,
            contract_gap=contract_leader_gap,
        )
        if trust_note:
            explanation = f"{explanation} {trust_note}"
        if (
            expected_core_domain
            and core_validation_status == "PASSED"
            and 0.45 <= domain_readiness_score < 0.75
        ):
            explanation = (
                f"{explanation} The dataset matches the expected domain, but readiness is moderate "
                "because contract/ontology coverage is incomplete."
            )

        passport_id = str(uuid.uuid4())[:12]

        mem_raw = float(detail_by_domain.get(best_domain or "", {}).get("memory_feedback_score", 0.5))
        mem_ui = self._memory_display_fields(
            memory_entries=memory_entries,
            best_domain=best_domain or "",
            memory_score=mem_raw,
            matched_memory=matched_memory,
        )

        domain_sentence_suggested = (
            domain_business_sentences.get(best_domain or "", "") if best_domain else ""
        )
        passport: dict[str, Any] = {
            "passport_id": passport_id,
            "dataset_name": csv_path.name,
            "dataset_origin": origin,
            "dataset_origin_display": self._dataset_origin_display(origin),
            "dataset_profile_text": dataset_profile_text,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "embedding_model_id": self._sentence_transformer_model_id,
            "embedding_weights_source": self.embedding_weights_source,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "dataset_business_sentence": dataset_business_sentence,
            "domain_business_sentence": domain_sentence_suggested,
            "suggested_domain": best_domain,
            "admission_score_weights": {k: round(float(v), 4) for k, v in self.admission_score_weights.items()},
            "required_coverage": round(float(best_parts.required_coverage), 4) if best_parts else 0.0,
            "contract_leader_gap": round(contract_leader_gap, 4),
            "semantic_best_domain": sem_best,
            "semantic_similarity_score": round(sem_best_score, 4),
            "semantic_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "profile_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "embedding_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "embedding_similarity": round(sem_for_suggested, 4),
            "ontology_concept_match_for_suggested_domain": round(ont_for_suggested, 4),
            "ontology_concept_match": round(ont_for_suggested, 4),
            "ontology_concept_match_score": round(ont_for_suggested, 4),
            "contract_coverage_score": round(detail_by_domain.get(best_domain or "", {}).get("contract_coverage_score", 0.0), 4),
            "contract_fit_score": round(cfit_for_suggested, 4),
            "domain_similarity_score": round(domain_similarity_score, 4),
            "domain_readiness_score": round(domain_readiness_score, 4),
            "memory_feedback_score": round(mem_raw, 4),
            "reviewer_memory_for_suggested_domain": round(mem_raw, 4),
            "reviewer_memory_score": round(mem_for_suggested, 4),
            "filename_score": round(detail_by_domain.get(best_domain or "", {}).get("filename_score", 0.0), 4),
            "final_admission_score": round(best_final, 4),
            "final_score": round(best_final, 4),
            "contract_gate": cg_code,
            "contract_gate_detail": cg_detail,
            "primary_reason_code": prc,
            "trust_eligibility_note": trust_note,
            "second_best_domain": second_domain,
            "second_best_score": round(second_final, 4),
            "semantic_second_best_domain": sem_second,
            "semantic_second_best_score": round(sem_second_score, 4),
            "ambiguity_gap": round(final_leader_gap, 4),
            "admission_score_ambiguity_gap": round(final_leader_gap, 4),
            "profile_similarity_ambiguity_gap": round(sem_gap, 4),
            "matched_memory_entries": matched_memory,
            "governance_risk_preview": gov_risk,
            "core_expected_domain": expected_core_domain,
            "core_validation_status": core_validation_status,
            "recommended_action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": admission_decision
            in {"HUMAN_REVIEW_REQUIRED", "NEW_DOMAIN_CANDIDATE", "GOVERNANCE_TICKET_RECOMMENDED"},
            "explanation": explanation,
            "timestamp": timestamp,
            "policy_reason_codes": reason_codes,
            "lexical_similarity_note": self._semantic_channel_user_note(),
            "memory_display_mode": mem_ui["mode"],
            "memory_score_for_display": mem_ui.get("score_for_display"),
        }

        review_required = passport["review_required"]
        if admission_decision == "NEW_DOMAIN_CANDIDATE":
            candidate_name = self._candidate_domain_name(csv_path.name, columns_detected, ranked_parts)
        else:
            candidate_name = None

        final_domain = best_domain if admission_decision == "AUTO_LOAD_ELIGIBLE" else None

        row = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_origin": origin,
            "dataset_origin_display": self._dataset_origin_display(origin),
            "dataset_profile_text": dataset_profile_text,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "embedding_model_id": self._sentence_transformer_model_id,
            "embedding_weights_source": self.embedding_weights_source,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "dataset_business_sentence": dataset_business_sentence,
            "domain_business_sentence": domain_sentence_suggested,
            "embedding_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "embedding_similarity_score": round(sem_for_suggested, 4),
            "embedding_similarity": round(sem_for_suggested, 4),
            "ontology_concept_match_score": round(ont_for_suggested, 4),
            "ontology_concept_match": round(ont_for_suggested, 4),
            "contract_fit_score": round(cfit_for_suggested, 4),
            "reviewer_memory_score": round(mem_for_suggested, 4),
            "domain_similarity_score": round(domain_similarity_score, 4),
            "domain_readiness_score": round(domain_readiness_score, 4),
            "final_score": round(best_final, 4),
            "columns_detected": columns_detected,
            "best_domain": best_domain,
            "confidence_score": round(best_final, 4),
            "semantic_similarity_score": round(sem_best_score, 4),
            "semantic_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "contract_coverage_score": passport["contract_coverage_score"],
            "memory_feedback_score": passport["memory_feedback_score"],
            "filename_score": passport["filename_score"],
            "final_admission_score": round(best_final, 4),
            "policy_reason_codes": reason_codes,
            "contract_gate": cg_code,
            "contract_gate_detail": cg_detail,
            "primary_reason_code": prc,
            "trust_eligibility_note": trust_note,
            "second_best_domain": second_domain,
            "second_best_score": round(second_final, 4),
            "semantic_best_domain": sem_best,
            "semantic_second_best_domain": sem_second,
            "semantic_second_best_score": round(sem_second_score, 4),
            "semantic_ambiguity_gap": round(sem_gap, 4),
            "admission_score_ambiguity_gap": round(final_leader_gap, 4),
            "ontology_concept_match_for_suggested_domain": round(ont_for_suggested, 4),
            "all_domain_scores": {k: round(v, 4) for k, v in final_scores.items()},
            "all_semantic_scores": {k: round(float(v), 4) for k, v in sem_sims.items()},
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": review_required,
            "candidate_domain_name": candidate_name,
            "final_domain": final_domain,
            "timestamp": timestamp,
            "explanation": explanation,
            "governance_risk_preview": gov_risk,
            "core_expected_domain": expected_core_domain,
            "core_validation_status": core_validation_status,
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": mem_ui["mode"],
            "memory_score_for_display": mem_ui.get("score_for_display"),
            "required_coverage": round(float(best_parts.required_coverage), 4) if best_parts else None,
            "contract_leader_gap": round(contract_leader_gap, 4),
            "memory_signal_active": mem_ui["mode"] == "scored",
        }
        self._enrich_admission_row(row)
        return row

    def _audit_row_from_passport(
        self,
        run_id: str,
        csv_path: Path,
        columns_detected: list[str],
        passport: dict[str, Any],
        admission_decision: str,
        review_required: bool,
        candidate_domain_name: str | None,
        ranked_final: dict[str, float],
        semantic_sims: dict[str, float],
        extra_explanation: str,
    ) -> dict:
        ts = passport.get("timestamp") or datetime.now().isoformat(timespec="seconds")
        explanation = str(passport.get("explanation") or "") + " " + extra_explanation
        best = passport.get("suggested_domain")
        conf = float(passport.get("final_admission_score") or 0.95)
        out = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_profile_text": passport.get("dataset_profile_text"),
            "columns_detected": columns_detected,
            "best_domain": best,
            "confidence_score": conf,
            "semantic_similarity_score": passport.get("semantic_similarity_score"),
            "semantic_similarity_for_suggested_domain": passport.get("semantic_similarity_for_suggested_domain"),
            "ontology_concept_match_for_suggested_domain": passport.get("ontology_concept_match_for_suggested_domain"),
            "contract_coverage_score": passport.get("contract_coverage_score"),
            "memory_feedback_score": passport.get("memory_feedback_score"),
            "filename_score": passport.get("filename_score"),
            "final_admission_score": conf,
            "dataset_origin": passport.get("dataset_origin"),
            "dataset_origin_display": passport.get("dataset_origin_display"),
            "policy_reason_codes": passport.get("policy_reason_codes"),
            "contract_gate": passport.get("contract_gate"),
            "contract_gate_detail": passport.get("contract_gate_detail"),
            "primary_reason_code": passport.get("primary_reason_code"),
            "trust_eligibility_note": passport.get("trust_eligibility_note"),
            "second_best_domain": passport.get("second_best_domain"),
            "second_best_score": passport.get("second_best_score"),
            "semantic_best_domain": passport.get("semantic_best_domain"),
            "semantic_second_best_domain": passport.get("semantic_second_best_domain"),
            "semantic_second_best_score": passport.get("semantic_second_best_score"),
            "semantic_backend": passport.get("semantic_backend"),
            "scoring_backend_requested": passport.get("scoring_backend_requested"),
            "scoring_backend_effective": passport.get("scoring_backend_effective"),
            "embedding_model_id": passport.get("embedding_model_id"),
            "embedding_weights_source": passport.get("embedding_weights_source"),
            "semantic_scoring_warning": passport.get("semantic_scoring_warning"),
            "dataset_business_sentence": passport.get("dataset_business_sentence"),
            "domain_business_sentence": passport.get("domain_business_sentence"),
            "embedding_similarity_score": passport.get("embedding_similarity_score")
            if passport.get("embedding_similarity_score") is not None
            else passport.get("embedding_similarity_for_suggested_domain"),
            "embedding_similarity": passport.get("embedding_similarity")
            if passport.get("embedding_similarity") is not None
            else (
                passport.get("embedding_similarity_score")
                if passport.get("embedding_similarity_score") is not None
                else passport.get("embedding_similarity_for_suggested_domain")
            ),
            "ontology_concept_match_score": passport.get("ontology_concept_match_score"),
            "ontology_concept_match": passport.get("ontology_concept_match")
            if passport.get("ontology_concept_match") is not None
            else passport.get("ontology_concept_match_score"),
            "contract_fit_score": passport.get("contract_fit_score")
            if passport.get("contract_fit_score") is not None
            else passport.get("contract_coverage_score"),
            "domain_similarity_score": passport.get("domain_similarity_score"),
            "domain_readiness_score": passport.get("domain_readiness_score"),
            "reviewer_memory_score": passport.get("reviewer_memory_score"),
            "final_score": passport.get("final_score")
            if passport.get("final_score") is not None
            else passport.get("final_admission_score"),
            "semantic_ambiguity_gap": passport.get("profile_similarity_ambiguity_gap", passport.get("ambiguity_gap")),
            "admission_score_ambiguity_gap": passport.get("admission_score_ambiguity_gap", passport.get("ambiguity_gap")),
            "all_domain_scores": ranked_final,
            "all_semantic_scores": semantic_sims,
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": review_required,
            "candidate_domain_name": candidate_domain_name,
            "final_domain": best,
            "timestamp": ts,
            "explanation": explanation.strip(),
            "governance_risk_preview": passport.get("governance_risk_preview"),
            "core_expected_domain": passport.get("core_expected_domain"),
            "core_validation_status": passport.get("core_validation_status"),
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": passport.get("memory_display_mode"),
            "memory_score_for_display": passport.get("memory_score_for_display"),
            "required_coverage": passport.get("required_coverage"),
            "contract_leader_gap": passport.get("contract_leader_gap"),
            "memory_signal_active": passport.get("memory_display_mode") in {"scored", "registry"},
        }
        self._enrich_admission_row(out)
        return out

    def _build_created_domain_passport(
        self,
        csv_path: Path,
        df: pd.DataFrame,
        columns_detected: list[str],
        dataset_profile_text: str,
        domain_name: str,
        timestamp: str,
        registry_entry: dict[str, Any],
        signatures: dict[str, dict[str, set[str]]],
        memory_entries: list[dict],
    ) -> dict[str, Any]:
        cr_origin = self._dataset_origin_for_name(csv_path.name)
        stems = self._expand_column_token_stems(set(columns_detected))
        dataset_business_sentence = self._build_dataset_business_sentence(
            csv_path.name, df, columns_detected, stems
        )
        domain_business_sentence = self._build_domain_business_sentence(
            domain_name, signatures, memory_entries
        )
        emb_sim = 0.95
        if self._sentence_transformer_model and dataset_business_sentence and domain_business_sentence:
            emb_sim = float(
                self._embedding_similarities(
                    dataset_business_sentence,
                    {domain_name: domain_business_sentence},
                    self._sentence_transformer_model,
                ).get(domain_name, 0.95)
            )
        ont_score = round(self._ontology_concept_match_score(domain_name, stems), 4)
        expected_core_domain = self._expected_core_domain(csv_path.name) if cr_origin == "CORE" else None
        core_validation_status = None
        if expected_core_domain:
            core_validation_status = "PASSED" if expected_core_domain == domain_name else "WARNING"
        return {
            "passport_id": str(uuid.uuid4())[:12],
            "dataset_name": csv_path.name,
            "dataset_origin": cr_origin,
            "dataset_origin_display": self._dataset_origin_display(cr_origin),
            "dataset_profile_text": dataset_profile_text,
            "semantic_backend": self.semantic_backend,
            "scoring_backend_requested": self.scoring_backend_requested,
            "scoring_backend_effective": self.scoring_backend_effective,
            "embedding_model_id": self._sentence_transformer_model_id,
            "semantic_scoring_warning": self.semantic_scoring_warning,
            "dataset_business_sentence": dataset_business_sentence,
            "domain_business_sentence": domain_business_sentence,
            "embedding_similarity_for_suggested_domain": round(emb_sim, 4),
            "embedding_similarity_score": round(emb_sim, 4),
            "embedding_similarity": round(emb_sim, 4),
            "ontology_concept_match_score": ont_score,
            "ontology_concept_match": ont_score,
            "contract_fit_score": 0.95,
            "domain_similarity_score": round(max(0.0, min(1.0, 0.50 * emb_sim + 0.50 * ont_score)), 4),
            "domain_readiness_score": round(max(0.0, min(1.0, 0.40 * emb_sim + 0.40 * ont_score + 0.20 * 0.95)), 4),
            "reviewer_memory_score": 1.0,
            "final_score": 0.95,
            "suggested_domain": domain_name,
            "required_coverage": 1.0,
            "contract_leader_gap": 1.0,
            "semantic_best_domain": domain_name,
            "semantic_similarity_score": 0.95,
            "semantic_similarity_for_suggested_domain": 0.95,
            "profile_similarity_for_suggested_domain": 0.95,
            "ontology_concept_match_for_suggested_domain": ont_score,
            "contract_coverage_score": 0.95,
            "memory_feedback_score": 1.0,
            "reviewer_memory_for_suggested_domain": 1.0,
            "filename_score": 0.95,
            "final_admission_score": 0.95,
            "contract_gate": "PASSED",
            "contract_gate_detail": "Routed via governed created-domain registry; prior approval applies.",
            "primary_reason_code": "CREATED_DOMAIN_REGISTRY",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "ambiguity_gap": 1.0,
            "admission_score_ambiguity_gap": 1.0,
            "profile_similarity_ambiguity_gap": 1.0,
            "matched_memory_entries": [],
            "governance_risk_preview": "LOW",
            "core_expected_domain": expected_core_domain,
            "core_validation_status": core_validation_status,
            "recommended_action": "AUTO_ASSIGN_CREATED_DOMAIN",
            "admission_decision": "AUTO_ASSIGN_CREATED_DOMAIN",
            "review_required": False,
            "memory_display_mode": "registry",
            "memory_score_for_display": None,
            "explanation": (
                f'This file is routed to the approved created domain "{domain_name}" from your registry. '
                f'It matches the domain that was established from "{registry_entry.get("source_dataset_name") or "an earlier approved dataset"}".'
            ),
            "timestamp": timestamp,
            "policy_reason_codes": ["CREATED_DOMAIN_REGISTRY"],
            "admission_score_weights": {k: round(float(v), 4) for k, v in self.admission_score_weights.items()},
            "lexical_similarity_note": (
                "Registry routing bypasses normal hybrid composite scoring; prior approval applies. "
                + self._semantic_channel_user_note()
            ),
        }

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    def _resolve_admission_policy(
        self,
        final_score_best: float,
        semantic_gap: float,
        admission_leader_gap: float,
        required_coverage_ok: bool,
        governance_risk: str,
        contract_coverage_best: float,
        required_coverage_best: float,
        contract_leader_gap: float,
    ) -> tuple[str, list[str]]:
        if governance_risk == "HIGH":
            return "GOVERNANCE_TICKET_RECOMMENDED", ["GOVERNANCE_RISK_HIGH"]

        margin_ok = (
            admission_leader_gap >= 0.10
            or semantic_gap >= 0.10
            or contract_leader_gap >= 0.10
        )

        # Contract-first: strong governance fit for known domains (semantic channel must not veto alone).
        if (
            contract_coverage_best >= 0.75
            and required_coverage_best >= 0.70
            and governance_risk != "HIGH"
            and margin_ok
        ):
            return "AUTO_LOAD_ELIGIBLE", ["CONTRACT_FIRST_GOVERNANCE_MATCH"]

        if final_score_best < 0.40:
            # Very weak fit to all domains → possible new domain; else ambiguous → human review.
            if contract_coverage_best < 0.28 and required_coverage_best < 0.35:
                return "NEW_DOMAIN_CANDIDATE", ["LOW_SCORE_NEW_DOMAIN"]
            return "HUMAN_REVIEW_REQUIRED", ["LOW_COMPOSITE_AMBIGUOUS"]

        if not margin_ok:
            return "HUMAN_REVIEW_REQUIRED", ["LOW_MARGIN_AMBIGUOUS"]

        if 0.40 <= final_score_best < 0.70:
            return "HUMAN_REVIEW_REQUIRED", ["SCORE_BAND_PROVISIONAL"]

        if final_score_best >= 0.70 and margin_ok and required_coverage_ok:
            return "AUTO_LOAD_ELIGIBLE", ["HYBRID_SCORE_AND_MARGIN_OK"]

        return "HUMAN_REVIEW_REQUIRED", ["FALLBACK_REVIEW"]

    def _domain_has_reviewer_memory_for_domain(self, memory_entries: list[dict], domain: str) -> bool:
        dom = (domain or "").strip().lower()
        if not dom:
            return False
        for m in memory_entries:
            if not isinstance(m, dict):
                continue
            if str(m.get("domain_name") or "").strip().lower() != dom:
                continue
            if str(m.get("reviewer_action") or "").upper() == "REJECT":
                continue
            return True
        return False

    def _memory_for_trust_composite(self, mem_raw: float, memory_entries: list[dict], domain: str) -> float:
        """When no reviewer memory exists for a domain, avoid treating 0.5 as a penalty in the trust blend."""
        if self._domain_has_reviewer_memory_for_domain(memory_entries, domain):
            return float(mem_raw)
        return 0.78

    def _contract_gate_eval(self, contract_cov: float, required_cov: float, governance_risk: str) -> tuple[str, str]:
        """PASSED / REVIEW / FAILED for UI — independent of auto-load policy thresholds."""
        if governance_risk == "HIGH":
            return "REVIEW", "Governance risk is elevated; contract signals are evaluated alongside risk controls."
        if contract_cov >= 0.75 and required_cov >= 0.70:
            return "PASSED", "Strong alignment with required and optional contract columns for the suggested domain."
        if contract_cov < 0.35 or required_cov < 0.30:
            return "FAILED", "Insufficient overlap with the domain contract (coverage or required columns)."
        return "REVIEW", "Partial contract alignment; confirm with semantic similarity (embedding or TF-IDF), ontology match, and reviewer memory."

    def _primary_reason_code(self, reason_codes: list[str]) -> str:
        if reason_codes:
            return str(reason_codes[0])
        return "UNKNOWN"

    def _reason_code_display(self, code: str | None) -> str:
        c = str(code or "")
        if not c:
            return "—"
        return REASON_CODE_DISPLAY.get(c, c.replace("_", " ").title())

    def _trust_eligibility_note(
        self,
        admission_decision: str,
        trust_score: float,
        reason_codes: list[str],
        semantic_for_suggested: float,
        semantic_backend: str,
    ) -> str | None:
        """Explains AUTO_LOAD_ELIGIBLE when trust score is < 70% (viva-defensible)."""
        if admission_decision != "AUTO_LOAD_ELIGIBLE":
            return None
        if trust_score >= 0.70:
            return None
        codes = set(reason_codes or [])
        sem_label = (
            "embedding similarity"
            if semantic_backend == "sentence_embedding"
            else ("TF-IDF fallback similarity" if semantic_backend == "tfidf_fallback" else "TF-IDF profile similarity")
        )
        if "CONTRACT_FIRST_GOVERNANCE_MATCH" in codes:
            return f"Eligible because contract gate passed strongly, although {sem_label} is moderate."
        if semantic_for_suggested < 0.42:
            return f"Eligible because contract gate passed strongly, although {sem_label} is moderate."
        return (
            "Eligible under admission policy: trust score is below 70% but margins and governance checks passed."
        )

    def _memory_display_fields(
        self,
        memory_entries: list[dict],
        best_domain: str,
        memory_score: float,
        matched_memory: list[dict],
    ) -> dict[str, Any]:
        """UI hints: avoid showing neutral 50% when no reviewer memory applies."""
        if not memory_entries:
            return {"mode": "no_bank", "score_for_display": None}
        dom = (best_domain or "").strip().lower()
        has_domain_row = any(
            isinstance(m, dict) and str(m.get("domain_name") or "").strip().lower() == dom for m in memory_entries
        )
        if matched_memory or has_domain_row:
            return {"mode": "scored", "score_for_display": round(float(memory_score), 4)}
        return {"mode": "neutral", "score_for_display": None}

    def _governance_risk_preview(self, df: pd.DataFrame) -> str:
        if df is None or len(df) == 0:
            return "HIGH"
        n = len(df)
        null_rate = float(df.isnull().values.mean()) if len(df.columns) else 0.0
        # Softer thresholds so typical Silver products are not all HIGH for viva demos.
        if null_rate > 0.40:
            return "HIGH"
        if n <= 2 or null_rate > 0.25:
            return "HIGH"
        if n < 12 or null_rate > 0.12:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Profiles & similarity
    # ------------------------------------------------------------------
    def _build_dataset_profile_text(self, dataset_name: str, df: pd.DataFrame, columns: list[str]) -> str:
        parts = [f"dataset:{dataset_name}", "columns:" + ",".join(columns)]
        dtypes = [str(df[c].dtype) for c in df.columns[: min(40, len(df.columns))]]
        parts.append("dtypes:" + ",".join(dtypes))
        parts.append("schema_summary:" + self._schema_summary(df))
        parts.append("samples:" + self._safe_sample_summary(df))
        return " ".join(parts)

    def _schema_summary(self, df: pd.DataFrame) -> str:
        pieces = []
        for col in list(df.columns)[:25]:
            s = df[col]
            nn = s.notna().sum()
            pieces.append(f"{col}[non_null={int(nn)}]")
        return ";".join(pieces)

    def _safe_sample_summary(self, df: pd.DataFrame) -> str:
        snippets: list[str] = []
        for col in list(df.columns)[:12]:
            series = df[col].dropna()
            if series.empty:
                continue
            head = series.head(50)
            nuniq = head.nunique()
            if pd.api.types.is_numeric_dtype(series):
                snippets.append(f"{col}:num_min={float(series.min()):.4g},max={float(series.max()):.4g}")
            elif nuniq <= 6:
                vals = [self._redact_token(str(v)) for v in head.unique()[:6]]
                snippets.append(f"{col}:cats={','.join(vals)}")
            else:
                snippets.append(f"{col}:n_unique<={int(nuniq)}")
        return ";".join(snippets)[:1200]

    def _redact_token(self, value: str) -> str:
        v = value.strip()
        if "@" in v and "." in v:
            return "[EMAIL]"
        if len(v) > 32:
            return v[:29] + "..."
        return v

    def _build_domain_profile_texts(self, signatures: dict[str, dict[str, set[str]]]) -> dict[str, str]:
        memory = self._read_memory_bank()
        approved_names: dict[str, list[str]] = {}
        for m in memory:
            if not isinstance(m, dict):
                continue
            if str(m.get("reviewer_action") or "").upper() == "REJECT":
                continue
            d = str(m.get("domain_name") or "").strip().lower()
            ds = str(m.get("dataset_name") or "").strip()
            if d and ds:
                approved_names.setdefault(d, []).append(ds)

        profiles: dict[str, str] = {}
        for domain, sig in signatures.items():
            cols = sorted(sig.get("all", set()))
            contract_cols = "contract_columns:" + ",".join(cols)
            onto = "ontology_concepts:" + ",".join(sorted(DOMAIN_ONTOLOGY_TERMS.get(domain, ()))[:48])
            prof = str(sig.get("profile_rich_text") or "").strip()
            prof_blob = f" domain_profile:{prof}" if prof else ""
            schema_bits: list[str] = []
            domain_csv = self.domain_products_dir / domain / f"{domain}.csv"
            if domain_csv.is_file():
                try:
                    ddf = pd.read_csv(domain_csv, nrows=80)
                    schema_bits.append("product_schema_columns:" + ",".join([str(c).strip().lower() for c in ddf.columns]))
                except Exception:
                    pass
            mem_ds = approved_names.get(domain, [])
            mem_part = "approved_dataset_names:" + ",".join(mem_ds[-15:])
            text = f"domain:{domain} {contract_cols} {onto}{prof_blob} {' '.join(schema_bits)} {mem_part}"
            profiles[domain] = text
        return profiles

    def _semantic_similarities(self, dataset_profile: str, domain_profile_texts: dict[str, str]) -> dict[str, float]:
        if not domain_profile_texts:
            return {}
        domains = list(domain_profile_texts.keys())
        texts = [dataset_profile] + [domain_profile_texts[d] for d in domains]
        vectorizer = TfidfVectorizer(max_features=4096, ngram_range=(1, 2), lowercase=True, min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            return {d: 0.0 for d in domains}
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return {domains[i]: max(0.0, min(1.0, float(sims[i]))) for i in range(len(domains))}

    def _memory_feedback_scores(self, dataset_profile: str, memory_entries: list[dict], domains: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for d in domains:
            pos_profiles = [
                str(m.get("dataset_profile_text") or "")
                for m in memory_entries
                if isinstance(m, dict)
                and str(m.get("domain_name") or "").strip().lower() == d
                and str(m.get("reviewer_action") or "").upper() != "REJECT"
            ]
            neg_profiles = [
                str(m.get("dataset_profile_text") or "")
                for m in memory_entries
                if isinstance(m, dict)
                and str(m.get("domain_name") or "").strip().lower() == d
                and str(m.get("reviewer_action") or "").upper() == "REJECT"
            ]
            pos_sim = self._max_profile_similarity(dataset_profile, pos_profiles) if pos_profiles else 0.0
            neg_sim = self._max_profile_similarity(dataset_profile, neg_profiles) if neg_profiles else 0.0
            raw = 0.5 + 0.5 * pos_sim - 0.5 * neg_sim
            scores[d] = max(0.0, min(1.0, raw))
        return scores

    def _max_profile_similarity(self, query: str, profiles: list[str]) -> float:
        if not profiles:
            return 0.0
        texts = [query] + profiles
        vectorizer = TfidfVectorizer(max_features=2048, ngram_range=(1, 2), lowercase=True, min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            return 0.0
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return max(float(x) for x in sims) if len(sims) else 0.0

    def _matched_memory_entries_for_dataset(
        self,
        dataset_profile: str,
        memory_entries: list[dict],
        top_domain: str,
    ) -> list[dict]:
        matched: list[dict] = []
        for m in memory_entries:
            if not isinstance(m, dict):
                continue
            mp = str(m.get("dataset_profile_text") or "")
            if not mp:
                continue
            sim = self._max_profile_similarity(dataset_profile, [mp])
            if sim >= 0.08:
                matched.append(
                    {
                        "domain_name": m.get("domain_name"),
                        "dataset_name": m.get("dataset_name"),
                        "reviewer_action": m.get("reviewer_action"),
                        "similarity_score": round(float(sim), 4),
                    }
                )
        matched.sort(key=lambda x: float(x.get("similarity_score") or 0), reverse=True)
        return matched[:12]

    # ------------------------------------------------------------------
    # Contracts / ranking
    # ------------------------------------------------------------------
    def _rank_domain_contract_parts(
        self,
        csv_path: Path,
        dataset_columns: list[str],
        signatures: dict[str, dict[str, set[str]]],
    ) -> list[DomainRankParts]:
        dataset_set = set(dataset_columns)
        ranked: list[DomainRankParts] = []
        for domain, signature in signatures.items():
            domain_columns = signature.get("all", set())
            required = signature.get("required", set())
            optional = signature.get("optional", set())
            bundles = signature.get("required_bundles") or []
            if not domain_columns:
                continue
            matched = sorted(dataset_set.intersection(domain_columns))
            if bundles:
                required_coverage = max(
                    len(dataset_set.intersection(set(b))) / max(1, len(b)) for b in bundles
                )
                req_match_count = max(len(dataset_set.intersection(set(b))) for b in bundles)
            else:
                req_match_count = len(dataset_set.intersection(required))
                required_coverage = req_match_count / max(1, len(required))
            opt_match_count = len(dataset_set.intersection(optional))
            optional_coverage = opt_match_count / max(1, len(optional)) if optional else required_coverage
            raw_column_score = (0.75 * required_coverage) + (0.25 * optional_coverage)
            unmatched_dataset_cols = max(0, len(dataset_set) - len(matched))
            noise_penalty = min(0.25, unmatched_dataset_cols * 0.03)
            column_score = max(0.0, raw_column_score - noise_penalty)
            contract_coverage_score = max(0.0, min(1.0, column_score))
            filename_score = self._filename_score(csv_path.stem, domain)
            ranked.append(
                DomainRankParts(
                    domain=domain,
                    contract_coverage_score=contract_coverage_score,
                    filename_score=float(filename_score),
                    column_score=float(column_score),
                    required_coverage=float(required_coverage),
                    optional_coverage=float(optional_coverage),
                    matched_columns=matched,
                )
            )
        ranked.sort(key=lambda item: item.contract_coverage_score, reverse=True)
        return ranked

    def _merge_created_domain_signatures(self, signatures: dict[str, dict[str, set[str]]]) -> None:
        for entry in self._active_created_domains():
            name = str(entry.get("domain_name") or "").strip().lower()
            cols = entry.get("source_columns") or []
            if not name or not isinstance(cols, list):
                continue
            col_set = {str(c).strip().lower() for c in cols if str(c).strip()}
            bundles = self._required_coverage_bundles_for_domain(name, set(col_set))
            signatures[name] = {
                "required": set(col_set),
                "optional": set(),
                "all": set(col_set),
                "required_bundles": bundles if bundles else [frozenset(col_set)],
                "profile_rich_text": "",
            }

    def _match_created_domain_for_dataset(self, dataset_name: str) -> dict[str, Any] | None:
        for entry in self._active_created_domains():
            if str(entry.get("source_dataset_name") or "").strip() == dataset_name:
                return entry
        return None

    def _filename_score(self, file_stem: str, domain_name: str) -> float:
        stem_tokens = self._tokenize(file_stem)
        domain_tokens = self._tokenize(domain_name.replace("_domain", ""))
        if not stem_tokens or not domain_tokens:
            return 0.0
        overlap = stem_tokens.intersection(domain_tokens)
        if overlap:
            return 1.0
        aliases = {
            "sales_domain": {"transaction", "transactions", "orders", "order", "sales", "payment", "payments"},
            "users_domain": {"users", "user", "customer", "customers", "profile"},
            "product_domain": {"product", "products", "catalog", "inventory", "sku"},
            "shop_domain": {"shop", "shops", "store", "stores", "location", "locations", "branch"},
            "engagement_domain": {"trend", "trends", "engagement", "session", "campaign", "visit"},
            "interaction_domain": {"interaction", "interactions", "event", "events", "activity", "click", "clicks"},
            "user_preferences_domain": {"preference", "preferences", "user_preferences", "wishlist"},
        }
        domain_aliases = aliases.get(domain_name, set())
        return 0.6 if stem_tokens.intersection(domain_aliases) else 0.0

    def _required_columns(self, domain_name: str, columns: list[str]) -> set[str]:
        column_set = set(columns)
        explicit: dict[str, set[str]] = {
            "sales": {"transaction_id", "user_id", "product_id", "transaction_date"},
            "users": {"user_id", "email", "signup_ts"},
            "product": {"product_id", "shop_id", "category", "price_lkr"},
            "shop": {"shop_id", "shop_name", "location"},
            "interaction": {"interaction_id", "user_id", "product_id", "interaction_ts"},
            "engagement": {"trend_id", "trend_name", "trend_score"},
            "preferences": {"preference_id", "user_id", "updated_ts"},
        }
        for key, req_cols in explicit.items():
            if key in domain_name:
                matched_explicit = req_cols.intersection(column_set)
                if matched_explicit:
                    return matched_explicit
        id_cols = sorted([col for col in columns if col.endswith("_id")])
        time_cols = sorted([col for col in columns if any(token in col for token in ("date", "_ts", "time"))])
        selected: list[str] = []
        selected.extend(id_cols[:3])
        selected.extend([col for col in time_cols if col not in selected][:1])
        if not selected:
            selected = columns[: min(4, len(columns))]
        return set(selected)

    def _candidate_domain_name(self, dataset_name: str, columns_detected: list[str], ranked: list[DomainRankParts]) -> str:
        stop_words = {"clean", "silver", "data", "dataset", "raw", "v1", "v2", "csv", "test"}
        ordered_tokens = [token for token in re.split(r"[^a-z0-9]+", Path(dataset_name).stem.lower()) if token]
        filename_tokens = [token for token in ordered_tokens if token not in stop_words]
        if filename_tokens:
            return f"candidate_{filename_tokens[0]}"
        if ranked and ranked[0].matched_columns:
            strongest = ranked[0].matched_columns[0]
            strongest_token = self._tokenize(strongest)
            if strongest_token:
                return f"candidate_{sorted(strongest_token)[0]}"
        if columns_detected:
            fallback = self._tokenize(columns_detected[0])
            if fallback:
                return f"candidate_{sorted(fallback)[0]}"
        return "candidate_new_domain"

    def _build_passport_explanation(
        self,
        admission_decision: str,
        reason_codes: list[str],
        best_domain: str | None,
        detail: dict[str, float],
        semantic_best: str | None,
        sem_gap: float,
        admission_leader_gap: float,
        gov_risk: str,
        contract_cov: float,
        req_cov: float,
        contract_gap: float,
    ) -> str:
        """Short, reviewer-facing narrative (numeric detail lives in structured passport fields)."""
        dom = _domain_pretty_name(best_domain)
        sem_dom = _domain_pretty_name(semantic_best or best_domain)
        sem = float(detail.get("embedding_similarity_score", detail.get("semantic_similarity", 0.0)))
        ont = float(detail.get("ontology_concept_match_score", 0.0))
        ctr_q = _signal_qual_strength(contract_cov, hi=0.62, mid=0.38)
        sem_q = _signal_qual_strength(sem, hi=0.55, mid=0.35)
        ont_q = _signal_qual_strength(ont, hi=0.55, mid=0.35)
        sem_m = _margin_qual(sem_gap)
        adm_m = _margin_qual(admission_leader_gap)
        ctr_sep = _margin_qual(contract_gap, low=0.08, high=0.12)
        primary = str(reason_codes[0]) if reason_codes else ""

        if admission_decision == "GOVERNANCE_TICKET_RECOMMENDED" or gov_risk == "HIGH":
            return (
                "Data quality or sparsity looks risky for automatic routing. Open a governance ticket and improve the dataset "
                "before assigning it to a domain."
            )

        if admission_decision == "NEW_DOMAIN_CANDIDATE":
            return (
                f"No existing domain is a clear home for this dataset. The closest shape resembles {dom}, but overall fit and "
                "contract coverage are weak, so it is flagged as a new-domain (orphan) candidate for your team to define next steps."
            )

        if admission_decision == "AUTO_LOAD_ELIGIBLE":
            if primary == "CONTRACT_FIRST_GOVERNANCE_MATCH":
                return (
                    f"This dataset lines up well with the {dom} domain: contract and required-column coverage are {ctr_q}, with "
                    f"{sem_q} semantic similarity and {ont_q} ontology alignment. Margins between top candidates look {adm_m}, so automatic loading is reasonable."
                )
            return (
                f"The dataset best matches the {dom} domain with {sem_q} semantic similarity, {ont_q} ontology match, and {ctr_q} contract fit. "
                f"Separation between the top and runner-up choices is {adm_m}, which supports automatic loading."
            )

        if admission_decision == "HUMAN_REVIEW_REQUIRED":
            if primary == "LOW_MARGIN_AMBIGUOUS":
                same = (semantic_best or "").strip().lower() == (best_domain or "").strip().lower()
                lead = f"The closest match is {dom}" if same else f"Semantic signals lean toward {sem_dom}, while the top composite pick is {dom}"
                return (
                    f"{lead}. Review is recommended because margins are tight: semantic separation is {sem_m}, overall leader margin is {adm_m}, "
                    f"and contract separation between domains is {ctr_sep}. Contract fit for {dom} is {ctr_q}, so a reviewer should confirm routing."
                )
            if primary == "SCORE_BAND_PROVISIONAL":
                return (
                    f"The leading candidate is {dom}, but the overall domain score sits in a middling band where automatic loading would be premature. "
                    f"Semantic similarity is {sem_q}, ontology alignment is {ont_q}, and contract fit is {ctr_q}. A reviewer should validate the assignment."
                )
            if primary == "LOW_COMPOSITE_AMBIGUOUS":
                return (
                    "Scores are weak across every domain, so the automatic suggestion may not be reliable. "
                    "Human review is needed to choose a domain, gather more schema context, or treat this as a new-domain case."
                )
            if primary == "FALLBACK_REVIEW":
                return (
                    f"Automatic routing to {dom} could not be confirmed under policy. Have a reviewer validate the fit or choose a different domain."
                )
            return (
                f"A reviewer should look at this dataset before loading. The current best match is {dom}, with {sem_q} semantic similarity "
                f"and {ctr_q} contract fit for that choice."
            )

        return (
            f"Assessment outcome is {admission_decision.replace('_', ' ').lower()}. The closest domain match is {dom}. "
            "See the structured scores on this passport for details."
        )

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------
    def _silver_csv_files(self) -> list[Path]:
        if not self.silver_dir.exists():
            return []
        return sorted([path for path in self.silver_dir.glob("*.csv") if path.is_file()], key=lambda p: p.name.lower())

    def _domain_signatures(self) -> dict[str, dict[str, set[str]]]:
        signatures: dict[str, dict[str, set[str]]] = {}
        if not self.contracts_dir.exists():
            return signatures
        for contract_file in self.contracts_dir.glob("*.yml"):
            domain = contract_file.stem.lower()
            payload = self._load_contract_yaml(contract_file)
            columns = self._contract_columns_from_payload(payload)
            if not columns:
                continue
            all_c = set(columns)
            bundles = self._required_coverage_bundles_for_domain(domain, all_c)
            required_union: set[str] = set()
            for b in bundles:
                required_union |= set(b)
            if not required_union:
                required_union = self._required_columns(domain_name=domain, columns=columns)
            optional = all_c - required_union
            profile_rich = self._domain_profile_rich_text(payload)
            signatures[domain] = {
                "required": required_union,
                "optional": optional,
                "all": all_c,
                "required_bundles": bundles,
                "profile_rich_text": profile_rich,
            }
        return signatures

    def _contract_columns(self, contract_file: Path) -> list[str]:
        return self._contract_columns_from_payload(self._load_contract_yaml(contract_file))

    def _dataset_schema(self, csv_path: Path) -> tuple[list[str], int]:
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            return [], 0
        cols = [str(col).strip().lower() for col in list(df.columns)]
        return cols, int(len(df))

    def _read_audit_rows(self) -> list[dict]:
        if not self.audit_log_path.exists():
            return []
        try:
            payload = json.loads(self.audit_log_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _append_audit_rows(self, new_rows: list[dict]) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._read_audit_rows()
        combined = list(new_rows) + existing
        self.audit_log_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    def _read_memory_bank(self) -> list[dict]:
        if not self.domain_memory_path.exists():
            return []
        try:
            data = json.loads(self.domain_memory_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _append_memory_bank(self, record: dict[str, Any]) -> None:
        rows = self._read_memory_bank()
        rows.append(record)
        self.domain_memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.domain_memory_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _clear_memory_bank(self) -> bool:
        if self.domain_memory_path.exists():
            self.domain_memory_path.unlink(missing_ok=True)
            return True
        return False

    def _append_review_decision(self, record: dict[str, Any]) -> None:
        rows: list[dict] = []
        if self.review_decisions_path.exists():
            try:
                payload = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    rows = payload
            except Exception:
                rows = []
        rows.append(record)
        self.review_decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.review_decisions_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _append_ticket(self, record: dict[str, Any]) -> None:
        rows: list[dict] = []
        if self.review_tickets_path.exists():
            try:
                payload = json.loads(self.review_tickets_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    rows = payload
            except Exception:
                rows = []
        rows.append(record)
        self.review_tickets_path.parent.mkdir(parents=True, exist_ok=True)
        self.review_tickets_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _read_created_registry(self) -> list[dict]:
        if not self.created_domain_registry_path.exists():
            return []
        try:
            data = json.loads(self.created_domain_registry_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _write_created_registry(self, rows: list[dict]) -> None:
        self.created_domain_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.created_domain_registry_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _active_created_domains(self) -> list[dict]:
        return [x for x in self._read_created_registry() if isinstance(x, dict) and x.get("status") == "ACTIVE"]

    def _upsert_created_domain_registry(
        self,
        domain_name: str,
        source_dataset_name: str,
        source_columns: list[str],
        detection_run_id: str,
    ) -> None:
        reg = self._read_created_registry()
        now = datetime.now().isoformat(timespec="seconds")
        entry = {
            "domain_id": str(uuid.uuid4())[:12],
            "domain_name": domain_name,
            "source_dataset_name": source_dataset_name,
            "source_columns": source_columns,
            "created_from_candidate": True,
            "detection_run_id": detection_run_id,
            "status": "ACTIVE",
            "created_at": now,
            "deleted_at": None,
            "created_by": "silver_to_domain_loader",
            "is_system_domain": False,
        }
        replaced = False
        for i, item in enumerate(reg):
            if isinstance(item, dict) and str(item.get("domain_name") or "").lower() == domain_name.lower():
                reg[i] = {**item, **entry, "status": "ACTIVE"}
                replaced = True
                break
        if not replaced:
            reg.append(entry)
        self._write_created_registry(reg)

    def _create_domain_folder(self, domain_name: str, source_csv: Path) -> None:
        folder = self.domain_products_dir / domain_name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{domain_name}.csv"
        target.write_bytes(source_csv.read_bytes())

    def _normalize_domain_name(self, value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        return raw if raw.endswith("_domain") else f"{raw}_domain"

    def _read_materialization_log(self) -> list[dict]:
        if not self.materialization_log_path.exists():
            return []
        try:
            data = json.loads(self.materialization_log_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _append_materialization_record(self, record: dict[str, Any]) -> None:
        rows = self._read_materialization_log()
        rows.append(record)
        self.materialization_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.materialization_log_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _latest_loading_status(self, dataset_name: str, target_domain: str) -> str:
        if not dataset_name or not target_domain:
            return "NOT_LOADED"
        nt = self._normalize_domain_name(target_domain).lower()
        matched = [
            r
            for r in self._read_materialization_log()
            if isinstance(r, dict)
            and str(r.get("dataset_name") or "") == dataset_name
            and self._normalize_domain_name(str(r.get("target_domain") or "")).lower() == nt
        ]
        if not matched:
            return "NOT_LOADED"
        matched.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        return str(matched[0].get("loading_status") or "NOT_LOADED")

    def _loading_status_display(self, code: str) -> str:
        labels = {
            "NOT_LOADED": "Not loaded",
            "LOADED_TO_DOMAIN": "Loaded to domain",
            "LOAD_FAILED": "Load failed",
            "ALREADY_GOVERNED": "Already governed",
        }
        return labels.get(str(code), str(code))

    def _admission_decision_display(self, decision: str | None) -> str:
        d = str(decision or "")
        mapping = {
            "AUTO_LOAD_ELIGIBLE": "Eligible for domain loading",
            "AUTO_ASSIGN_CREATED_DOMAIN": "Eligible (created domain)",
            "HUMAN_REVIEW_REQUIRED": "Human review required",
            "NEW_DOMAIN_CANDIDATE": "New domain candidate",
            "GOVERNANCE_TICKET_RECOMMENDED": "Governance ticket recommended",
        }
        return mapping.get(d, d or "—")

    def _find_audit_row_by_passport(self, passport_id: str, dataset_name: str) -> dict | None:
        for row in self._read_audit_rows():
            if not isinstance(row, dict):
                continue
            if str(row.get("dataset_name") or "") != dataset_name:
                continue
            pp = row.get("admission_passport") if isinstance(row.get("admission_passport"), dict) else {}
            if str(pp.get("passport_id") or "") == str(passport_id):
                return row
        return None

    def _latest_audit_row_for_dataset(self, dataset_name: str) -> dict | None:
        for row in self._read_audit_rows():
            if not isinstance(row, dict):
                continue
            if str(row.get("dataset_name") or "") != str(dataset_name or ""):
                continue
            return row
        return None

    def _read_review_decisions_flat(self) -> list[dict]:
        if not self.review_decisions_path.exists():
            return []
        try:
            data = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _review_allows_materialization(self, dataset_name: str, target_domain: str) -> bool:
        nt = self._normalize_domain_name(target_domain).lower()
        positive = {
            "APPROVE",
            "APPROVE_PROVISIONAL",
            "CHANGE_DOMAIN",
            "VALIDATE_CANDIDATE",
            "CREATE_DOMAIN_AFTER_APPROVAL",
        }
        for r in reversed(self._read_review_decisions_flat()):
            if not isinstance(r, dict):
                continue
            if str(r.get("dataset_name") or "") != dataset_name:
                continue
            action = str(r.get("reviewer_action") or "").upper()
            if action not in positive:
                continue
            ap = self._normalize_domain_name(str(r.get("approved_domain") or "")).lower()
            if ap == nt:
                return True
        return False

    def _can_apply_materialization(self, row: dict) -> bool:
        if row.get("dataset_origin") == "CORE":
            return False
        if row.get("loading_status") in {"LOADED_TO_DOMAIN", "ALREADY_GOVERNED"}:
            return False
        decision = str(row.get("admission_decision") or row.get("action") or "")
        dataset = str(row.get("dataset_name") or "")
        target = str(row.get("best_domain") or "")
        if not target:
            return False
        if decision in {"AUTO_LOAD_ELIGIBLE", "AUTO_ASSIGN_CREATED_DOMAIN"}:
            return True
        if decision in {"HUMAN_REVIEW_REQUIRED", "NEW_DOMAIN_CANDIDATE", "GOVERNANCE_TICKET_RECOMMENDED"}:
            return self._review_allows_materialization(dataset, target)
        return False

    def _resolve_domain_product_dir(self, domain_name: str) -> Path:
        norm = self._normalize_domain_name(domain_name)
        if not norm:
            raise ValueError("Invalid domain name.")
        base = self.domain_products_dir
        base.mkdir(parents=True, exist_ok=True)
        for child in base.iterdir():
            if child.is_dir() and child.name.lower() == norm.lower():
                return child
        out = base / norm
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _enrich_admission_row(self, row: dict) -> None:
        decision = str(row.get("admission_decision") or row.get("action") or "")
        dataset = str(row.get("dataset_name") or "")
        target = str(row.get("best_domain") or "")
        pp = row.get("admission_passport") if isinstance(row.get("admission_passport"), dict) else {}
        origin = row.get("dataset_origin") or pp.get("dataset_origin") or self._dataset_origin_for_name(dataset)
        row["dataset_origin"] = origin
        row["dataset_origin_display"] = self._dataset_origin_display(origin)

        ls_raw = self._latest_loading_status(dataset, target)
        if origin == "CORE":
            row["loading_status"] = "ALREADY_GOVERNED"
            row["loading_status_display"] = self._loading_status_display("ALREADY_GOVERNED")
        else:
            row["loading_status"] = ls_raw
            row["loading_status_display"] = self._loading_status_display(ls_raw)
        row["admission_decision_display"] = self._admission_decision_display(decision)
        row["can_apply_to_domain"] = self._can_apply_materialization(dict(row))

        cg = row.get("contract_gate") or pp.get("contract_gate")
        if not cg:
            cc = float(row.get("contract_coverage_score") if row.get("contract_coverage_score") is not None else pp.get("contract_coverage_score") or 0)
            rc_val = row.get("required_coverage")
            if rc_val is None:
                rc_val = pp.get("required_coverage")
            rc_val = float(rc_val or 0)
            gr = str(row.get("governance_risk_preview") or pp.get("governance_risk_preview") or "LOW")
            cg, _detail_infer = self._contract_gate_eval(cc, rc_val, gr)
        row["contract_gate"] = cg
        gate_labels = {"PASSED": "Passed", "REVIEW": "Review", "FAILED": "Failed"}
        row["contract_gate_display"] = gate_labels.get(str(cg or ""), str(cg or "—"))

        rcodes = row.get("policy_reason_codes")
        if not isinstance(rcodes, list):
            rcodes = pp.get("policy_reason_codes") if isinstance(pp.get("policy_reason_codes"), list) else []
        prc = row.get("primary_reason_code") or pp.get("primary_reason_code")
        if not prc:
            prc = self._primary_reason_code(rcodes)
        row["primary_reason_code"] = prc
        row["primary_reason_code_display"] = self._reason_code_display(prc)

        trust = float(row.get("final_admission_score") if row.get("final_admission_score") is not None else row.get("confidence_score") or 0)
        sem_sug = row.get("semantic_similarity_for_suggested_domain")
        if sem_sug is None:
            sem_sug = pp.get("semantic_similarity_for_suggested_domain")
        if sem_sug is None:
            sem_sug = row.get("semantic_similarity_score") if row.get("semantic_similarity_score") is not None else pp.get("semantic_similarity_score")
        sem_sug = float(sem_sug or 0)
        tn = row.get("trust_eligibility_note")
        if tn is None and isinstance(pp, dict):
            tn = pp.get("trust_eligibility_note")
        if tn is None and decision == "AUTO_LOAD_ELIGIBLE":
            sb = str(pp.get("semantic_backend") or row.get("semantic_backend") or "tfidf")
            tn = self._trust_eligibility_note(
                decision, trust, rcodes if isinstance(rcodes, list) else [], sem_sug, sb
            )
        row["trust_eligibility_note"] = tn

    def _tokenize(self, value: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if token}
