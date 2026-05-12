from aws_cdk import (
    Stack, RemovalPolicy,
    aws_s3 as s3,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    aws_certificatemanager as acm,
    CfnOutput,
)
from constructs import Construct


class FrontendStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        domain   = self.node.try_get_context("domain")
        cert_arn = self.node.try_get_context("cert_arn")

        bucket = s3.Bucket(
            self, "FrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # SSL sertifikası (cert_arn ve domain verilmişse bağla)
        certificate = None
        domain_names = None
        if cert_arn and domain:
            certificate  = acm.Certificate.from_certificate_arn(self, "Cert", cert_arn)
            domain_names = [domain]

        distribution = cf.Distribution(
            self, "Distribution",
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            price_class=cf.PriceClass.PRICE_CLASS_100,
            geo_restriction=cf.GeoRestriction.allowlist("DE"),
            error_responses=[
                cf.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html"),
            ],
            domain_names=domain_names,
            certificate=certificate,
        )

        s3deploy.BucketDeployment(
            self, "Deploy",
            sources=[s3deploy.Source.asset("../babalar-frontend/dist")],
            destination_bucket=bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        CfnOutput(self, "CloudFrontURL", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
