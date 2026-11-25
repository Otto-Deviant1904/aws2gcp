import csv

COLUMNS = [
    "identity/LineItemId", "bill/BillingEntity", "bill/BillingPeriodStartDate", "bill/BillingPeriodEndDate",
    "lineItem/UsageAccountId", "lineItem/LineItemType", "lineItem/UsageStartDate", "lineItem/UsageEndDate",
    "lineItem/ProductCode", "lineItem/UsageType", "lineItem/Operation", "lineItem/ResourceId",
    "lineItem/UsageAmount", "lineItem/CurrencyCode", "lineItem/UnblendedCost", "pricing/publicOnDemandCost",
    "pricing/unit", "product/region", "product/operatingSystem", "product/preInstalledSw",
    "product/databaseEngine", "reservation/EffectiveCost", "reservation/EndTime",
    "savingsPlan/SavingsPlanEffectiveCost", "savingsPlan/EndTime",
]

ROWS = [
    ("Usage", "AmazonEC2", "APS3-BoxUsage:t3.medium", "RunInstances", "i-web1", 720, 32.26, {}),
    ("SavingsPlanCoveredUsage", "AmazonEC2", "APS3-BoxUsage:m5.large", "RunInstances", "i-api1", 720, 72.72,
     {"savingsPlan/SavingsPlanEffectiveCost": "50.90"}),
    ("SavingsPlanNegation", "ComputeSavingsPlans", "ComputeSP:1yrNoUpfront", "", "i-api1", 720, -72.72, {}),
    ("SavingsPlanRecurringFee", "ComputeSavingsPlans", "ComputeSP:1yrNoUpfront", "", "sp-1", 720, 55.00,
     {"savingsPlan/EndTime": "2027-06-30T00:00:00Z"}),
    ("DiscountedUsage", "AmazonEC2", "APS3-BoxUsage:c5.xlarge", "RunInstances", "i-batch1", 720, 0.0,
     {"reservation/EffectiveCost": "85.00", "pricing/publicOnDemandCost": "122.40"}),
    ("RIFee", "AmazonEC2", "APS3-HeavyUsage:c5.xlarge", "RunInstances", "ri-1", 720, 85.00,
     {"reservation/EndTime": "2027-03-31T00:00:00Z"}),
    ("Usage", "AmazonEC2", "APS3-BoxUsage:m6g.large", "RunInstances", "i-arm1", 360, 27.72, {}),
    ("Usage", "AmazonEC2", "APS3-BoxUsage:t3.large", "RunInstances:0002", "i-win1", 720, 79.78,
     {"product/operatingSystem": "Windows"}),
    ("Usage", "AmazonEC2", "APS3-SpotUsage:m5.xlarge", "RunInstances:SV001", "i-spot1", 200, 14.00, {}),
    ("Usage", "AmazonEC2", "APS3-CPUCredits:t3", "RunInstances", "i-web1", 30, 1.50, {}),
    ("Usage", "AmazonLightsail", "APS3-BundleUsage:4GB", "", "ls-blog", 720, 23.22, {}),
    ("Usage", "AmazonEC2", "APS3-BoxUsage:g4dn.xlarge", "RunInstances", "i-gpu1", 100, 57.90, {}),
    ("Usage", "AmazonEC2", "APS3-EBS:VolumeUsage.gp3", "CreateVolume-Gp3", "vol-1", 500, 45.60, {}),
    ("Usage", "AmazonEC2", "APS3-EBS:VolumeP-IOPS.gp3", "CreateVolume-Gp3", "vol-1", 2000, 11.40, {}),
    ("Usage", "AmazonEC2", "APS3-EBS:SnapshotUsage", "CreateSnapshot", "snap-1", 300, 15.00, {}),
    ("Usage", "AmazonS3", "APS3-TimedStorage-ByteHrs", "StandardStorage", "assets-bucket", 2000, 50.00, {}),
    ("Usage", "AmazonS3", "APS3-TimedStorage-GDA-ByteHrs", "DeepArchiveStorage", "archive-bucket", 5000, 10.00, {}),
    ("Usage", "AmazonS3", "APS3-Requests-Tier1", "PutObject", "assets-bucket", 1_000_000, 5.00, {}),
    ("Usage", "AmazonS3", "APS3-Requests-Tier2", "GetObject", "assets-bucket", 10_000_000, 4.00, {}),
    ("Usage", "AmazonRDS", "APS3-Multi-AZUsage:db.m5.large", "CreateDBInstance:0014", "db-main", 720, 266.40,
     {"product/databaseEngine": "PostgreSQL"}),
    ("Usage", "AmazonRDS", "APS3-RDS:Multi-AZ-GP2-Storage", "CreateDBInstance:0014", "db-main", 200, 55.20, {}),
    ("Usage", "AmazonRDS", "APS3-InstanceUsage:db.r6g.large", "CreateDBInstance:0021", "db-aurora", 720, 208.80,
     {"product/databaseEngine": "Aurora PostgreSQL"}),
    ("Usage", "AmazonRDS", "APS3-Aurora:StorageIOUsage", "CreateDBInstance:0021", "db-aurora", 50_000_000, 11.00, {}),
    ("Usage", "AmazonRDS", "APS3-RDS:ChargedBackupUsage", "CreateDBInstance:0014", "db-main", 100, 9.50, {}),
    ("Usage", "AmazonEC2", "APS3-NatGateway-Hours", "NatGateway", "nat-1", 720, 40.32, {}),
    ("Usage", "AmazonEC2", "APS3-NatGateway-Bytes", "NatGateway", "nat-1", 500, 28.00, {}),
    ("Usage", "AWSDataTransfer", "APS3-DataTransfer-Out-Bytes", "", "", 1000, 109.30, {}),
    ("Usage", "AWSDataTransfer", "APS3-DataTransfer-Regional-Bytes", "InterZone-In", "", 2000, 20.00, {}),
    ("Usage", "AmazonVPC", "APS3-PublicIPv4:InUseAddress", "AssociateAddress", "ip-1", 2160, 10.80, {}),
    ("Usage", "AWSELB", "APS3-LoadBalancerUsage", "LoadBalancing:Application", "alb-1", 720, 17.21, {}),
    ("Usage", "AWSELB", "APS3-LCUUsage", "LoadBalancing:Application", "alb-1", 1000, 8.00, {}),
    ("Usage", "AmazonEKS", "APS3-AmazonEKS-Hours:perCluster", "CreateOperation", "eks-1", 720, 72.00, {}),
    ("Usage", "AmazonRoute53", "HostedZone", "", "zone-1", 2, 1.00, {"product/region": "global"}),
    ("Usage", "AWSLambda", "APS3-Request", "Invoke", "fn-1", 5_000_000, 1.00, {}),
    ("Usage", "AWSLambda", "APS3-Lambda-GB-Second", "Invoke", "fn-1", 100_000, 1.67, {}),
    ("Usage", "AmazonCloudWatch", "APS3-DataProcessing-Bytes", "PutLogEvents", "", 30, 20.10, {}),
    ("Usage", "prod-abc123", "SoftwareUsage:standard", "", "", 1, 99.00, {"bill/BillingEntity": "AWS Marketplace"}),
    ("Usage", "AWSSupportBusiness", "Dollar", "", "", 1, 100.00, {}),
    ("Usage", "AmazonSageMaker", "APS3-Notebk:ml.t3.medium", "RunInstance", "nb-1", 50, 2.50, {}),
    ("Tax", "AmazonEC2", "Tax", "", "", 1, 150.00, {}),
    ("Credit", "AmazonEC2", "Credit", "", "", 1, -200.00, {}),
    ("Refund", "AmazonEC2", "Refund", "", "", 1, -10.00, {}),
    ("Fee", "AmazonEC2", "APS3-HeavyUsage:c5.xlarge", "", "ri-2", 1, 120.00, {}),
]


