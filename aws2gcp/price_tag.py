from .twin_finder import machine_hourly


def lookup(prices: dict, dotted: str) -> float:
    node = prices
    for part in dotted.split("."):
        node = node[part]
    return float(node)


# n2 only. under 25% of month = no discount
def sud_factor(uptime: float, tiers: list) -> float:
    if uptime <= 0:
        return 1.0
    paid = sum(max(0.0, min(uptime, t["to"]) - t["from"]) * t["rate"] for t in tiers)
    return paid / uptime


def price_lines(lines: list, prices: dict, settings: dict) -> None:
    bands = settings["confidence_band"]
    for line in lines:
        result = _price_one(line, prices, settings)
        if isinstance(result, tuple):
            low, likely, high = result
        else:
            band = bands[line.confidence]
            likely = result
            low, high = likely * (1 - band), likely * (1 + band)
        line.gcp_low, line.gcp_likely, line.gcp_high = low, likely, high
        line.note("price", f"GCP ${likely:.2f}/month (range ${low:.2f}..${high:.2f}); AWS ${line.monthly_aws:.2f}")


def _price_one(line, prices, settings):
    rule, a = line.price_rule, line.price_args
    if rule in ("same_as_aws",):
        return line.monthly_aws
    if rule in ("zero", "support"):
        return 0.0
    if rule == "per_unit":
        unit = lookup(prices, a["price"])
        cost = a["quantity"] * unit * a.get("multiplier", 1) / a.get("per", 1)
        line.note("price", f"{a['quantity']:.2f} x ${unit} ({a['price']})"
                           + (f" x {a['multiplier']}" if a.get("multiplier", 1) != 1 else "")
                           + (f" / {a['per']}" if a.get("per", 1) != 1 else ""))
        return cost
    if rule == "vm":
        return _price_vm(line, prices, settings)
    if rule == "cloudsql":
        return _price_cloudsql(line, prices, settings)
    if rule == "nat":
        net = prices["network"]
        per_hour = min(a["vms"] * net["nat_per_vm_hour"], net["nat_gateway_hour_cap"])
        line.note("price", f"NAT: min({a['vms']} VMs x ${net['nat_per_vm_hour']}, cap ${net['nat_gateway_hour_cap']}) "
                           f"= ${per_hour:.4f}/h x {a['hours']:.0f} h")
        return per_hour * a["hours"]
    raise ValueError(f"unknown price rule {rule}")


def _price_vm(line, prices, settings):
    a, comp = line.price_args, prices["compute"]
    spec = comp["families"][a["family"]]
    hourly = machine_hourly(spec, a["vcpu"], a["ram"], a["custom"], comp["custom_premium"])
    if a["windows"]:
        hourly += comp["windows_license_vcpu_hour"] * a["license_vcpu"]
    perf = settings["gcp"]["perf_factor"]
    base = hourly * a["hours"] * perf
    line.note("price", f"${hourly:.4f}/h x {a['hours']:.0f} h" + (f" x perf {perf}" if perf != 1 else "")
                       + f" = ${base:.2f} on-demand")

    if a["spot"]:
        s = comp["spot_discount"]
        line.note("price", f"Spot: {s['low']:.0%}..{s['high']:.0%} off, likely {s['likely']:.0%}")
        return base * (1 - s["high"]), base * (1 - s["likely"]), base * (1 - s["low"])

    cud = settings["gcp"]["cud"]
    if cud != "none":
        off = comp["cud_discount"][cud]
        line.note("price", f"committed-use {cud}: {off:.0%} off")
        return base * (1 - off)

    if spec["sud"]:
        factor = sud_factor(a["uptime"], comp["sud_tiers_n2"])
        line.note("price", f"sustained-use: ran {a['uptime']:.0%} of month -> pay {factor:.1%}")
        return base * factor
    line.note("price", f"{a['family']} gets no sustained-use discount")
    return base


def _price_cloudsql(line, prices, settings):
    a, sql = line.price_args, prices["cloudsql"]
    hourly = a["vcpu"] * sql["vcpu_hour"] + a["ram"] * sql["gb_hour"]
    if a["ha"]:
        hourly *= sql["ha_multiplier"]
    cost = hourly * a["hours"] * settings["gcp"]["perf_factor"]
    line.note("price", f"Cloud SQL ${hourly:.4f}/h" + (" (HA x2)" if a["ha"] else "") + f" x {a['hours']:.0f} h")
    cud = settings["gcp"]["cud"]
    if cud != "none":
        off = sql["cud_discount"][cud]
        line.note("price", f"Cloud SQL committed-use {cud}: {off:.0%} off")
        cost *= 1 - off
    return cost
