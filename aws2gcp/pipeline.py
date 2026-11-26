from dataclasses import dataclass

from . import moving_truck, price_tag, receipt as receipt_mod, sorter, twin_finder

CONFIDENCES = ("exact", "close", "assumed", "human")


@dataclass
class Result:
    receipt: object
    lines: list
    totals: dict
    migration: dict
    settings: dict
    prices_meta: dict


def run(paths, data: dict, settings: dict) -> Result:
    data = dict(data, settings=settings)
    rec = receipt_mod.read_receipt(paths, settings)
    lines = rec.usage()

    sorter.sort_lines(lines, data)

    vm_ids = {l.resource_id for l in lines if l.kind == "vm" and l.resource_id}
    vm_hours = sum(l.monthly_quantity for l in lines if l.kind == "vm")
    vm_count = len(vm_ids) or max(1, round(vm_hours / settings["hours_per_month"]))
    twin_finder.find_twins(lines, data, {"vm_count": vm_count})

    price_tag.price_lines(lines, data["prices"], settings)
    _gke_free_cluster(lines, data["prices"], settings)
    _support(lines, settings)

    totals = _totals(lines, rec, settings)

    migration = moving_truck.estimate(lines, rec, totals, settings)

    return Result(rec, lines, totals, migration, settings, data["prices"]["meta"])


def _gke_free_cluster(lines, prices, settings):
    if not settings["gcp"]["gke_free_cluster"]:
        return
    credit = prices["gke"]["cluster_hour"] * settings["hours_per_month"]
    for l in lines:
        if l.kind == "k8s_cluster" and l.gcp_likely > 0:
            cut = min(credit, l.gcp_likely)
            l.gcp_low, l.gcp_likely, l.gcp_high = (max(0.0, v - cut) for v in (l.gcp_low, l.gcp_likely, l.gcp_high))
            l.note("price", f"GKE free tier credit -${cut:.2f} (one zonal/Autopilot cluster per billing account)")
            return


def _support(lines, settings):
    rows = [l for l in lines if l.price_rule == "support"]
    if not rows:
        return
    g = settings["gcp"]
    base = sum(l.gcp_likely for l in lines if l.price_rule != "support")
    cost = max(g["support_min_monthly"], base * g["support_pct"])
    band = settings["confidence_band"]["assumed"]
    first = rows[0]
    first.gcp_low, first.gcp_likely, first.gcp_high = cost * (1 - band), cost, cost * (1 + band)
    first.note("price", f"GCP support = max(${g['support_min_monthly']}, {g['support_pct']:.0%} x ${base:.2f})")


def _totals(lines, rec, settings) -> dict:
    aws = sum(l.monthly_aws for l in lines)
    t = {
        "aws_monthly": aws,
        "aws_on_demand_monthly": sum(l.on_demand * l.scale for l in lines),
        "gcp_low": sum(l.gcp_low for l in lines),
        "gcp_likely": sum(l.gcp_likely for l in lines),
        "gcp_high": sum(l.gcp_high for l in lines),
        "by_confidence": {c: sum(l.monthly_aws for l in lines if l.confidence == c) for c in CONFIDENCES},
        "buckets_monthly": rec.bucket_monthly(),
        "buckets_raw": rec.bucket_totals(),
        "reconcile_diff": rec.reconcile(),
        "raw_total": rec.raw_total,
    }
    covered = sum(l.monthly_aws for l in lines if l.line_type in ("DiscountedUsage", "SavingsPlanCoveredUsage"))
    t["commitment_coverage"] = covered / aws if aws else 0.0
    aws_set = settings["aws"]
    t["aws_compare"] = aws * (1 - aws_set["retention_discount_pct"])
    t["aws_cleaned_up"] = t["aws_compare"] * (1 - aws_set["optimisation_pct"])
    t["coverage"] = {c: (v / aws if aws else 0.0) for c, v in t["by_confidence"].items()}
    t["credits_monthly"] = t["buckets_monthly"].get("credit", 0.0)
    return t
