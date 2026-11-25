def find_twins(lines: list, data: dict, ctx: dict) -> None:
    for line in lines:
        handler = HANDLERS.get(line.kind, _human)
        handler(line, data, ctx)
        line.note("twin", f"{line.twin} [{line.confidence}] via price rule '{line.price_rule}'")


def _set(line, twin, confidence, rule, **args):
    line.twin, line.confidence, line.price_rule, line.price_args = twin, confidence, rule, args


def _human(line, data=None, ctx=None, why=""):
    if why:
        line.note("twin", why)
    _set(line, "needs a human", "human", "same_as_aws")


def machine_hourly(spec: dict, vcpu: float, ram: float, custom: bool, premium: float) -> float:
    price = vcpu * spec["vcpu_hour"] + ram * spec["gb_hour"]
    return price * (1 + premium) if custom else price


# cheaper of custom vs next size up
def pick_machine(family: str, vcpu: float, ram: float, prices: dict):
    spec = prices["compute"]["families"][family]
    premium = prices["compute"]["custom_premium"]
    need_ratio = ram / vcpu

    predefined = None
    for rname, ratio in sorted(spec["ratios"].items(), key=lambda kv: kv[1]):
        if ratio + 1e-9 < need_ratio:
            continue
        size = next((s for s in spec["sizes"] if s >= vcpu), None)
        if size:
            predefined = (f"{family}-{rname}-{size}", size, size * ratio, False)
            break
    if predefined and predefined[1] == vcpu and abs(predefined[2] - ram) < 1e-6:
        return (*predefined, True)

    candidates = [predefined] if predefined else []
    if spec["custom"]:
        candidates.append((f"{family}-custom-{int(vcpu)}-{int(ram * 1024)}", vcpu, ram, True))
    if not candidates:
        return None
    best = min(candidates, key=lambda c: machine_hourly(spec, c[1], c[2], c[3], premium))
    return (*best, False)


def _vm(line, data, ctx):
    d, prices = line.details, data["prices"]
    shape = d.get("shape")
    if not shape:
        return _human(line, why=f"instance type '{d.get('itype')}' not understood "
                                "(GPU, storage-optimised, metal or a new family)")
    if d.get("sql_server"):
        return _human(line, why="SQL Server licence is inside the AWS price; licensing on GCP needs a human")

    uptime = min(1.0, line.amount / line.period_hours) if line.period_hours else 1.0
    if not line.resource_id:
        line.note("twin", "no resource id: several machines may be summed, uptime is a guess")

    reasons = []
    if shape["arm"]:
        family = "c4a"
        reasons.append("ARM (Graviton) -> C4A (Google ARM); check C4A is offered in your region")
    elif shape["burstable"]:
        family = "e2"
        reasons.append("burstable t-family -> E2; part-time vs full CPU differ")
    else:
        family = "n2"

    shared = prices["compute"]["shared_core"]
    if family == "e2" and shape["vcpu"] == 2 and shape["ram_gb"] <= 4:
        name = "e2-micro" if shape["ram_gb"] <= 1 else "e2-small" if shape["ram_gb"] <= 2 else "e2-medium"
        vcpu, ram, custom, exact_shape = shared[name]["vcpu"], shared[name]["ram_gb"], False, False
        reasons.append(f"small burstable -> shared-core {name} (billed as {vcpu} vCPU)")
    else:
        picked = pick_machine(family, shape["vcpu"], shape["ram_gb"], prices)
        if not picked:
            return _human(line, why=f"no {family} machine big enough for {shape}")
        name, vcpu, ram, custom, exact_shape = picked
        if custom:
            reasons.append("no matching standard size; custom shape is cheaper than rounding up")
        elif not exact_shape:
            reasons.append(f"rounded up to {name} ({vcpu} vCPU, {ram:g} GB)")

    if d.get("windows"):
        reasons.append("Windows: GCP licence fee added")
    if d.get("spot"):
        reasons.append("Spot: price moves; wide range used")
    if shape["local_nvme"]:
        reasons.append("local NVMe disk is included in AWS price; GCP Local SSD not priced")

    clean = exact_shape and not (shape["arm"] or shape["burstable"] or d.get("windows")
                                 or d.get("spot") or shape["local_nvme"])
    for r in reasons:
        line.note("twin", r)
    _set(line, name, "exact" if clean else "close", "vm",
         family=family, vcpu=vcpu, ram=ram, custom=custom, hours=line.monthly_quantity,
         uptime=uptime, windows=d.get("windows", False), license_vcpu=shape["vcpu"],
         spot=d.get("spot", False))


