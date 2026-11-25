from dataclasses import dataclass, field


@dataclass
class Line:
    line_type: str
    bucket: str
    product: str
    usage_type: str
    operation: str
    amount: float
    unit: str
    unblended: float
    effective: float
    on_demand: float
    resource_id: str = ""
    account: str = ""
    region_col: str = ""
    billing_entity: str = ""
    db_engine: str = ""
    os: str = ""
    pre_installed_sw: str = ""
    period: str = ""
    period_hours: float = 0.0
    scale: float = 1.0
    commitment_end: str = ""
    source: str = ""

    kind: str = ""
    group: str = ""
    region: str = ""
    details: dict = field(default_factory=dict)

    twin: str = ""
    confidence: str = ""
    price_rule: str = ""
    price_args: dict = field(default_factory=dict)

    gcp_low: float = 0.0
    gcp_likely: float = 0.0
    gcp_high: float = 0.0

    trace: list = field(default_factory=list)

    @property
    def monthly_aws(self) -> float:
        return self.effective * self.scale

    @property
    def monthly_quantity(self) -> float:
        return self.amount * self.scale

    def note(self, step: str, text: str) -> None:
        self.trace.append(f"[{step}] {text}")
