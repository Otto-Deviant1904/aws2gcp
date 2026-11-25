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

## known issues
- gcp prices are approx, not verified yet
- only mumbai (asia-south1) prices
- only CUR works, not the console "download csv"
- gpu / sql server / oracle / marketplace -> marked "needs a human"
- only tested on one small real CUR (mostly lightsail), no big EC2/RDS bill yet