def _disk(line, data, ctx):
    vol = line.details.get("vol") or "standard"
    pd = data["services"]["ebs_to_pd"].get(vol)
    if not pd:
        return _human(line, why=f"unknown EBS volume type '{vol}'")
    line.note("twin", "PD speed grows with disk size; gp3 gives fixed free speed. Check IOPS needs.")
    _set(line, pd.replace("_", "-"), "close", "per_unit", price="disk." + pd, quantity=line.monthly_quantity)


def _disk_perf(line, data, ctx):
    line.note("twin", "extra gp3/io IOPS: PD includes speed by size. If not enough, Hyperdisk (not priced)")
    _set(line, "included in Persistent Disk size", "close", "zero")


def _snapshot(line, data, ctx):
    _set(line, "PD snapshot", "close", "per_unit", price="disk.snapshot", quantity=line.monthly_quantity)


def _s3_storage(line, data, ctx):
    code = line.details.get("s3class", "")
    gcs = data["services"]["s3_to_gcs"].get(code)
    if not gcs:
        return _human(line, why=f"unknown S3 storage class code '{code}'")
    conf = "exact" if gcs == "standard" else "close"
    if gcs != "standard":
        line.note("twin", "cold classes have minimum storage times and read fees that differ per cloud")
    _set(line, f"GCS {gcs}", conf, "per_unit", price=f"gcs.{gcs}", quantity=line.monthly_quantity)


def _s3_requests(line, data, ctx):
    tier = line.details.get("tier", "class_b")
    _set(line, f"GCS {tier.replace('_', ' ')} operations", "close", "per_unit",
         price=f"gcs.{tier}_per_1000", quantity=line.monthly_quantity, per=1000)


def _s3_retrieval(line, data, ctx):
    _set(line, "GCS retrieval", "close", "per_unit", price="gcs.retrieval_gb", quantity=line.monthly_quantity)


def _db_instance(line, data, ctx):
    d = line.details
    engine, shape = d.get("engine", "unknown"), d.get("shape")
    if any(x in engine for x in ("Oracle", "SQL Server")):
        return _human(line, why=f"{engine}: licence included in AWS price; Cloud SQL has no Oracle")
    if engine == "unknown" or not shape:
        return _human(line, why=f"database engine '{engine}' or shape {d.get('itype')} not understood")

    conf = "exact"
    if "Aurora" in engine:
        conf = "close"
        line.note("twin", "Aurora is not plain MySQL/PostgreSQL; priced as Cloud SQL, consider AlloyDB")
    if shape["burstable"]:
        conf = "close"
        line.note("twin", "burstable db.t* -> Cloud SQL small shape; part-time vs full CPU")
    if shape["ram_gb"] / shape["vcpu"] > 6.5:
        conf = "close"
        line.note("twin", "Cloud SQL Enterprise allows max 6.5 GB per vCPU; may need more vCPUs")
    base = engine.replace("Aurora ", "")
    ha = d.get("multi_az", False)
    twin = f"Cloud SQL {base} {shape['vcpu']} vCPU / {shape['ram_gb']:g} GB" + (" HA" if ha else "")
    _set(line, twin, conf, "cloudsql", vcpu=shape["vcpu"], ram=shape["ram_gb"],
         hours=line.monthly_quantity, ha=ha)


def _db_storage(line, data, ctx):
    ha = line.details.get("multi_az", False)
    _set(line, "Cloud SQL SSD storage" + (" (HA)" if ha else ""), "exact", "per_unit",
         price="cloudsql.ssd_gb_month", quantity=line.monthly_quantity,
         multiplier=data["prices"]["cloudsql"]["ha_multiplier"] if ha else 1)


def _db_io(line, data, ctx):
    line.note("twin", "Aurora bills per I/O; Cloud SQL does not")
    _set(line, "no I/O charge on Cloud SQL", "close", "zero")


def _db_backup(line, data, ctx):
    _set(line, "Cloud SQL backups", "close", "per_unit", price="cloudsql.backup_gb_month",
         quantity=line.monthly_quantity)


