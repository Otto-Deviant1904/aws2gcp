import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import yaml

from aws2gcp import refresh_prices as rp
from aws2gcp.config import DATA_DIR


def sku(desc, price, region="asia-south1", usage="OnDemand"):
    units, nanos = int(price), round((price - int(price)) * 1e9)
    return {"description": desc, "serviceRegions": [region], "category": {"usageType": usage},
            "pricingInfo": [{"pricingExpression": {"tieredRates": [
                {"startUsageAmount": 0, "unitPrice": {"units": str(units), "nanos": nanos}}]}}]}


FAKE = {
    "Compute Engine": [
        sku("N2 Instance Core running in Mumbai", 0.03797),
        sku("N2 Instance Ram running in Mumbai", 0.005088),
        sku("N2 Instance Core running in Virginia", 0.031, region="us-east4"),
        sku("Spot Preemptible N2 Instance Core running in Mumbai", 0.01128, usage="Preemptible"),
        sku("E2 Instance Core running in Mumbai", 0.0261993),
        sku("Balanced PD Capacity in Mumbai", 0.12),
    ],
    "Cloud SQL": [sku("Cloud SQL for PostgreSQL: Zonal - vCPU in Mumbai", 0.0496)],
    "Cloud Storage": [sku("Standard Storage Mumbai", 0.023), sku("Standard Storage Mumbai", 0.026)],
}


def fake_fetch(url, key):
    if url.split("?")[0].endswith("/services"):
        return {"services": [{"displayName": n, "name": f"services/{i}"} for i, n in enumerate(FAKE)]}
    i = int(url.split("services/")[1].split("/")[0])
    return {"skus": list(FAKE.values())[i]}


class RefreshPrices(unittest.TestCase):
    def setUp(self):
        self.file = Path(tempfile.mkdtemp()) / "prices.yaml"
        shutil.copy(DATA_DIR / "prices.yaml", self.file)
        self.changes, self.problems, self.found = rp.refresh(
            "fake-key", self.file, fetch=fake_fetch, today=date(2026, 12, 1))
        self.new = yaml.safe_load(self.file.read_text())

    def test_prices_come_from_the_api(self):
        self.assertEqual(self.new["compute"]["families"]["n2"]["vcpu_hour"], 0.03797)
        self.assertEqual(self.new["cloudsql"]["vcpu_hour"], 0.0496)

    def test_other_regions_and_spot_are_ignored(self):
        self.assertEqual(self.found["compute.families.n2.vcpu_hour"], 0.03797)

    def test_missing_or_ambiguous_skus_keep_old_number(self):
        self.assertIn("compute.families.c4a.vcpu_hour", self.problems)
        self.assertIn("different prices", self.problems["gcs.standard"])
        old = yaml.safe_load((DATA_DIR / "prices.yaml").read_text())
        self.assertEqual(self.new["gcs"]["standard"], old["gcs"]["standard"])

    def test_not_verified_when_something_is_missing(self):
        self.assertFalse(self.new["meta"]["verified"])
        self.assertEqual(str(self.new["meta"]["snapshot_date"]), "2026-12-01")

    def test_comments_and_layout_kept(self):
        text = self.file.read_text()
        self.assertIn("# Google Axion, ARM", text)
        self.assertEqual(len(text.splitlines()), len((DATA_DIR / "prices.yaml").read_text().splitlines()))

    def test_summary_lists_problems(self):
        s = rp.summary(self.changes, self.problems, self.found, "asia-south1")
        self.assertIn("Not updated", s)
        self.assertIn("gcs.standard", s)


def inst(cpu, ram, hour):
    return {"cpu": cpu, "ram": ram, "cost": {"asia-south1": {"hour": hour}}}


PUBLIC = {
    "compute": {
        "instance": {
            "n2-standard-2": inst(2, 8, 2 * 0.03797 + 8 * 0.005088),
            "n2-highcpu-2": inst(2, 2, 2 * 0.03797 + 2 * 0.005088),
            "e2-standard-2": inst(2, 8, 0.08048436),
            "e2-highcpu-2": inst(2, 2, 0.05942004),
        },
        "storage": {"balanced": {"cost": {"asia-south1": {"month": 0.12}}}},
        "network": {},
    },
    "storage": {"bucket": {}},
}


class RefreshPublic(unittest.TestCase):
    def setUp(self):
        self.file = Path(tempfile.mkdtemp()) / "prices.yaml"
        shutil.copy(DATA_DIR / "prices.yaml", self.file)
        self.changes, self.problems, self.found = rp.refresh(
            None, self.file, public=lambda: PUBLIC, today=date(2026, 12, 1))

    def test_vcpu_and_ram_solved_from_two_machines(self):
        self.assertAlmostEqual(self.found["compute.families.n2.vcpu_hour"], 0.03797)
        self.assertAlmostEqual(self.found["compute.families.n2.gb_hour"], 0.005088)
        self.assertAlmostEqual(self.found["compute.families.e2.gb_hour"], 0.00351072)

    def test_missing_stuff_is_a_problem_not_a_crash(self):
        self.assertIn("compute.families.c4a.vcpu_hour", self.problems)
        self.assertIn("gcs.standard", self.problems)
        self.assertEqual(self.found["disk.pd_balanced"], 0.12)


if __name__ == "__main__":
    unittest.main()
