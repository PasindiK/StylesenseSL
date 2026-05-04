#!/usr/bin/env python3
"""
Run SilverToDomainLoaderService admission on validation datasets (real CSV when present under
Test-upload-data, otherwise a one-row synthetic file from domain_admission_validation.csv).

Prints expected vs predicted, scores by domain, top-2, ambiguity gap, decision, and pass/fail
against expected_outcome / expected_domain rules (same semantics as evaluate_embedding_domain_similarity.py).
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
SERVICE_SRC = THIS_DIR.parent / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from silver_to_domain_loader import SilverToDomainLoaderService  # noqa: E402


def _synthetic_csv(name: str, cols: list[str]) -> Path:
    tmp = Path(tempfile.gettempdir()) / f"dm_diag_{uuid.uuid4().hex[:10]}_{name}"
    pd.DataFrame([{c: "" for c in cols}]).to_csv(tmp, index=False)
    return tmp


def _pass_fail(gold: dict[str, str], row: dict[str, Any]) -> tuple[bool, str]:
    outcome = str(gold.get("expected_outcome") or "").strip().upper()
    pred = str(row.get("best_domain") or "").strip()
    dec = str(row.get("admission_decision") or "").strip()
    exp_dom = str(gold.get("expected_domain") or "").strip()

    if outcome == "EXISTING_DOMAIN":
        ok = pred == exp_dom
        return ok, "top1_domain_match" if ok else f"expected_domain={exp_dom} got={pred}"
    if outcome == "ORPHAN_DOMAIN_CANDIDATE":
        ok = dec == "NEW_DOMAIN_CANDIDATE"
        return ok, "orphan_decision" if ok else f"expected NEW_DOMAIN_CANDIDATE got={dec}"
    if outcome == "REVIEW_REQUIRED":
        ok = dec in {"HUMAN_REVIEW_REQUIRED", "GOVERNANCE_TICKET_RECOMMENDED"}
        return ok, "review_routing" if ok else f"expected review decision got={dec}"
    return True, "no_rule"


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-dataset domain admission diagnostic.")
    ap.add_argument("--data-root", type=Path, default=THIS_DIR.parent / "data")
    ap.add_argument(
        "--validation-csv",
        type=Path,
        default=THIS_DIR.parent / "data" / "evaluation" / "domain_admission_validation.csv",
    )
    ap.add_argument(
        "--upload-dir",
        type=Path,
        default=THIS_DIR.parent / "data" / "Data" / "Test-upload-data",
    )
    args = ap.parse_args()
    data_root = args.data_root.resolve()
    val_path = args.validation_csv.resolve()
    upload_dir = args.upload_dir.resolve()

    svc = SilverToDomainLoaderService(data_root=data_root)
    signatures = svc._domain_signatures()
    svc._merge_created_domain_signatures(signatures)
    domain_profile_texts = svc._build_domain_profile_texts(signatures)
    memory_entries = svc._read_memory_bank()
    run_id = "diag"
    ts = datetime.now().isoformat(timespec="seconds")

    rows_gold: list[dict[str, str]] = []
    with val_path.open(newline="", encoding="utf-8") as f:
        rows_gold.extend(csv.DictReader(f))

    temps: list[Path] = []
    print("=== Domain admission diagnostic ===")
    print("data_root:", data_root)
    print("validation_csv:", val_path)
    print("upload_dir:", upload_dir)
    print("semantic_backend:", svc.semantic_backend, "| scoring_backend_effective:", svc.scoring_backend_effective)
    print("admission_score_weights:", svc.admission_score_weights)
    if svc.semantic_scoring_warning:
        print("WARNING:", svc.semantic_scoring_warning)
    print()

    for gold in rows_gold:
        name = str(gold.get("dataset_name") or "").strip()
        up = upload_dir / name
        if up.is_file():
            csv_path = up
            src = "upload_csv"
        else:
            cols = [c.strip().lower() for c in str(gold.get("columns_text") or "").split() if c.strip()]
            csv_path = _synthetic_csv(name, cols)
            temps.append(csv_path)
            src = "synthetic_row"

        df_one = pd.read_csv(csv_path)
        cols_lower = [str(c).strip().lower() for c in df_one.columns]
        row = svc._evaluate_dataset(
            csv_path,
            run_id,
            ts,
            signatures,
            domain_profile_texts,
            memory_entries,
            semantic_channel="active",
            admission_weights=None,
        )
        ok, rule = _pass_fail(gold, row)
        passport = row.get("admission_passport") or {}
        all_scores = row.get("all_domain_scores") or {}
        all_sem = row.get("all_semantic_scores") or {}
        ranked = sorted(all_scores.items(), key=lambda kv: float(kv[1]), reverse=True)
        top2 = ranked[:2]
        gap = float(row.get("admission_score_ambiguity_gap") or passport.get("ambiguity_gap") or 0.0)

        parts = svc._rank_domain_contract_parts(csv_path, cols_lower, signatures)
        contract_by_domain = {p.domain: float(p.contract_coverage_score) for p in parts}
        stems = svc._expand_column_token_stems(set(cols_lower))

        print(f"--- {name} ({src}) ---")
        print("  expected_outcome:", gold.get("expected_outcome"), "| expected_domain:", gold.get("expected_domain"))
        print("  predicted_domain:", row.get("best_domain"), "| admission_decision:", row.get("admission_decision"))
        print("  final_score (best):", row.get("final_admission_score"), "| ambiguity_gap:", gap)
        print("  top2 composite:", top2)
        print("  embedding/semantic sim (all domains):")
        for d in sorted(all_sem.keys()):
            print(f"    {d}: {float(all_sem[d]):.4f}")
        print("  ontology match (all domains):")
        for d in sorted(signatures.keys()):
            print(f"    {d}: {svc._ontology_concept_match_score(d, stems):.4f}")
        print("  contract coverage (all domains):")
        for d in sorted(contract_by_domain.keys()):
            print(f"    {d}: {contract_by_domain[d]:.4f}")
        print("  suggested passport — ontology:", passport.get("ontology_concept_match_score"), "contract:", passport.get("contract_coverage_score"))
        print("  PASS" if ok else "  FAIL", f"({rule})")
        print()

    for tp in temps:
        try:
            tp.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
