#!/usr/bin/env python3
"""CDK entry point.

    cd infrastructure && cdk synth -c ntfyTopic=dummy     # validate, no credentials needed
    cd infrastructure && cdk deploy -c ntfyTopic=<topic>  # deploy to your account
"""

from __future__ import annotations

import os
import sys

import aws_cdk as cdk

from stack import DealAlertStack

app = cdk.App()

ntfy_topic = app.node.try_get_context("ntfyTopic") or os.environ.get("NTFY_TOPIC")
if not ntfy_topic:
    sys.exit("Set your private ntfy topic: cdk deploy -c ntfyTopic=<topic> (or NTFY_TOPIC=...)")

DealAlertStack(
    app,
    "LaptopDealAlert",
    description="Watches laptop prices and pushes deals to ntfy",
    ntfy_topic=ntfy_topic,
    ntfy_server=str(app.node.try_get_context("ntfyServer") or "https://ntfy.sh"),
    # Optional, free from developer.bestbuy.com. Without it only Slickdeals is checked.
    bestbuy_api_key=app.node.try_get_context("bestbuyApiKey") or os.environ.get("BESTBUY_API_KEY") or None,
    interval_minutes=int(app.node.try_get_context("intervalMinutes") or 30),
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)

app.synth()
