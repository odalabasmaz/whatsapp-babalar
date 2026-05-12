from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_secretsmanager as sm,
    CfnOutput,
)
from constructs import Construct


class DatabaseStack(Stack):
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, rds_sg: ec2.SecurityGroup, **kwargs):
        super().__init__(scope, id, **kwargs)

        # DB şifresi Secrets Manager'dan
        self.db_secret = sm.Secret.from_secret_name_v2(self, "DBSecret", "babalar/db-password")

        self.instance = rds.DatabaseInstance(
            self, "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
            instance_type=ec2.InstanceType("t4g.micro"),  # Graviton2, ~$13/ay
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_sg],
            database_name="babalar",
            credentials=rds.Credentials.from_secret(self.db_secret, username="babalar"),
            storage_type=rds.StorageType.GP3,
            allocated_storage=20,
            multi_az=False,
            backup_retention=Duration.days(7),
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
            # pgvector extension — RDS Parameter Group
            parameter_group=rds.ParameterGroup(
                self, "PG",
                engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
                parameters={"shared_preload_libraries": "pg_stat_statements"},
            ),
        )

        CfnOutput(self, "DBEndpoint", value=self.instance.db_instance_endpoint_address)
