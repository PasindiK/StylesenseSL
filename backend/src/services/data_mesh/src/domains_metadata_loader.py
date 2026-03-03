import pandas as pd
from pathlib import Path
import yaml
import os

def load_domains_metadata(data_mesh_path):
    # Load metadata CSV if available
    meta_csv = Path(data_mesh_path) / "metadata/data_mesh_metadata.csv"
    meta = pd.read_csv(meta_csv) if meta_csv.exists() else pd.DataFrame()
    # Load contract status and schema version from Contracts folder
    contracts_dir = Path(data_mesh_path).parent / "Contracts"
    contracts = {}
    if contracts_dir.exists():
        for f in contracts_dir.glob("*.yml"):
            with open(f, "r") as file:
                yml = yaml.safe_load(file)
                domain = f.stem.replace("_domain", "").lower()  # Always lowercase
                contracts[domain] = {
                    "schema_version": yml.get("schema_version", "v1"),
                    "contract_status": "Valid" if yml else "Unknown",
                    "contract_file": str(f)
                }
    return meta, contracts

def get_domains_metadata(data_mesh_path, health_dict):
    meta, contracts = load_domains_metadata(data_mesh_path)
    domains = []
    for domain in health_dict:
        # Normalize domain name for metadata and contract lookup
        domain_norm = domain.lower().replace('_domain', '')
        d = {"domain": domain.replace("_domain", "")}
        # Owner/contact from metadata
        if not meta.empty:
            row = meta[meta["domain_name"].str.replace('_domain','').str.lower() == domain_norm]
            if not row.empty:
                d["owner"] = row.iloc[0].get("owner", "-") if "owner" in row.columns else "-"
                d["contact"] = row.iloc[0].get("contact", "-") if "contact" in row.columns else "-"
                d["sla"] = row.iloc[0].get("sla", "-") if "sla" in row.columns else "-"
            else:
                d["owner"] = d["contact"] = d["sla"] = "-"
        else:
            d["owner"] = d["contact"] = d["sla"] = "-"
        # Contract/schema info
        c = contracts.get(domain_norm, {})  # Always lookup lowercased
        d["schema_version"] = c.get("schema_version", "v1")
        d["contract_status"] = c.get("contract_status", "Unknown")
        d["contract_file"] = c.get("contract_file", None)
        # Health info
        h = health_dict[domain]
        d["last_modified"] = h.get("last_modified", "-")
        d["health"] = "Healthy" if h.get("row_count", 0) > 0 and not any(v > 0 for v in h.get("null_counts", {}).values()) else "Warning"
        domains.append(d)
    return domains
