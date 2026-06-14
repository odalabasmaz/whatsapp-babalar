from __future__ import annotations

import boto3
from aws_cdk import Stack, aws_ec2 as ec2
from constructs import Construct


def _cloudfront_prefix_list(region: str) -> str | None:
    """Look up the AWS-managed prefix list for CloudFront origin-facing IPs."""
    try:
        client = boto3.client("ec2", region_name=region)
        resp = client.describe_managed_prefix_lists(
            Filters=[{"Name": "prefix-list-name",
                       "Values": ["com.amazonaws.global.cloudfront.origin-facing"]}]
        )
        return resp["PrefixLists"][0]["PrefixListId"]
    except Exception:
        return None


class NetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        self.vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
            ],
        )

        self.alb_sg = ec2.SecurityGroup(self, "ALBSG", vpc=self.vpc, description="babalar-alb")

        # Restrict ALB ingress to CloudFront edge IPs only
        cf_pl = _cloudfront_prefix_list(self.region)
        if cf_pl:
            self.alb_sg.add_ingress_rule(
                ec2.Peer.prefix_list(cf_pl),
                ec2.Port.tcp(80),
                "CloudFront to ALB",
            )
        else:
            # Fallback if prefix list lookup fails at synth time
            self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP fallback")

        # EC2 only accepts traffic from ALB — no SSH, use SSM
        self.ec2_sg = ec2.SecurityGroup(self, "EC2SG", vpc=self.vpc, description="babalar-backend")
        self.ec2_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8000), "ALB to backend")

        # RDS only accepts traffic from EC2
        self.rds_sg = ec2.SecurityGroup(self, "RDSSG", vpc=self.vpc, description="babalar-rds")
        self.rds_sg.add_ingress_rule(self.ec2_sg, ec2.Port.tcp(5432), "EC2 to RDS")
