import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aws2gcp import config, pipeline, report_card
from aws2gcp.price_tag import sud_factor
from aws2gcp.receipt import ReceiptError
from aws2gcp.sample import ROWS, write_sample
from aws2gcp.sorter import parse_instance
from aws2gcp.twin_finder import pick_machine

TODAY = date(2026, 11, 23)


def run(flags=None, **sample_kwargs):
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "cur.csv"
    write_sample(path, **sample_kwargs)
    data = config.load_all()
    settings = config.apply_flags(data["settings"], flags or {})
    return pipeline.run([str(path)], data, settings, today=TODAY)


def line(result, usage_type):
    return next(l for l in result.lines if l.usage_type == usage_type)


class Receipt(unittest.TestCase):
    def test_buckets_add_up_to_bill_total(self):
        r = run()
        self.assertLess(r.totals["reconcile_diff"], 0.005)
        self.assertAlmostEqual(r.totals["raw_total"], sum(row[6] for row in ROWS), places=2)

    def test_savings_plan_not_double_counted(self):
        r = run()
        expected = sum(
            float(extra.get("savingsPlan/SavingsPlanEffectiveCost") or extra.get("reservation/EffectiveCost") or cost)
            for ltype, _, _, _, _, _, cost, extra in ROWS
            if ltype in ("Usage", "DiscountedUsage", "SavingsPlanCoveredUsage"))
        self.assertAlmostEqual(r.totals["aws_monthly"], expected * 730 / 720, places=2)

    def test_reserved_instance_uses_effective_cost(self):
        self.assertAlmostEqual(line(run(), "APS3-BoxUsage:c5.xlarge").effective, 85.0)

    def test_tax_credit_fee_kept_out_of_workload(self):
        kinds = {l.line_type for l in run().lines}
        self.assertFalse(kinds & {"Tax", "Credit", "Refund", "Fee", "RIFee", "SavingsPlanNegation"})

    def test_partial_month_is_warned_and_scaled(self):
        r = run(last_usage="2026-11-15T00:00:00Z")
        self.assertTrue(any("only has 14.0 of 30 days" in w for w in r.warnings))
        self.assertAlmostEqual(r.lines[0].scale, 730 / (14 * 24))

    def test_bills_console_csv_is_rejected_clearly(self):
        tmp = Path(tempfile.mkdtemp()) / "bills.csv"
        with open(tmp, "w", newline="") as fh:
            csv.writer(fh).writerows([["Service", "Region", "Cost"], ["EC2", "Mumbai", "10"]])
        data = config.load_all()
        with self.assertRaisesRegex(ReceiptError, "does not look like a Cost and Usage Report"):
            pipeline.run([str(tmp)], data, data["settings"], today=TODAY)


class Sorter(unittest.TestCase):
    def test_ec2_junk_drawer_sorted_by_usage_type(self):
        r = run()
        self.assertEqual(line(r, "APS3-EBS:VolumeUsage.gp3").kind, "disk")
        self.assertEqual(line(r, "APS3-NatGateway-Hours").kind, "nat_hours")
        self.assertEqual(line(r, "APS3-BoxUsage:t3.medium").kind, "vm")

    def test_region_from_prefix_when_no_column(self):
        r = run()
        l = line(r, "APS3-BoxUsage:t3.medium")
        self.assertEqual(l.region, "ap-south-1")

    def test_instance_shapes(self):
        self.assertEqual(parse_instance("m5.large")["vcpu"], 2)
        self.assertEqual(parse_instance("r5.xlarge")["ram_gb"], 32)
        self.assertTrue(parse_instance("m6g.large")["arm"])
        self.assertTrue(parse_instance("t3.micro")["burstable"])
        self.assertIsNone(parse_instance("g4dn.xlarge"))
        self.assertIsNone(parse_instance("inf1.xlarge"))

    def test_nothing_is_dropped(self):
        r = run()
        self.assertTrue(all(l.kind for l in r.lines))
        self.assertEqual(line(r, "APS3-Notebk:ml.t3.medium").kind, "unknown")


