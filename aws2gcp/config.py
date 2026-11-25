import copy
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).parent / "data"


def load_yaml(name: str, override: str | None = None) -> dict:
    path = Path(override) if override else DATA_DIR / name
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_all(prices_file: str | None = None, assumptions_file: str | None = None) -> dict:
    return {
        "prices": load_yaml("prices.yaml", prices_file),
        "settings": load_yaml("assumptions.yaml", assumptions_file),
        "rules": load_yaml("sorter_rules.yaml")["rules"],
        "services": load_yaml("services.yaml"),
        "regions": load_yaml("regions.yaml"),
    }


FLAG_PATHS = {
    "gcp_cud": ("gcp", "cud"),
    "network_tier": ("gcp", "network_tier"),
    "perf_factor": ("gcp", "perf_factor"),
    "gke_free_cluster": ("gcp", "gke_free_cluster"),
    "gcp_credits": ("gcp", "credits_usd"),
    "aws_retention_discount": ("aws", "retention_discount_pct"),
    "overlap_months": ("migration", "overlap_months"),
    "egress_waived": ("migration", "egress_waived"),
    "labor_rate": ("migration", "labor", "rate_usd_per_hour"),
}


def apply_flags(settings: dict, flags: dict) -> dict:
    out = copy.deepcopy(settings)
    for flag, value in flags.items():
        if value is None or flag not in FLAG_PATHS:
            continue
        *parents, leaf = FLAG_PATHS[flag]
        node = out
        for p in parents:
            node = node[p]
        node[leaf] = value
    return out


def flag_for(path: tuple) -> str:
    for flag, p in FLAG_PATHS.items():
        if p == path:
            if flag == "gke_free_cluster":
                return "--no-gke-free-cluster"
            return "--" + flag.replace("_", "-")
    return "edit assumptions.yaml"
