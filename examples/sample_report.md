# AWS to GCP cost report

Prices: GCP asia-south1, snapshot 2026-11-23, verified: False. All amounts USD per standard 730-hour month, tax excluded.

## Warnings

- GCP prices are an APPROXIMATE snapshot (prices.yaml verified: false). Check them before quoting a client.
- 9% of AWS spend uses RIs / Savings Plans, but GCP is priced without commitments. For a fair match try --gcp-cud 1y.

## Headline

| | Monthly |
|---|---|
| AWS today (after RI/SP discounts, before credits) | $1,617.23 |
| AWS at list price (no discounts) | $1,677.28 |
| AWS if cleaned up first (rough, -15%) | $1,374.65 |
| GCP estimate | $1,428.73 ($1,143.56 .. $1,712.77) |
| Monthly saving (likely) | $188.50 (12% of AWS) |

One-time moving cost: $10,914.47 ($7,640.13 .. $14,188.81)

Break-even: likely 57.9 months; best case 16.1 months; worst case never (GCP is not cheaper).

Note: AWS credits paid $202.78 this month. Real spend before credits is the AWS figure above.

## How much to trust this

Share of the AWS bill matched: exact 32%, close 50%, assumed 8%, needs a human 10%.

- exact: same product and shape (+/- 5%)
- close: same job, different shape or pricing rules (+/- 20%)
- assumed: GCP service exists, but we copied the AWS cost (+/- 30%)
- needs a human: no safe twin; AWS cost copied as a placeholder (+/- 50%)

## Needs a human (most expensive first)

| AWS monthly | Product | UsageType | Why |
|---:|---|---|---|
| $100.38 | prod-abc123 | `SoftwareUsage:standard` | sold through AWS Marketplace: third-party licence, may not move to GCP |
| $58.70 | AmazonEC2 | `APS3-BoxUsage:g4dn.xlarge` | instance type 'g4dn.xlarge' not understood (GPU, storage-optimised, metal or a new family) |
| $2.53 | AmazonSageMaker | `APS3-Notebk:ml.t3.medium` | no rule matched 'Notebk:ml.t3.medium' (AmazonSageMaker) -> needs a human |

## By group

| Group | AWS | GCP likely | GCP range |
|---|---:|---:|---|
| database | $558.55 | $463.49 | $415.54 .. $511.43 |
| compute | $377.45 | $465.13 | $357.38 .. $568.09 |
| network | $236.87 | $199.08 | $160.10 .. $238.07 |
| storage | $142.96 | $133.02 | $113.41 .. $152.63 |
| human | $102.91 | $102.91 | $51.45 .. $154.36 |
| support | $101.39 | $41.61 | $29.13 .. $54.10 |
| kubernetes | $73.00 | $0.00 | $0.00 .. $3.65 |
| managed | $23.09 | $23.09 | $16.16 .. $30.01 |
| dns | $1.01 | $0.41 | $0.39 .. $0.43 |

## Top lines

| AWS | GCP likely | Confidence | AWS UsageType | GCP twin |
|---:|---:|---|---|---|
| $270.10 | $222.50 | exact | `APS3-Multi-AZUsage:db.m5.large` | Cloud SQL PostgreSQL 2 vCPU / 8 GB HA |
| $211.70 | $156.22 | close | `APS3-InstanceUsage:db.r6g.large` | Cloud SQL PostgreSQL 2 vCPU / 16 GB |
| $110.82 | $121.67 | close | `APS3-DataTransfer-Out-Bytes` | internet egress (premium) |
| $101.39 | $41.61 | assumed | `Dollar` | Google Cloud Customer Care |
| $100.38 | $100.38 | human | `SoftwareUsage:standard` | needs a human |
| $86.18 | $108.67 | close | `APS3-BoxUsage:c5.xlarge` | n2-custom-4-8192 |
| $80.89 | $120.89 | close | `APS3-BoxUsage:t3.large` | e2-standard-2 |
| $73.00 | $0.00 | exact | `APS3-AmazonEKS-Hours:perCluster` | GKE cluster fee |
| $58.70 | $58.70 | human | `APS3-BoxUsage:g4dn.xlarge` | needs a human |
| $55.97 | $75.84 | exact | `APS3-RDS:Multi-AZ-GP2-Storage` | Cloud SQL SSD storage (HA) |
| $51.61 | $62.75 | exact | `APS3-BoxUsage:m5.large` | n2-standard-2 |
| $50.69 | $46.64 | exact | `APS3-TimedStorage-ByteHrs` | GCS standard |
| $46.23 | $55.76 | close | `APS3-EBS:VolumeUsage.gp3` | pd-balanced |
| $40.88 | $7.15 | close | `APS3-NatGateway-Hours` | Cloud NAT gateway |
| $32.71 | $26.86 | close | `APS3-BoxUsage:t3.medium` | e2-medium |
| $28.39 | $22.81 | close | `APS3-NatGateway-Bytes` | Cloud NAT data processing |
| $28.10 | $34.89 | close | `APS3-BoxUsage:m6g.large` | c4a-standard-2 |
| $23.54 | $39.31 | close | `APS3-BundleUsage:4GB` | e2-medium + 80GB pd-balanced |
| $20.38 | $20.38 | assumed | `APS3-DataProcessing-Bytes` | Cloud Logging + Cloud Monitoring |
| $20.28 | $10.14 | close | `APS3-DataTransfer-Regional-Bytes` | inter-zone traffic |
| $17.45 | $18.25 | close | `APS3-LoadBalancerUsage` | Cloud Load Balancing forwarding rule |
| $15.21 | $8.82 | close | `APS3-EBS:SnapshotUsage` | PD snapshot |
| $14.19 | $13.04 | close | `APS3-SpotUsage:m5.xlarge` | n2-standard-4 |
| $11.56 | $0.00 | close | `APS3-EBS:VolumeP-IOPS.gp3` | included in Persistent Disk size |
| $11.15 | $0.00 | close | `APS3-Aurora:StorageIOUsage` | no I/O charge on Cloud SQL |

