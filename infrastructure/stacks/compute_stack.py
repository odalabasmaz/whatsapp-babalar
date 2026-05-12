from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_autoscaling as asg,
    CfnOutput,
)
from constructs import Construct


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        vpc: ec2.Vpc,
        ec2_sg: ec2.SecurityGroup,
        alb: elbv2.ApplicationLoadBalancer,
        db_endpoint: str,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        repo_url   = self.node.try_get_context("repo_url")  or ""
        key_pair   = self.node.try_get_context("key_pair")  or ""
        region     = self.region

        # IAM Role — Secrets Manager okuma + CloudWatch Logs
        role = iam.Role(
            self, "EC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")],
        )
        role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[f"arn:aws:secretsmanager:{region}:*:secret:babalar/*"],
        ))

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(f"""
set -euo pipefail
exec > /var/log/babalar-setup.log 2>&1
echo "[babalar] EC2 setup başlıyor..."

# Paket kurulumu
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose v2 plugin (ARM64 / Graviton)
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.27.1/docker-compose-linux-aarch64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Repo klonla
git clone {repo_url} /app
cd /app

# Secrets Manager'dan değerleri oku
get_secret() {{
  aws secretsmanager get-secret-value \
    --region {region} --secret-id "$1" \
    --query SecretString --output text
}}

DB_PASSWORD=$(get_secret babalar/db-password | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")
OPENAI_API_KEY=$(get_secret babalar/openai-api-key)
JWT_SECRET=$(get_secret babalar/jwt-secret)
INGEST_API_KEY=$(get_secret babalar/ingest-api-key)

# .env oluştur
cat > /app/.env << ENVEOF
DATABASE_URL=postgresql+asyncpg://babalar:${{DB_PASSWORD}}@{db_endpoint}:5432/babalar
OPENAI_API_KEY=${{OPENAI_API_KEY}}
JWT_SECRET=${{JWT_SECRET}}
JWT_ACCESS_TTL_MINUTES=60
JWT_REFRESH_TTL_DAYS=30
INGEST_API_KEY=${{INGEST_API_KEY}}
BACKEND_URL=http://backend:8000
INGEST_CRON=0 2 * * *
ENVIRONMENT=production
LOG_LEVEL=INFO
ENVEOF

# Servisleri başlat
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d

# Backend hazır olana kadar bekle
echo "[babalar] Backend bekleniyor..."
for i in $(seq 1 24); do
  if curl -sf http://localhost:8000/health; then
    echo "[babalar] Backend hazır."
    break
  fi
  sleep 5
done

# DB migration
docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head

echo "[babalar] Setup tamamlandı."
echo "[babalar] Admin kurmak için: docker compose -f docker-compose.prod.yml exec backend python -m app.cli setup"
""")

        lt = ec2.LaunchTemplate(
            self, "LaunchTemplate",
            instance_type=ec2.InstanceType("t4g.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=ec2.AmazonLinuxCpuType.ARM_64),
            security_group=ec2_sg,
            role=role,
            user_data=user_data,
            key_pair=ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_pair) if key_pair else None,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(20, volume_type=ec2.EbsDeviceVolumeType.GP3),
                )
            ],
        )

        self.asg = asg.AutoScalingGroup(
            self, "ASG",
            vpc=vpc,
            launch_template=lt,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            min_capacity=1,
            max_capacity=1,
            desired_capacity=1,
        )

        tg = elbv2.ApplicationTargetGroup(
            self, "TargetGroup",
            vpc=vpc,
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.asg],
            health_check=elbv2.HealthCheck(path="/health", healthy_http_codes="200"),
        )

        alb.add_listener("HTTP", port=80, default_action=elbv2.ListenerAction.redirect(
            protocol="HTTPS", port="443", permanent=True,
        ))
        alb.add_listener("HTTPS", port=443, default_target_groups=[tg])

        CfnOutput(self, "ASGName", value=self.asg.auto_scaling_group_name)
