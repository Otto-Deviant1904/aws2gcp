# TODO: rds engine op codes not checked on a real CUR yet
import re

GROUP_OF_KIND = {
    "vm": "compute", "vm_cpu_credits": "compute",
    "disk": "storage", "disk_perf": "storage", "snapshot": "storage",
    "s3_storage": "storage", "s3_requests": "storage", "s3_retrieval": "storage",
    "db_instance": "database", "db_storage": "database", "db_io": "database", "db_backup": "database",
    "egress_internet": "network", "inter_zone": "network", "inter_region": "network",
    "ingress": "network", "nat_hours": "network", "nat_bytes": "network", "ipv4": "network",
    "lb_hours": "network", "lb_lcu": "network", "lb_bytes": "network",
    "k8s_cluster": "kubernetes", "k8s_extended_support": "kubernetes",
    "dns_zone": "dns",
    "managed": "managed",
    "support": "support",
    "marketplace": "human", "unknown": "human",
}

EC2_OS_BY_OPERATION = {
    "RunInstances": "Linux",
    "RunInstances:0002": "Windows",
    "RunInstances:0006": "Windows with SQL Server Standard",
    "RunInstances:0102": "Windows with SQL Server Enterprise",
    "RunInstances:0202": "Windows with SQL Server Web",
    "RunInstances:0010": "RHEL",
    "RunInstances:000g": "SUSE",
}

RDS_ENGINE_BY_OPERATION = {
    "CreateDBInstance:0002": "MySQL",
    "CreateDBInstance:0014": "PostgreSQL",
    "CreateDBInstance:0016": "Aurora MySQL",
    "CreateDBInstance:0021": "Aurora PostgreSQL",
    "CreateDBInstance:0018": "MariaDB",
}

T_SIZES = {"nano": (2, 0.5), "micro": (2, 1), "small": (2, 2), "medium": (2, 4),
           "large": (2, 8), "xlarge": (4, 16), "2xlarge": (8, 32)}
GB_PER_VCPU = {"m": 4, "c": 2, "r": 8, "x": 16}


def parse_instance(itype: str):
    m = re.fullmatch(r"([a-z]+)(\d+)([a-z-]*)\.(\w+)", itype)
    if not m:
        return None
    letters, gen, attrs, size = m.groups()
    cls = letters[0]
    shape = {
        "family": f"{letters}{gen}{attrs}",
        "cls": cls,
        "arm": "g" in attrs,
        "burstable": cls == "t",
        "local_nvme": "d" in attrs,
    }
    if len(letters) > 1:
        return None
    if shape["burstable"]:
        if size not in T_SIZES:
            return None
        shape["vcpu"], shape["ram_gb"] = T_SIZES[size]
        return shape
    if cls not in GB_PER_VCPU:
        return None
    vcpu = _size_to_vcpu(size)
    if vcpu is None:
        return None
    shape["vcpu"], shape["ram_gb"] = vcpu, vcpu * GB_PER_VCPU[cls]
    return shape


def _size_to_vcpu(size: str):
    if size == "medium":
        return 1
    if size == "large":
        return 2
    if size == "xlarge":
        return 4
    m = re.fullmatch(r"(\d+)xlarge", size)
    return 4 * int(m.group(1)) if m else None


def sort_lines(lines: list, data: dict) -> None:
    rules = [dict(r, _re=re.compile(r["match"]), _prod=re.compile(r["product"]) if "product" in r else None)
             for r in data["rules"]]
    prefixes = data["regions"]["prefix_to_aws_region"]
    services = data["services"]
    for line in lines:
        _sort_one(line, rules, prefixes, services)


def _sort_one(line, rules, prefixes, services) -> None:
    usage = line.usage_type
    prefix = usage.split("-", 1)[0] if "-" in usage else ""
    if prefix in prefixes:
        usage = usage[len(prefix) + 1:]
    else:
        prefix = ""

    if line.region_col:
        line.region = line.region_col
    elif prefix:
        line.region = prefixes[prefix]
    else:
        line.region = "us-east-1"
        line.note("sorter", "no region column and no prefix: AWS means us-east-1")

    kind, details = None, {}
    if line.billing_entity == "AWS Marketplace":
        kind = "marketplace"
        line.note("sorter", "sold through AWS Marketplace: third-party licence, may not move to GCP")
    elif line.product in services["support_products"]:
        kind = "support"
    else:
        for rule in rules:
            if rule["_prod"] and not rule["_prod"].search(line.product):
                continue
            m = rule["_re"].search(usage)
            if m:
                kind = rule["kind"]
                details = {k: v for k, v in m.groupdict().items() if v is not None}
                for extra in ("spot", "tier"):
                    if extra in rule:
                        details[extra] = rule[extra]
                line.note("sorter", f"UsageType '{usage}' matched rule /{rule['match']}/ -> {kind}")
                break
    if kind is None:
        if line.product in services["managed"]:
            kind = "managed"
            line.note("sorter", f"no specific rule; {line.product} is a known managed service")
        else:
            kind = "unknown"
            line.note("sorter", f"no rule matched '{usage}' ({line.product}) -> needs a human")

    line.kind, line.group, line.details = kind, GROUP_OF_KIND[kind], details
    _add_details(line)


def _add_details(line) -> None:
    d = line.details
    if line.kind == "vm":
        d["shape"] = parse_instance(d.get("itype", ""))
        os_name = line.os or EC2_OS_BY_OPERATION.get(line.operation, "Linux")
        d["os"] = os_name
        d["windows"] = "Windows" in os_name
        sw = line.pre_installed_sw if line.pre_installed_sw not in ("", "NA") else ""
        d["sql_server"] = "SQL" in sw or "SQL" in os_name
        line.note("sorter", f"instance {d.get('itype')} -> shape {d['shape']}, OS {os_name}")
    elif line.kind == "db_instance":
        d["shape"] = parse_instance(d.get("itype", ""))
        d["engine"] = line.db_engine or RDS_ENGINE_BY_OPERATION.get(line.operation, "unknown")
        d["multi_az"] = d.get("az") == "Multi-AZUsage"
        line.note("sorter", f"database {d.get('itype')} engine={d['engine']} multi_az={d['multi_az']}")
    elif line.kind == "db_storage":
        d["multi_az"] = bool(d.get("multiaz"))