Run `aws2gcp explain <bill> --match <text>` to see how any line was decided.

## Moving truck (one-time)

| Part | Cost | How |
|---|---:|---|
| Data egress out of AWS | $702.62 | 7,807 GB x $0.09/GB |
| Reading back archived S3 data | $101.39 | 5,069 GB x $0.02/GB |
| Engineering labor | $8,100.00 | 270 h x $30/h (base 80 h, 7 compute x 4 h, 2 database x 16 h, 1 dns x 2 h, 1 kubernetes x 40 h, 2 managed x 8 h, 5 network x 4 h, 4 storage x 1 h, 3 needs-a-human x 16 h) |
| Running both clouds (overlap) | $1,428.73 | 1 month(s) of GCP while AWS still runs |
| Unused AWS commitments after move | $581.72 | monthly fee x months left after the move |
| **Total (likely)** | **$10,914.47** | range $7,640.13 .. $14,188.81 |

## Money not in the comparison

| Bucket | Per month | Meaning |
|---|---:|---|
| commitment | $263.61 | RI and Savings Plan fees (already counted via effective cost) |
| credit | -$202.78 | promotional credits |
| refund | -$10.14 | refunds |
| sp_negation | -$73.73 | Savings Plan cancel-out rows (ignored on purpose) |
| tax | $152.08 | GST / tax; GCP charges tax too, so it is left out |
| workload | $1,553.18 | usage that was compared above (row cost, before RI/SP effective cost) |

Reconciliation: buckets add up to the bill total $1,659.18 (OK).

## Assumptions

| Setting | Value | Change with |
|---|---|---|
| hours_per_month | 730 | edit assumptions.yaml |
| fx_to_usd | {'USD': 1.0, 'INR': 0.012} | edit assumptions.yaml |
| confidence_band | {'exact': 0.05, 'close': 0.2, 'assumed': 0.3, 'human': 0.5} | edit assumptions.yaml |
| gcp.cud | none | --gcp-cud |
| gcp.network_tier | premium | --network-tier |
| gcp.perf_factor | 1.0 | --perf-factor |
| gcp.gke_free_cluster | True | --no-gke-free-cluster |
| gcp.support_pct | 0.03 | edit assumptions.yaml |
| gcp.support_min_monthly | 29 | edit assumptions.yaml |
| gcp.credits_usd | 0 | --gcp-credits |
| aws.optimisation_pct | 0.15 | edit assumptions.yaml |
| aws.retention_discount_pct | 0 | --aws-retention-discount |
| migration.overlap_months | 1 | --overlap-months |
| migration.egress_usd_per_gb | 0.09 | edit assumptions.yaml |
| migration.egress_waived | False | --egress-waived |
| migration.archive_retrieval_usd_per_gb | 0.02 | edit assumptions.yaml |
| migration.band | 0.3 | edit assumptions.yaml |
| migration.labor.rate_usd_per_hour | 30 | --labor-rate |
| migration.labor.base_project_hours | 80 | edit assumptions.yaml |
| migration.labor.hours_per_resource | {'compute': 4, 'storage': 1, 'database': 16, 'network': 4, 'kubernetes': 40, 'dns': 2, 'managed': 8} | edit assumptions.yaml |
| migration.labor.hours_per_human_item | 16 | edit assumptions.yaml |
| stale_price_days | 60 | edit assumptions.yaml |