class TwinFinder(unittest.TestCase):
    def setUp(self):
        self.r = run()

    def twin(self, usage):
        l = line(self.r, usage)
        return l.twin, l.confidence

    def test_general_purpose_exact(self):
        self.assertEqual(self.twin("APS3-BoxUsage:m5.large"), ("n2-standard-2", "exact"))

    def test_odd_shape_goes_custom_when_cheaper(self):
        self.assertEqual(self.twin("APS3-BoxUsage:c5.xlarge"), ("n2-custom-4-8192", "close"))

    def test_burstable_small_goes_shared_core(self):
        self.assertEqual(self.twin("APS3-BoxUsage:t3.medium"), ("e2-medium", "close"))

    def test_arm_goes_to_arm(self):
        self.assertEqual(self.twin("APS3-BoxUsage:m6g.large"), ("c4a-standard-2", "close"))

    def test_gpu_marketplace_unknown_need_human(self):
        for u in ("APS3-BoxUsage:g4dn.xlarge", "SoftwareUsage:standard", "APS3-Notebk:ml.t3.medium"):
            self.assertEqual(self.twin(u)[1], "human", u)

    def test_lightsail_bundle_is_vm_plus_disk(self):
        l = line(self.r, "APS3-BundleUsage:4GB")
        self.assertEqual((l.twin, l.confidence), ("e2-medium + 80GB pd-balanced", "close"))

    def test_aurora_is_close_not_exact(self):
        self.assertEqual(self.twin("APS3-InstanceUsage:db.r6g.large")[1], "close")

    def test_multi_az_becomes_ha(self):
        self.assertIn("HA", self.twin("APS3-Multi-AZUsage:db.m5.large")[0])

    def test_pick_machine_rounds_up_when_no_custom(self):
        prices = config.load_all()["prices"]
        name, vcpu, ram, custom, exact = pick_machine("c4a", 3, 6, prices)
        self.assertEqual((name, custom, exact), ("c4a-highcpu-4", False, False))


class PriceTag(unittest.TestCase):
    def test_sud_full_month_is_about_80_percent(self):
        tiers = config.load_all()["prices"]["compute"]["sud_tiers_n2"]
        self.assertAlmostEqual(sud_factor(1.0, tiers), 0.80, places=2)
        self.assertEqual(sud_factor(0.2, tiers), 1.0)

    def test_e2_gets_no_sud(self):
        l = line(run(), "APS3-BoxUsage:t3.medium")
        self.assertAlmostEqual(l.gcp_likely, (1 * 0.024 + 4 * 0.0032) * 730, places=2)

    def test_spot_has_its_own_wide_range(self):
        l = line(run(), "APS3-SpotUsage:m5.xlarge")
        self.assertLess(l.gcp_low, l.gcp_likely * 0.5)

    def test_cud_flag_lowers_compute(self):
        a = line(run(), "APS3-BoxUsage:m5.large").gcp_likely
        b = line(run({"gcp_cud": "1y"}), "APS3-BoxUsage:m5.large").gcp_likely
        self.assertLess(b, a)

    def test_cross_zone_counted_once(self):
        l = line(run(), "APS3-DataTransfer-Regional-Bytes")
        self.assertAlmostEqual(l.gcp_likely, 2000 * 0.5 * 0.01 * 730 / 720, places=2)

    def test_human_rows_copy_aws_cost(self):
        l = line(run(), "APS3-BoxUsage:g4dn.xlarge")
        self.assertAlmostEqual(l.gcp_likely, l.monthly_aws)


class MovingTruckAndReport(unittest.TestCase):
    def test_egress_waived_lowers_one_time_cost(self):
        self.assertLess(run({"egress_waived": True}).migration["likely"], run().migration["likely"])

    def test_credits_lower_one_time_cost(self):
        self.assertAlmostEqual(run().migration["likely"] - run({"gcp_credits": 1000}).migration["likely"], 1000)

    def test_stranded_commitments_found(self):
        stranded = next(p for p in run().migration["parts"] if p[0].startswith("Unused AWS"))
        self.assertGreater(stranded[1], 0)

    def test_report_has_every_section(self):
        text = report_card.render(run())
        for heading in ("## Headline", "## How much to trust this", "## Needs a human", "## Moving truck",
                        "## Money not in the comparison", "## Assumptions", "Reconciliation", "(OK)"):
            self.assertIn(heading, text)

    def test_explain_shows_every_step(self):
        text = report_card.explain(run(), "m6g")
        for step in ("[receipt]", "[sorter]", "[twin]", "[price]"):
            self.assertIn(step, text)


if __name__ == "__main__":
    unittest.main()
