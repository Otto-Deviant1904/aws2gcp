from datetime import datetime, timedelta

ARCHIVE_CODES = {"Glacier", "GDA", "GIR", "INT-AA", "INT-DAA"}


def estimate(lines: list, receipt, totals: dict, settings: dict) -> dict:
    mig = settings["migration"]
    parts = []

    stored_gb = sum(l.monthly_quantity for l in lines if l.kind in ("s3_storage", "disk", "db_storage"))
    egress = 0.0 if mig["egress_waived"] else stored_gb * mig["egress_usd_per_gb"]
    parts.append(("Data egress out of AWS", egress,
                  f"{stored_gb:,.0f} GB x ${mig['egress_usd_per_gb']}/GB"
                  + (" (waived)" if mig["egress_waived"] else "")))

    archive_gb = sum(l.monthly_quantity for l in lines
                     if l.kind == "s3_storage" and l.details.get("s3class") in ARCHIVE_CODES)
    if archive_gb:
        parts.append(("Reading back archived S3 data", archive_gb * mig["archive_retrieval_usd_per_gb"],
                      f"{archive_gb:,.0f} GB x ${mig['archive_retrieval_usd_per_gb']}/GB"))

    lab = mig["labor"]
    resources = {}
    for l in lines:
        if l.group in lab["hours_per_resource"] and l.confidence != "human":
            resources.setdefault(l.group, set()).add(l.resource_id or l.usage_type)
    human_items = {(l.product, l.usage_type) for l in lines if l.confidence == "human"}
    hours = lab["base_project_hours"]
    detail = [f"base {lab['base_project_hours']} h"]
    for group, ids in sorted(resources.items()):
        h = len(ids) * lab["hours_per_resource"][group]
        hours += h
        detail.append(f"{len(ids)} {group} x {lab['hours_per_resource'][group]} h")
    if human_items:
        hours += len(human_items) * lab["hours_per_human_item"]
        detail.append(f"{len(human_items)} needs-a-human x {lab['hours_per_human_item']} h")
    parts.append(("Engineering labor", hours * lab["rate_usd_per_hour"],
                  f"{hours:,.0f} h x ${lab['rate_usd_per_hour']}/h ({', '.join(detail)})"))

    overlap = totals["gcp_likely"] * mig["overlap_months"]
    parts.append(("Running both clouds (overlap)", overlap,
                  f"{mig['overlap_months']} month(s) of GCP while AWS still runs"))

    stranded, notes = _stranded(receipt, mig["overlap_months"])
    parts.append(("Unused AWS commitments after move", stranded, notes))

    likely = sum(p[1] for p in parts)
    credits = settings["gcp"]["credits_usd"]
    band = mig["band"]
    net = max(0.0, likely - credits)
    return {
        "parts": parts,
        "gross": likely,
        "credits": credits,
        "low": max(0.0, likely * (1 - band) - credits),
        "likely": net,
        "high": max(0.0, likely * (1 + band) - credits),
        "labor_hours": hours,
        "stored_gb": stored_gb,
    }


def _stranded(receipt, overlap_months: int):
    fees = [l for l in receipt.lines if l.line_type in ("RIFee", "SavingsPlanRecurringFee")]
    if not fees:
        return 0.0, "no RI / Savings Plan fees in the bill"
    total, missing = 0.0, 0
    for l in fees:
        if not l.commitment_end:
            missing += 1
            continue
        end = datetime.fromisoformat(l.commitment_end.replace("Z", "+00:00"))
        period_end = receipt.periods[l.period]["end"]
        move_date = period_end + timedelta(days=30.44 * overlap_months)
        months_left = max(0.0, (end - move_date).days / 30.44)
        total += l.unblended * l.scale * months_left
    note = "monthly fee x months left after the move"
    if missing:
        note += f"; {missing} fee row(s) had no end date and were skipped"
    return total, note
