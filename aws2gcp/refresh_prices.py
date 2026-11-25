import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

from .config import DATA_DIR

API = "https://cloudbilling.googleapis.com/v1"
# no key needed. Cyclenerd rebuilds this every week from googles own billing api (apache 2.0)
PUBLIC_URL = "https://raw.githubusercontent.com/Cyclenerd/google-cloud-pricing-cost-calculator/master/pricing.yml"

# price per vcpu + per GB: solve from 2 machines with same cpus but different ram
PUBLIC_FAMILIES = {"e2": ("e2-standard-2", "e2-highcpu-2"),
                   "n2": ("n2-standard-2", "n2-highcpu-2"),
                   "c4a": ("c4a-standard-1", "c4a-highcpu-1")}
# our path -> path in their file ({r} = region)
PUBLIC_PATHS = {
    "disk.pd_balanced": "compute.storage.balanced.cost.{r}.month",
    "disk.pd_ssd": "compute.storage.ssd.cost.{r}.month",
    "disk.pd_standard": "compute.storage.hdd.cost.{r}.month",
    "disk.snapshot": "compute.storage.snapshot.cost.{r}.month",
    "gcs.standard": "storage.bucket.standard.cost.{r}.month",
    "gcs.nearline": "storage.bucket.nearline.cost.{r}.month",
    "gcs.coldline": "storage.bucket.coldline.cost.{r}.month",
    "gcs.archive": "storage.bucket.archiv.cost.{r}.month",
    "network.ipv4_hour": "compute.network.ip.vm.cost.{r}.hour",
    "network.nat_gb": "compute.network.nat.data.cost.{r}.month",
    "network.nat_gateway_hour_cap": "compute.network.nat.gateway.cost.{r}.hour",
    "network.egress_premium_gb": "compute.network.traffic.egress.internet.cost.0-1.{r}.month",
}


def fetch_json(url, key):
    sep = "&" if "?" in url else "?"
    with urllib.request.urlopen(f"{url}{sep}key={urllib.parse.quote(key)}", timeout=60) as r:
        return json.load(r)


def _pages(url, field, key, fetch):
    token = ""
    while True:
        page = fetch(url + (f"&pageToken={token}" if token else ""), key)
        yield from page.get(field, [])
        token = page.get("nextPageToken")
        if not token:
            return


def load_catalog(wanted_services, key, fetch=fetch_json):
    """returns {short name: [sku, ...]} straight from google"""
    services = {s["displayName"]: s["name"] for s in _pages(f"{API}/services?pageSize=5000", "services", key, fetch)}
    out = {}
    for short, display in wanted_services.items():
        if display not in services:
            raise RuntimeError(f"service '{display}' not in google catalog")
        out[short] = list(_pages(f"{API}/{services[display]}/skus?currencyCode=USD&pageSize=5000", "skus", key, fetch))
    return out