def write_sample(path, month_start="2026-11-01T00:00:00Z", month_end="2026-12-01T00:00:00Z",
                 last_usage=None) -> None:
    last_usage = last_usage or month_end
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for i, (ltype, product, usage, op, res, amount, cost, extra) in enumerate(ROWS, start=1):
            row = {c: "" for c in COLUMNS}
            row.update({
                "identity/LineItemId": f"li-{i}",
                "bill/BillingEntity": "AWS",
                "bill/BillingPeriodStartDate": month_start,
                "bill/BillingPeriodEndDate": month_end,
                "lineItem/UsageAccountId": "111122223333",
                "lineItem/LineItemType": ltype,
                "lineItem/UsageStartDate": month_start,
                "lineItem/UsageEndDate": last_usage,
                "lineItem/ProductCode": product,
                "lineItem/UsageType": usage,
                "lineItem/Operation": op,
                "lineItem/ResourceId": res,
                "lineItem/UsageAmount": str(amount),
                "lineItem/CurrencyCode": "USD",
                "lineItem/UnblendedCost": f"{cost:.2f}",
                "pricing/publicOnDemandCost": f"{cost:.2f}" if ltype == "Usage" else "",
                "product/region": "ap-south-1",
            })
            row.update(extra)
            w.writerow(row)
