"""AsyncAPI 3.0 conformance harness.

Loads each AsyncAPI document under contracts/asyncapi/ and asserts message-shape
conformance against producer/consumer fixtures. The harness uses the JSON Schema
embedded in each `payload` definition to validate concrete message instances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts" / "asyncapi"


def load_message_schema(channel: str, message_name: str) -> dict[str, Any]:
    """Resolve the JSON Schema for a given (channel, message) pair from AsyncAPI 3.0."""
    candidates = list(CONTRACTS_DIR.glob("*.yaml"))
    for path in candidates:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        channels = doc.get("channels", {})
        if channel not in channels:
            continue
        components = doc.get("components", {})
        messages = components.get("messages", {})
        if message_name not in messages:
            continue
        payload_ref = messages[message_name]["payload"]["$ref"]
        schema_name = payload_ref.split("/")[-1]
        return components.get("schemas", {}).get(schema_name, {})
    raise KeyError(f"AsyncAPI message not found: channel={channel} message={message_name}")


def validate_message(channel: str, message_name: str, instance: dict[str, Any]) -> None:
    """Validate a concrete instance against the AsyncAPI payload schema."""
    schema = load_message_schema(channel, message_name)
    jsonschema.validate(instance=instance, schema=schema)
