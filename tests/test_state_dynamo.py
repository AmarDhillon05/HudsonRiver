"""DynamoState against moto's DynamoDB, mainly the float/Decimal and nested-dict handling."""

import boto3
import pytest

moto = pytest.importorskip("moto")

from dealalert.state import DynamoState


@pytest.fixture
def state(monkeypatch):
    for k, v in {"AWS_DEFAULT_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    with moto.mock_aws():
        db = boto3.resource("dynamodb")
        db.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoState("t", db)


def test_seen(state):
    assert not state.seen("https://sd/1")
    state.mark_seen("https://sd/1")
    assert state.seen("https://sd/1")


def test_records_round_trip(state):
    assert state.get("health") is None
    record = {"low": 1599.99, "alerted": 1500, "sources": {"slickdeals": {"failing_since": "2026-10-25T20:00:00+00:00", "alerted": True}}}
    state.put("health", record)
    got = state.get("health")
    assert got == record
    assert isinstance(got["low"], float) and isinstance(got["alerted"], int)
