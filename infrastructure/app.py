import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.database_stack import DatabaseStack
from stacks.compute_stack import ComputeStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

region  = app.node.try_get_context("region")  or "eu-central-1"
account = app.node.try_get_context("account") or None

env = cdk.Environment(region=region, account=account)

network = NetworkStack(app, "BabalarNetwork", env=env)

database = DatabaseStack(
    app, "BabalarDatabase",
    vpc=network.vpc,
    rds_sg=network.rds_sg,
    env=env,
)

compute = ComputeStack(
    app, "BabalarCompute",
    vpc=network.vpc,
    ec2_sg=network.ec2_sg,
    alb=network.alb,
    db_endpoint=database.instance.db_instance_endpoint_address,
    env=env,
)

frontend = FrontendStack(app, "BabalarFrontend", env=env)

app.synth()
