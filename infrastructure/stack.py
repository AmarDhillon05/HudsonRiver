"""The whole deployment: one scheduled Lambda and one small DynamoDB table.

Sized to stay inside AWS's always-free tiers:
- Lambda: ~1,500 runs a month at 128 MB on ARM is a tiny fraction of the
  always-free 1M requests / 400,000 GB-seconds.
- DynamoDB on-demand: a few thousand reads and writes a month, about $0.01 even
  with no free tier (reserved capacity would cost ~$0.57/month outside it).
- EventBridge scheduled rules are free. Logs are kept one week.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

SRC = Path(__file__).resolve().parent.parent / "src"


class DealAlertStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        ntfy_topic: str,
        ntfy_server: str = "https://ntfy.sh",
        bestbuy_api_key: str | None = None,
        interval_minutes: int = 30,
        summary_hour_utc: int = 13,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Only dedupe markers and last-seen prices live here; nothing worth keeping.
        table = dynamodb.Table(
            self,
            "State",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires",
            removal_policy=RemovalPolicy.DESTROY,
        )

        environment = {"TABLE_NAME": table.table_name, "NTFY_TOPIC": ntfy_topic, "NTFY_SERVER": ntfy_server}
        if bestbuy_api_key:
            environment["BESTBUY_API_KEY"] = bestbuy_api_key

        fn = lambda_.Function(
            self,
            "Checker",
            description="Checks laptop prices and pushes deals to ntfy",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="dealalert.handler.handler",
            # Standard library + the runtime's boto3 only, so the source dir is the bundle.
            code=lambda_.Code.from_asset(str(SRC), exclude=["**/__pycache__", "*.egg-info"]),
            memory_size=128,
            timeout=Duration.seconds(90),
            environment=environment,
            # An explicit log group rather than the deprecated `log_retention` prop.
            log_group=logs.LogGroup(
                self, "CheckerLogs", retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY
            ),
        )
        table.grant_read_write_data(fn)

        events.Rule(
            self,
            "Schedule",
            description=f"Run the laptop price check every {interval_minutes} minutes",
            schedule=events.Schedule.rate(Duration.minutes(interval_minutes)),
            # No retries: the next scheduled run is never far away.
            targets=[targets.LambdaFunction(fn, retry_attempts=0)],
        )

        # Once a day, deals or not: a low-priority summary, urgent if checks have stopped.
        events.Rule(
            self,
            "DailySummary",
            description=f"Daily deal summary push at {summary_hour_utc:02d}:00 UTC",
            schedule=events.Schedule.cron(minute="0", hour=str(summary_hour_utc)),
            targets=[targets.LambdaFunction(
                fn, event=events.RuleTargetInput.from_object({"task": "daily-summary"}), retry_attempts=2
            )],
        )
