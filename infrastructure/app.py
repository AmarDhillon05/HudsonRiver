#!/usr/bin/env python3
"""CDK entry point. Use the Makefile, which passes the context below.

    make deploy               # LaptopDealAlert: the Lambda, table and schedules
    make deploy-github-role   # once: the role GitHub Actions uses to auto-deploy
"""

from __future__ import annotations

import os
import sys

import aws_cdk as cdk

from github_deploy_stack import GitHubDeployStack
from stack import DealAlertStack

app = cdk.App()
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

ntfy_topic = app.node.try_get_context("ntfyTopic") or os.environ.get("NTFY_TOPIC")
if not ntfy_topic:
    sys.exit("Set the ntfy topic: cdk deploy -c ntfyTopic=<topic> (the Makefile defaults it)")

DealAlertStack(
    app,
    "LaptopDealAlert",
    description="Watches laptop prices and pushes deals to ntfy",
    ntfy_topic=ntfy_topic,
    ntfy_server=str(app.node.try_get_context("ntfyServer") or "https://ntfy.sh"),
    # Optional, from developer.bestbuy.com. Without it only Slickdeals is checked.
    bestbuy_api_key=app.node.try_get_context("bestbuyApiKey") or os.environ.get("BESTBUY_API_KEY") or None,
    interval_minutes=int(app.node.try_get_context("intervalMinutes") or 30),
    # 13:00 UTC is 9am Eastern in summer, 8am in winter.
    summary_hour_utc=int(app.node.try_get_context("summaryHourUtc") or 13),
    env=env,
)

GitHubDeployStack(
    app,
    "LaptopDealAlertGitHubDeploy",
    description="Lets GitHub Actions (OIDC, one repo and branch) deploy LaptopDealAlert",
    repository=str(app.node.try_get_context("githubRepo") or "AmarDhillon05/hudsonriver"),
    branch=str(app.node.try_get_context("githubBranch") or "main"),
    create_oidc_provider=str(app.node.try_get_context("githubCreateOidcProvider")).lower() == "true",
    env=env,
)

app.synth()