def fetch_public(url=PUBLIC_URL):
    with urllib.request.urlopen(url, timeout=120) as r:
        return yaml.load(r.read(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


def match_public(data, region):
    """same output as match_prices but from the public file. cloudsql isnt in there so stays by hand"""
    found, problems = {}, {}
    inst = data["compute"]["instance"]
    for fam, (a, b) in PUBLIC_FAMILIES.items():
        try:
            c1, r1, p1 = inst[a]["cpu"], inst[a]["ram"], inst[a]["cost"][region]["hour"]
            c2, r2, p2 = inst[b]["cpu"], inst[b]["ram"], inst[b]["cost"][region]["hour"]
        except (KeyError, TypeError):
            problems[f"compute.families.{fam}.vcpu_hour"] = f"{a}/{b} not in public file for {region}"
            continue
        gb = (p1 * c2 - p2 * c1) / (r1 * c2 - r2 * c1)
        found[f"compute.families.{fam}.gb_hour"] = round(gb, 10)
        found[f"compute.families.{fam}.vcpu_hour"] = round((p1 - r1 * gb) / c1, 10)
    for path, where in PUBLIC_PATHS.items():
        try:
            found[path] = round(float(get(data, where.format(r=region))), 10)
        except (KeyError, TypeError, ValueError):
            problems[path] = f"{where.format(r=region)} not in public file"
    return found, problems


def unit_price(sku):
    # last pricingInfo = current price. tiers: take first one that isnt free (some have a free first tier)
    rates = sku["pricingInfo"][-1]["pricingExpression"]["tieredRates"]
    for r in rates:
        p = int(r["unitPrice"].get("units", 0) or 0) + r["unitPrice"].get("nanos", 0) / 1e9
        if p > 0:
            return p
    return 0.0


def match_prices(catalog, mapping, region):
    """returns (found {path: price}, problems {path: why})"""
    found, problems = {}, {}
    for path, m in mapping.items():
        pat = re.compile(m["sku"])
        hits = [s for s in catalog.get(m["service"], [])
                if pat.search(s["description"]) and s.get("category", {}).get("usageType") == "OnDemand"]
        regional = [s for s in hits if region in s.get("serviceRegions", [])]
        hits = regional or [s for s in hits if "global" in s.get("serviceRegions", [])]
        prices = sorted({round(unit_price(s), 8) for s in hits})
        if not prices:
            problems[path] = f"no sku matched /{m['sku']}/ in {region}"
        elif len(prices) > 1:
            problems[path] = f"{len(hits)} skus matched with different prices {prices}, fix the regex"
        else:
            found[path] = prices[0]
    return found, problems


def rewrite_yaml(text, updates):
    """change numbers in prices.yaml in place so comments and layout stay the same"""
    out, stack = [], []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\s*)([\w-]+):(\s*)(.*?)(\s*#.*)?$", line.rstrip("\n"))
        if not m or line.lstrip().startswith("#"):
            out.append(line)
            continue
        indent = len(m.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group(2)))
        path = ".".join(k for _, k in stack)
        if path in updates and m.group(4):
            line = f"{m.group(1)}{m.group(2)}:{m.group(3) or ' '}{updates[path]:.10g}{m.group(5) or ''}\n"
        out.append(line)
    return "".join(out)


def get(d, path):
    for k in path.split("."):
        d = d[k]
    return d


def refresh(key=None, prices_file=None, mapping_file=None, region=None, fetch=fetch_json, today=None, write=True,
            public=fetch_public):
    prices_file = Path(prices_file or DATA_DIR / "prices.yaml")
    mapping = yaml.safe_load(Path(mapping_file or DATA_DIR / "price_skus.yaml").read_text())
    text = prices_file.read_text()
    old = yaml.safe_load(text)
    region = region or old["meta"]["region"]

    if key:  # googles api directly
        catalog = load_catalog(mapping["services"], key, fetch)
        found, problems = match_prices(catalog, mapping["prices"], region)
    else:    # no key, use the public file
        found, problems = match_public(public(), region)

    changes = []
    for path, new in sorted(found.items()):
        before = get(old, path)
        if abs(new - before) > 1e-9:
            changes.append((path, before, new))

    text = rewrite_yaml(text, found)
    text = re.sub(r"(?m)^(  snapshot_date:\s*)\S+", rf"\g<1>{(today or date.today()).isoformat()}", text)
    text = re.sub(r"(?m)^(  verified:\s*)\S+", rf"\g<1>{'true' if not problems else 'false'}", text)
    text = re.sub(r"(?m)^(  region:\s*)\S+", rf"\g<1>{region}", text)
    if write:
        prices_file.write_text(text)
    return changes, problems, found


def summary(changes, problems, found, region, source="the Cloud Billing Catalog API"):
    lines = [f"# GCP price refresh ({region})", "",
             f"{len(found)} prices checked against {source}, {len(changes)} changed.", ""]
    if changes:
        lines += ["| price | old | new | change |", "|---|---:|---:|---:|"]
        for path, a, b in changes:
            pct = (b - a) / a if a else 0
            flag = " **check this**" if abs(pct) > 0.3 else ""
            lines.append(f"| `{path}` | {a:g} | {b:g} | {pct:+.1%}{flag} |")
        lines.append("")
    if problems:
        lines += ["Not updated (kept the old number):", ""] + [f"- `{p}`: {why}" for p, why in problems.items()] + [""]
    lines.append("Anything not listed above (discounts, cloud sql without a key, ...) is still typed by hand.")
    return "\n".join(lines)


def main(args):
    key = os.environ.get("GCP_PRICING_API_KEY")  # optional. without it we use the public file
    source = "the Cloud Billing Catalog API" if key else f"the public price file ({PUBLIC_URL})"
    region = args.region or yaml.safe_load(Path(args.prices or DATA_DIR / "prices.yaml").read_text())["meta"]["region"]
    try:
        changes, problems, found = refresh(key, args.prices, region=region, write=not args.dry_run)
    except Exception as e:  # bad key, api down etc
        hint = " (api key wrong, or Cloud Billing API not enabled for it)" if key and ("400" in str(e) or "403" in str(e)) else ""
        print(f"error: {e}{hint}")
        return 1
    text = summary(changes, problems, found, region, source)
    print(text)
    if args.summary:
        Path(args.summary).write_text(text)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as fh:
            fh.write(f"changed={len(changes)}\nproblems={len(problems)}\n")
    return 0
