import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infrastructure.stack import DealAlertStack


def synth(**kwargs) -> Template:
    app = cdk.App()
    stack = DealAlertStack(app, "Test", ntfy_topic="test-topic", **kwargs)
    return Template.from_stack(stack)


def test_minimal_footprint():
    t = synth()
    t.resource_count_is("AWS::Lambda::Function", 1)
    t.resource_count_is("AWS::DynamoDB::Table", 1)
    t.resource_count_is("AWS::Events::Rule", 2)  # price check + daily summary
    # Nothing that bills by the hour.
    for kind in ("AWS::EC2::NatGateway", "AWS::EC2::VPC", "AWS::SQS::Queue", "AWS::SNS::Topic", "AWS::ApiGateway::RestApi"):
        t.resource_count_is(kind, 0)


def test_table_is_on_demand_with_ttl():
    synth().has_resource_properties("AWS::DynamoDB::Table", {
        "BillingMode": "PAY_PER_REQUEST",
        "TimeToLiveSpecification": {"AttributeName": "expires", "Enabled": True},
    })


def test_function_config():
    t = synth()
    t.has_resource_properties("AWS::Lambda::Function", {
        "Runtime": "python3.12",
        "Architectures": ["arm64"],
        "MemorySize": 128,
        "Handler": "dealalert.handler.handler",
        "Environment": {"Variables": Match.object_like({"NTFY_TOPIC": "test-topic"})},
    })
    # No reserved concurrency: new accounts can't spare it (see the jobs repo's BLK-014).
    fn = next(iter(t.find_resources("AWS::Lambda::Function").values()))
    assert "ReservedConcurrentExecutions" not in fn["Properties"]
    t.has_resource_properties("AWS::Logs::LogGroup", {"RetentionInDays": 7})


def test_bestbuy_key_only_when_given():
    without = synth()
    fn = next(iter(without.find_resources("AWS::Lambda::Function").values()))
    assert "BESTBUY_API_KEY" not in fn["Properties"]["Environment"]["Variables"]
    synth(bestbuy_api_key="k").has_resource_properties("AWS::Lambda::Function", {
        "Environment": {"Variables": Match.object_like({"BESTBUY_API_KEY": "k"})},
    })


def test_schedules():
    t = synth(interval_minutes=60, summary_hour_utc=12)
    t.has_resource_properties("AWS::Events::Rule", {"ScheduleExpression": "rate(1 hour)"})
    t.has_resource_properties("AWS::Events::Rule", {
        "ScheduleExpression": "cron(0 12 * * ? *)",
        "Targets": [Match.object_like({"Input": '{"task":"daily-summary"}'})],
    })
