from .config import flag_for

def USD(x: float) -> str:
    x = round(x, 2) + 0.0  # no "-$0.00"
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def money_range(low, likely, high):
    return f"{USD(likely)} ({USD(low)} .. {USD(high)})"


def break_even(one_time: float, aws: float, gcp: float):
    saving = aws - gcp
    if saving <= 0:
        return None
    return one_time / saving


def months_text(m):
    return "never (GCP is not cheaper)" if m is None else f"{m:,.1f} months"


def render(result) -> str:
    t, mig, s = result.totals, result.migration, result.settings
    out = ["# AWS to GCP cost report", ""]
    out += [f"Prices: GCP {result.prices_meta['region']}, snapshot {result.prices_meta['snapshot_date']}, "
            f"verified: {result.prices_meta.get('verified', False)}. All amounts USD per standard 730-hour month, "
            "tax excluded.", ""]

    aws = t["aws_compare"]
    save_likely = aws - t["gcp_likely"]
    be_likely = break_even(mig["likely"], aws, t["gcp_likely"])
    be_best = break_even(mig["low"], aws, t["gcp_low"])
    be_worst = break_even(mig["high"], aws, t["gcp_high"])
    out += ["## Headline", "",
            "| | Monthly |", "|---|---|",
            f"| AWS today (after RI/SP discounts, before credits) | {USD(aws)} |",
            f"| AWS at list price (no discounts) | {USD(t['aws_on_demand_monthly'])} |",
            f"| AWS if cleaned up first (rough, -{s['aws']['optimisation_pct']:.0%}) | {USD(t['aws_cleaned_up'])} |",
            f"| GCP estimate | {money_range(t['gcp_low'], t['gcp_likely'], t['gcp_high'])} |",
            f"| Monthly saving (likely) | {USD(save_likely)} ({save_likely / aws:.0%} of AWS) |" if aws else "",
            "",
            f"One-time moving cost: {money_range(mig['low'], mig['likely'], mig['high'])}"
            + (f" after {USD(mig['credits'])} GCP credits" if mig["credits"] else ""),
            "",
            f"Break-even: likely {months_text(be_likely)}; best case {months_text(be_best)}; "
            f"worst case {months_text(be_worst)}.", ""]
    if t["credits_monthly"]:
        out += [f"Note: AWS credits paid {USD(-t['credits_monthly'])} this month. "
                f"Real spend before credits is the AWS figure above.", ""]

    cov = t["coverage"]
    out += ["## How much to trust this", "",
            f"Share of the AWS bill matched: exact {cov['exact']:.0%}, close {cov['close']:.0%}, "
            f"assumed {cov['assumed']:.0%}, needs a human {cov['human']:.0%}.", "",
            "- exact: same product and shape (+/- 5%)",
            "- close: same job, different shape or pricing rules (+/- 20%)",
            "- assumed: GCP service exists, but we copied the AWS cost (+/- 30%)",
            "- needs a human: no safe twin; AWS cost copied as a placeholder (+/- 50%)", ""]

    humans = sorted((l for l in result.lines if l.confidence == "human"), key=lambda l: -l.monthly_aws)
    if humans:
        out += ["## Needs a human (most expensive first)", "",
                "| AWS monthly | Product | UsageType | Why |", "|---:|---|---|---|"]
        for l in humans[:10]:
            why = next((x.split("] ", 1)[1] for x in reversed(l.trace) if x.startswith("[twin]")
                        and "needs a human" not in x), "")
            why = why or next((x.split("] ", 1)[1] for x in l.trace if x.startswith("[sorter]")), "")
            out.append(f"| {USD(l.monthly_aws)} | {l.product} | `{l.usage_type}` | {why} |")
        out.append("")

    groups = {}
    for l in result.lines:
        g = groups.setdefault(l.group, [0.0, 0.0, 0.0, 0.0])
        g[0] += l.monthly_aws
        g[1] += l.gcp_low
        g[2] += l.gcp_likely
        g[3] += l.gcp_high
    out += ["## By group", "", "| Group | AWS | GCP likely | GCP range |", "|---|---:|---:|---|"]
    for name, (a, lo, li, hi) in sorted(groups.items(), key=lambda kv: -kv[1][0]):
        out.append(f"| {name} | {USD(a)} | {USD(li)} | {USD(lo)} .. {USD(hi)} |")
    out.append("")

    out += ["## Top lines", "", "| AWS | GCP likely | Confidence | AWS UsageType | GCP twin |",
            "|---:|---:|---|---|---|"]
    for l in sorted(result.lines, key=lambda l: -l.monthly_aws)[:25]:
        out.append(f"| {USD(l.monthly_aws)} | {USD(l.gcp_likely)} | {l.confidence} | `{l.usage_type}` | {l.twin} |")
    out += ["", "Run `aws2gcp explain <bill> --match <text>` to see how any line was decided.", ""]

    out += ["## Moving truck (one-time)", "", "| Part | Cost | How |", "|---|---:|---|"]
    for name, cost, how in mig["parts"]:
        out.append(f"| {name} | {USD(cost)} | {how} |")
    if mig["credits"]:
        out.append(f"| GCP credits | -{USD(mig['credits'])} | --gcp-credits |")
    out += [f"| **Total (likely)** | **{USD(mig['likely'])}** | range {USD(mig['low'])} .. {USD(mig['high'])} |", ""]

    out += ["## Money not in the comparison", "", "| Bucket | Per month | Meaning |", "|---|---:|---|"]
    meaning = {
        "usage": "usage that was compared above (row cost, before RI/SP effective cost)",
        "tax": "GST / tax; GCP charges tax too, so it is left out",
        "credit": "promotional credits",
        "refund": "refunds",
        "discount": "bundled / private discounts",
        "commitment": "RI and Savings Plan fees (already counted via effective cost)",
        "sp_negation": "Savings Plan cancel-out rows (ignored on purpose)",
        "other": "unrecognised line types",
    }
    for b, v in sorted(t["buckets_monthly"].items()):
        out.append(f"| {b} | {USD(v)} | {meaning.get(b, '')} |")
    ok = t["reconcile_diff"] < 0.005
    out += ["", f"Reconciliation: buckets add up to the bill total {USD(t['raw_total'])} "
                f"({'OK' if ok else 'MISMATCH ' + USD(t['reconcile_diff'])}).", ""]

    out += ["## Assumptions", "", "| Setting | Value | Change with |", "|---|---|---|"]
    for path, value in _flatten(s):
        out.append(f"| {'.'.join(path)} | {value} | {flag_for(path)} |")
    out.append("")
    return "\n".join(x for x in out if x is not None)


def _flatten(d, prefix=()):
    for k, v in d.items():
        if isinstance(v, dict) and k not in ("fx_to_usd", "confidence_band", "hours_per_resource"):
            yield from _flatten(v, prefix + (k,))
        else:
            yield prefix + (k,), v


def explain(result, match: str) -> str:
    hits = [l for l in result.lines if match.lower() in (l.usage_type + " " + l.resource_id).lower()]
    if not hits:
        return f"No usage line contains '{match}'."
    out = []
    for l in hits:
        out += [f"== {l.source}  {l.product}  {l.usage_type}  {l.resource_id}",
                f"   kind={l.kind} group={l.group} region={l.region}",
                f"   twin={l.twin} confidence={l.confidence}",
                f"   AWS {USD(l.monthly_aws)}/month  ->  GCP {money_range(l.gcp_low, l.gcp_likely, l.gcp_high)}"]
        out += [f"   {step}" for step in l.trace]
        out.append("")
    return "\n".join(out)
