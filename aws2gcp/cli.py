import argparse
import sys
from pathlib import Path

from . import config, pipeline, report_card
from .receipt import ReceiptError
from .sample import write_sample


def _common(p):
    p.add_argument("bills", nargs="+", help="CUR .csv / .csv.gz files or folders")
    p.add_argument("--prices", help="use a different prices.yaml")
    p.add_argument("--assumptions", help="use a different assumptions.yaml")
    p.add_argument("--gcp-cud", choices=["none", "1y", "3y"], help="price GCP with a committed-use discount")
    p.add_argument("--network-tier", choices=["premium", "standard"])
    p.add_argument("--perf-factor", type=float, help="1.2 = GCP needs 20%% more compute for the same work")
    p.add_argument("--no-gke-free-cluster", dest="gke_free_cluster", action="store_false", default=None)
    p.add_argument("--gcp-credits", type=float, help="GCP credits in USD (startup program etc.)")
    p.add_argument("--aws-retention-discount", type=float, help="0.1 = AWS offers 10%% off to stay")
    p.add_argument("--overlap-months", type=int, help="months paying both clouds")
    p.add_argument("--egress-waived", action="store_true", default=None, help="AWS waives exit data transfer")
    p.add_argument("--labor-rate", type=float, help="engineer cost in USD per hour")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aws2gcp", description="Estimate an AWS bill on Google Cloud.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    conv = sub.add_parser("convert", help="write the full report")
    _common(conv)
    conv.add_argument("-o", "--out", help="write report to this file instead of the screen")
    exp = sub.add_parser("explain", help="show how lines matching TEXT were decided")
    _common(exp)
    exp.add_argument("--match", required=True, help="text in the UsageType or resource id")
    smp = sub.add_parser("sample", help="write a fake CUR file to try the tool")
    smp.add_argument("out")
    ref = sub.add_parser("refresh-prices", help="update prices.yaml from google's billing catalog api")
    ref.add_argument("--prices", help="prices.yaml to update (default: the built-in one)")
    ref.add_argument("--region", help="gcp region, e.g. asia-south1 (default: the one in prices.yaml)")
    ref.add_argument("--dry-run", action="store_true", help="show changes, dont write")
    ref.add_argument("--summary", help="also write the change table to this markdown file")
    args = ap.parse_args(argv)

    if args.cmd == "refresh-prices":
        from . import refresh_prices
        return refresh_prices.main(args)

    if args.cmd == "sample":
        write_sample(args.out)
        print(f"Fake bill written to {args.out}. Try: aws2gcp convert {args.out}")
        return 0

    data = config.load_all(args.prices, args.assumptions)
    flags = {k: getattr(args, k) for k in config.FLAG_PATHS}
    settings = config.apply_flags(data["settings"], flags)
    try:
        result = pipeline.run(args.bills, data, settings)
    except ReceiptError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    text = report_card.render(result) if args.cmd == "convert" else report_card.explain(result, args.match)
    if getattr(args, "out", None):
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Report written to {args.out}")
    else:
        print(text)
    return 0
