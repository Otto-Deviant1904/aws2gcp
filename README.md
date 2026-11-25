# aws2gcp

Takes an AWS CUR (cost and usage report) and estimates what the same stuff would cost on GCP + how much the move itself costs + break-even.

needs python 3.10+ and pyyaml (`pip install pyyaml`)

```
python3 -m aws2gcp sample examples/sample_cur.csv      # makes a fake bill
python3 -m aws2gcp convert examples/sample_cur.csv -o report.md
python3 -m aws2gcp explain examples/sample_cur.csv --match t3.medium   # why a row got its price
python3 -m unittest discover -s tests -t .
```

For a real bill download the CUR files from the s3 bucket and pass the folder.

flags: `--gcp-cud 1y|3y`, `--egress-waived`, `--network-tier standard`, `--gcp-credits N`, `--overlap-months N`, `--labor-rate N` (see `python3 -m aws2gcp convert -h`)

Steps: receipt.py -> sorter.py -> twin_finder.py -> price_tag.py -> moving_truck.py -> report_card.py. prices/assumptions are in `aws2gcp/data/*.yaml`.

Example output: examples/sample_report.md

## keeping prices up to date

GCP prices are in `aws2gcp/data/prices.yaml`. Refresh them live, no key needed:

```
python3 -m aws2gcp refresh-prices --dry-run   # show what would change
python3 -m aws2gcp refresh-prices             # update prices.yaml
```

Which google SKU fills which price is in `aws2gcp/data/price_skus.yaml`. Stuff not listed there (egress tiers, NAT, discounts) is still typed by hand.

Without a key it reads the public [pricing.yml](https://github.com/Cyclenerd/google-cloud-pricing-cost-calculator) which gets rebuilt weekly from google's billing api. vcpu/ram prices are worked out from 2 machine sizes (e.g. n2-standard-2 vs n2-highcpu-2). Cloud SQL isnt in that file so its still by hand.

If you set `GCP_PRICING_API_KEY` (google cloud api key, Cloud Billing API on) it asks google directly instead, and cloud sql gets updated too.

`.github/workflows/refresh-prices.yml` runs this every monday. If a price changed it opens a PR with an old -> new table, otherwise it just bumps the date. The api key secret is optional.

## known issues
- compute, disk, gcs storage, ip, nat, egress (first TB) come from the live refresh. cloud sql checked by hand 2026-11-25. discounts, gcs ops, lb, standard tier egress still approx
- only mumbai (asia-south1) prices
- only CUR works, not the console "download csv"
- gpu / sql server / oracle / marketplace -> marked "needs a human"
- only tested on one small real CUR (mostly lightsail), no big EC2/RDS bill yet
