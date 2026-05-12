from aws_cdk import Stack, aws_ec2 as ec2, aws_elasticloadbalancingv2 as elbv2, CfnOutput
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        self.vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=0,  # EC2 public subnet'te, NAT Gateway yok
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
            ],
        )

        # EC2 Security Group — sadece ALB'den gelen trafiğe izin ver
        self.ec2_sg = ec2.SecurityGroup(self, "EC2SG", vpc=self.vpc, description="babalar-backend")
        self.ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH (geçici, production'da kaldır)")

        # ALB Security Group
        self.alb_sg = ec2.SecurityGroup(self, "ALBSG", vpc=self.vpc, description="babalar-alb")
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirect")

        # EC2 sadece ALB'den gelen 8000 portunu kabul etsin
        self.ec2_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8000), "ALB → backend")

        # RDS Security Group — sadece EC2'den
        self.rds_sg = ec2.SecurityGroup(self, "RDSSG", vpc=self.vpc, description="babalar-rds")
        self.rds_sg.add_ingress_rule(self.ec2_sg, ec2.Port.tcp(5432), "EC2 → RDS")

        # ALB
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "ALB",
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        CfnOutput(self, "AlbDnsName", value=self.alb.load_balancer_dns_name)
