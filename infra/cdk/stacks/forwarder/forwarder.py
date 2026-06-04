"""DynamoDB Stream → SNS forwarder. One SNS message per INSERT."""
import json
import os
from decimal import Decimal
from typing import Any

import boto3

_sns = boto3.client("sns")
_TOPIC = os.environ["TOPIC_ARN"]


def _decode(av: dict) -> Any:
    if "NULL" in av:
        return None
    if "S" in av:
        return av["S"]
    if "BOOL" in av:
        return av["BOOL"]
    if "N" in av:
        n = av["N"]
        return float(n) if "." in n else int(n)
    if "L" in av:
        return [_decode(x) for x in av["L"]]
    if "M" in av:
        return {k: _decode(v) for k, v in av["M"].items()}
    return None


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    return value


def handler(event: dict, _ctx: Any) -> dict:
    published = 0
    for record in event.get("Records", []):
        if record.get("eventName") != "INSERT":
            continue
        image = record["dynamodb"].get("NewImage") or {}
        item = {k: _decode(v) for k, v in image.items()}
        _sns.publish(
            TopicArn=_TOPIC,
            Message=json.dumps(_to_json_safe(item)),
            MessageAttributes={
                "kind": {
                    "DataType": "String",
                    "StringValue": str(item.get("kind", "unknown")),
                },
                "investor_id": {
                    "DataType": "String",
                    "StringValue": str(item.get("investor_id", "unknown")),
                },
            },
        )
        published += 1
    return {"published": published}
