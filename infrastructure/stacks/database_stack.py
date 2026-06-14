import aws_cdk as cdk
from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_rds as rds,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class DatabaseStack(Stack):
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, rds_sg: ec2.SecurityGroup, **kwargs):
        super().__init__(scope, id, **kwargs)

        self.instance = rds.DatabaseInstance(
            self, "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
            instance_type=ec2.InstanceType("t4g.micro"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_sg],
            database_name="babalar",
            # Reference password field directly — avoids SecretTargetAttachment
            # which requires both "username" and "password" keys in the secret.
            credentials=rds.Credentials.from_username(
                "babalar",
                password=cdk.SecretValue.secrets_manager(
                    "babalar/db-password",
                    json_field="password",
                ),
            ),
            storage_type=rds.StorageType.GP3,
            allocated_storage=20,
            multi_az=False,
            backup_retention=Duration.days(7),
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
            parameter_group=rds.ParameterGroup(
                self, "PG",
                engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
                parameters={"shared_preload_libraries": "pg_stat_statements"},
            ),
        )

        CfnOutput(self, "DBEndpoint", value=self.instance.db_instance_endpoint_address)
