"""The role GitHub Actions assumes to deploy LaptopDealAlert.

Deployed ONCE, by hand (``make deploy-github-role``); from then on every push to
``main`` redeploys through ``.github/workflows/deploy.yml``.

No AWS keys are stored in GitHub. The workflow exchanges a short-lived GitHub
OIDC token for this role, which trusts only this repository's ``main`` branch
and may do nothing but assume the roles ``cdk bootstrap`` created.

An account holds one GitHub OIDC provider. By default this reuses the one that
already exists (the jobs repo created it); pass ``-c githubCreateOidcProvider=true``
in an account that has none.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

GITHUB_OIDC_HOST = "token.actions.githubusercontent.com"
CDK_QUALIFIER = "hnb659fds"  # what `cdk bootstrap` uses unless told otherwise


class GitHubDeployStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        repository: str,
        branch: str = "main",
        create_oidc_provider: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if repository.count("/") != 1:
            raise ValueError(f"repository must be 'owner/name', got {repository!r}")

        if create_oidc_provider:
            provider_arn = iam.CfnOIDCProvider(
                self, "GitHubOidc", url=f"https://{GITHUB_OIDC_HOST}", client_id_list=["sts.amazonaws.com"]
            ).attr_arn
        else:
            provider_arn = f"arn:{self.partition}:iam::{self.account}:oidc-provider/{GITHUB_OIDC_HOST}"

        role = iam.Role(
            self,
            "DeployRole",
            description=f"GitHub Actions deploys LaptopDealAlert from {repository}@{branch}",
            max_session_duration=Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider_arn,
                conditions={
                    "StringEquals": {
                        f"{GITHUB_OIDC_HOST}:aud": "sts.amazonaws.com",
                        # Exact match: no other repository, branch, tag or pull request.
                        f"{GITHUB_OIDC_HOST}:sub": f"repo:{repository}:ref:refs/heads/{branch}",
                    },
                },
            ),
        )
        role.add_to_policy(iam.PolicyStatement(
            sid="UseTheCdkBootstrapRoles",
            actions=["sts:AssumeRole", "sts:TagSession"],
            resources=[f"arn:{self.partition}:iam::{self.account}:role/cdk-{CDK_QUALIFIER}-*"],
        ))

        CfnOutput(self, "DeployRoleArn", value=role.role_arn,
                  description="Set as the AWS_DEPLOY_ROLE_ARN repository variable on GitHub")
