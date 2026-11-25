import csv
import gzip
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import Line

BUCKET_OF_TYPE = {
    "Usage": "workload",
    "DiscountedUsage": "workload",
    "SavingsPlanCoveredUsage": "workload",
    "Tax": "tax",
    "Credit": "credit",
    "Refund": "refund",
    "BundledDiscount": "discount",
    "Discount": "discount",
    "EdpDiscount": "discount",
    "PrivateRateDiscount": "discount",
    "RIFee": "commitment",
    "Fee": "commitment",
    "SavingsPlanUpfrontFee": "commitment",
    "SavingsPlanRecurringFee": "commitment",
    "SavingsPlanNegation": "sp_negation",  # ignore these, else SP gets counted twice
}

REQUIRED = [
    "lineitemlineitemtype", "lineitemusagetype", "lineitemunblendedcost",
    "lineitemusageamount", "lineitemproductcode",
    "billbillingperiodstartdate", "billbillingperiodenddate",
]


class ReceiptError(Exception):
    pass


@dataclass
class Receipt:
    lines: list
    raw_total: float
    periods: dict
    warnings: list = field(default_factory=list)

    def workload(self) -> list:
        return [l for l in self.lines if l.bucket == "workload"]

    def bucket_totals(self) -> dict:
        totals = {}
        for l in self.lines:
            totals[l.bucket] = totals.get(l.bucket, 0.0) + l.unblended
        return totals

    def bucket_monthly(self) -> dict:
        totals = {}
        for l in self.lines:
            totals[l.bucket] = totals.get(l.bucket, 0.0) + l.unblended * l.scale
        return totals

    def reconcile(self) -> float:
        return abs(sum(self.bucket_totals().values()) - self.raw_total)


def norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", col.lower())


def num(value: str) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def when(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def find_files(paths) -> list:
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.name.endswith((".csv", ".csv.gz")))
        elif p.exists():
            files.append(p)
        else:
            raise ReceiptError(f"File not found: {p}")
    if not files:
        raise ReceiptError("No .csv or .csv.gz files found.")
    return files


def open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", newline="", encoding="utf-8")
    return open(path, newline="", encoding="utf-8")


def read_receipt(paths, settings: dict) -> Receipt:
    fx = settings["fx_to_usd"]
    lines, raw_total, periods, warnings = [], 0.0, {}, []

    for path in find_files(paths):
        with open_text(path) as fh:
            reader = csv.DictReader(fh)
            present = {norm(c) for c in (reader.fieldnames or [])}
            missing = [c for c in REQUIRED if c not in present]
            if missing:
                raise ReceiptError(
                    f"{path.name} does not look like a Cost and Usage Report "
                    f"(missing: {', '.join(missing)}). The console 'Bills -> Download CSV' "
                    "export is not supported yet; use the CUR files from your S3 bucket."
                )
            for row_no, row in enumerate(reader, start=2):
                r = {norm(k): (v or "").strip() for k, v in row.items() if k}
                line = _make_line(r, fx, f"{path.name}:{row_no}")
                raw_total += line.unblended
                lines.append(line)

                p = periods.setdefault(line.period, {
                    "start": when(r["billbillingperiodstartdate"]),
                    "end": when(r["billbillingperiodenddate"]),
                    "last_usage": None,
                })
                # only real usage rows. tax rows end on the last day of month even if month not done
                if line.bucket != "workload":
                    continue
                usage_end = when(r.get("lineitemusageenddate", ""))
                if usage_end and (p["last_usage"] is None or usage_end > p["last_usage"]):
                    p["last_usage"] = usage_end

    _scale_to_standard_month(lines, periods, settings["hours_per_month"], warnings)
    receipt = Receipt(lines, raw_total, periods, warnings)

    diff = receipt.reconcile()
    if diff > 0.005:
        raise ReceiptError(f"Reconciliation failed: buckets differ from bill total by ${diff:.4f}")
    return receipt


def _make_line(r: dict, fx: dict, source: str) -> Line:
    currency = r.get("lineitemcurrencycode") or "USD"
    if currency not in fx:
        raise ReceiptError(f"Currency {currency} unknown; add it to fx_to_usd in assumptions.yaml")
    rate = fx[currency]

    line_type = r["lineitemlineitemtype"]
    unblended = num(r["lineitemunblendedcost"]) * rate

    effective = unblended
    if line_type == "DiscountedUsage" and r.get("reservationeffectivecost"):
        effective = num(r["reservationeffectivecost"]) * rate
    elif line_type == "SavingsPlanCoveredUsage" and r.get("savingsplansavingsplaneffectivecost"):
        effective = num(r["savingsplansavingsplaneffectivecost"]) * rate

    on_demand = num(r["pricingpublicondemandcost"]) * rate if r.get("pricingpublicondemandcost") else unblended

    line = Line(
        line_type=line_type,
        bucket=BUCKET_OF_TYPE.get(line_type, "other"),
        product=r["lineitemproductcode"],
        usage_type=r["lineitemusagetype"],
        operation=r.get("lineitemoperation", ""),
        amount=num(r["lineitemusageamount"]),
        unit=r.get("pricingunit", ""),
        unblended=unblended,
        effective=effective,
        on_demand=on_demand,
        resource_id=r.get("lineitemresourceid", ""),
        account=r.get("lineitemusageaccountid", ""),
        region_col=r.get("productregion", "") or r.get("productregioncode", ""),
        billing_entity=r.get("billbillingentity", ""),
        db_engine=r.get("productdatabaseengine", ""),
        os=r.get("productoperatingsystem", ""),
        pre_installed_sw=r.get("productpreinstalledsw", ""),
        period=r["billbillingperiodstartdate"][:10],
        commitment_end=r.get("reservationendtime", "") or r.get("savingsplanendtime", ""),
        source=source,
    )
    line.note("receipt", f"type={line_type} -> bucket '{line.bucket}'; "
                         f"unblended ${unblended:.2f}, effective ${effective:.2f}, on-demand ${on_demand:.2f}")
    return line


# TODO handle multiple months properly, right now just averages
def _scale_to_standard_month(lines, periods, hours_per_month, warnings) -> None:
    n = len(periods)
    for key, p in periods.items():
        full = (p["end"] - p["start"]).total_seconds() / 3600
        last = min(p["last_usage"] or p["end"], p["end"])
        covered = max((last - p["start"]).total_seconds() / 3600, 1.0)
        p["covered_hours"] = covered
        p["scale"] = hours_per_month / covered / n
        if covered < full - 24:
            warnings.append(
                f"Billing period {key} only has {covered / 24:.1f} of {full / 24:.0f} days of data "
                "(month not finished?). Costs were stretched to a full month; treat with care."
            )
    if n > 1:
        warnings.append(f"{n} billing periods found; results are the average month.")
    for l in lines:
        l.period_hours = periods[l.period]["covered_hours"]
        l.scale = periods[l.period]["scale"]
