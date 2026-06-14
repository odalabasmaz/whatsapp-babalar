import aws_cdk as cdk
from stacks.frontend_stack import FrontendStack

app = cdk.App()

region  = app.node.try_get_context("region")  or "eu-central-1"
account = app.node.try_get_context("account") or None

env = cdk.Environment(region=region, account=account)

FrontendStack(app, "BabalarFrontend", env=env)

app.synth()