def _egress(line, data, ctx):
    tier = data["settings"]["gcp"]["network_tier"]
    line.note("twin", f"internet egress on {tier} tier; real price depends on destination and volume")
    _set(line, f"internet egress ({tier})", "close", "per_unit",
         price=f"network.egress_{tier}_gb", quantity=line.monthly_quantity)


# aws bills cross az both sides, gcp once -> halve it
def _inter_zone(line, data, ctx):
    line.note("twin", "AWS bills cross-zone GB in BOTH directions; GCP bills once -> half the GB")
    _set(line, "inter-zone traffic", "close", "per_unit", price="network.inter_zone_gb",
         quantity=line.monthly_quantity, multiplier=0.5)


def _inter_region(line, data, ctx):
    _set(line, "inter-region traffic", "assumed", "same_as_aws")


def _ingress(line, data, ctx):
    _set(line, "ingress (free)", "exact", "zero")


def _nat_hours(line, data, ctx):
    line.note("twin", f"Cloud NAT bills per VM behind it; assumed all {ctx['vm_count']} VMs use NAT")
    _set(line, "Cloud NAT gateway", "close", "nat", hours=line.monthly_quantity, vms=ctx["vm_count"])


def _nat_bytes(line, data, ctx):
    _set(line, "Cloud NAT data processing", "close", "per_unit", price="network.nat_gb",
         quantity=line.monthly_quantity)


def _ipv4(line, data, ctx):
    _set(line, "external IPv4 address", "exact", "per_unit", price="network.ipv4_hour",
         quantity=line.monthly_quantity)


def _lb_hours(line, data, ctx):
    _set(line, "Cloud Load Balancing forwarding rule", "close", "per_unit",
         price="network.lb_rule_hour", quantity=line.monthly_quantity)


def _lb_lcu(line, data, ctx):
    line.note("twin", "AWS LCU units have no GCP equivalent; copied AWS cost")
    _set(line, "Cloud Load Balancing data processing", "assumed", "same_as_aws")


def _lb_bytes(line, data, ctx):
    _set(line, "Cloud Load Balancing data processing", "close", "per_unit",
         price="network.lb_gb", quantity=line.monthly_quantity)


def _k8s_cluster(line, data, ctx):
    _set(line, "GKE cluster fee", "exact", "per_unit", price="gke.cluster_hour", quantity=line.monthly_quantity)


def _k8s_extended(line, data, ctx):
    line.note("twin", "EKS extended support (old k8s version) is avoidable by upgrading; priced as normal GKE")
    _set(line, "GKE cluster fee (after upgrade)", "close", "per_unit", price="gke.cluster_hour",
         quantity=line.monthly_quantity)


def _dns_zone(line, data, ctx):
    _set(line, "Cloud DNS zone", "exact", "per_unit", price="dns.zone_month", quantity=line.monthly_quantity)


def _managed(line, data, ctx):
    twin = data["services"]["managed"][line.product]
    _set(line, twin, "assumed", "same_as_aws")


def _support(line, data, ctx):
    _set(line, "Google Cloud Customer Care", "assumed", "support")


def _vm_cpu_credits(line, data, ctx):
    line.note("twin", "t-instance burst credits: the machine is often busy; E2 has no credit fees, "
                      "but a bigger machine may be needed")
    _set(line, "no CPU credit fee on GCP", "close", "zero")


HANDLERS = {
    "vm": _vm, "vm_cpu_credits": _vm_cpu_credits,
    "disk": _disk, "disk_perf": _disk_perf, "snapshot": _snapshot,
    "s3_storage": _s3_storage, "s3_requests": _s3_requests, "s3_retrieval": _s3_retrieval,
    "db_instance": _db_instance, "db_storage": _db_storage, "db_io": _db_io, "db_backup": _db_backup,
    "egress_internet": _egress, "inter_zone": _inter_zone, "inter_region": _inter_region,
    "ingress": _ingress, "nat_hours": _nat_hours, "nat_bytes": _nat_bytes, "ipv4": _ipv4,
    "lb_hours": _lb_hours, "lb_lcu": _lb_lcu, "lb_bytes": _lb_bytes,
    "k8s_cluster": _k8s_cluster, "k8s_extended_support": _k8s_extended,
    "dns_zone": _dns_zone, "managed": _managed, "support": _support,
    "marketplace": _human, "unknown": _human,
}
