import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infrastructure.github_deploy_stack import GitHubDeployStack


def synth(**kwargs) -> Template:
    app = cdk.App()
    return Template.from_stack(GitHubDeployStack(app, "Test", repository="AmarDhillon05/hudsonriver", **kwargs))


def test_role_trusts_only_main_of_this_repo():
    statement = next(iter(synth().find_resources("AWS::IAM::Role").values()))["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    assert statement["Condition"] == {"StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:AmarDhillon05/hudsonriver:ref:refs/heads/main",
    }}


def test_role_can_only_assume_cdk_bootstrap_roles():
    policy = next(iter(synth().find_resources("AWS::IAM::Policy").values()))["Properties"]["PolicyDocument"]
    [statement] = policy["Statement"]
    assert statement["Action"] == ["sts:AssumeRole", "sts:TagSession"]
    assert "cdk-hnb659fds-*" in str(statement["Resource"])


def test_reuses_existing_oidc_provider_by_default():
    synth().resource_count_is("AWS::IAM::OIDCProvider", 0)
    synth(create_oidc_provider=True).resource_count_is("AWS::IAM::OIDCProvider", 1)


def test_rejects_malformed_repository():
    with pytest.raises(ValueError):
        GitHubDeployStack(cdk.App(), "Bad", repository="hudsonriver")
