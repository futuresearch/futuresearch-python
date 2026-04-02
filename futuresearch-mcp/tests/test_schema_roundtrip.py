import json

from futuresearch.generated.models.agent_map_operation_response_schema_type_0 import (
    AgentMapOperationResponseSchemaType0,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EBAY_DEALS_SCHEMA = {
    "type": "object",
    "properties": {
        "deals": {
            "type": "array",
            "description": "List of eBay deals found where per-item cost is below avg_90d",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Full eBay listing title",
                    },
                    "per_item_cost": {
                        "type": "number",
                        "description": "Price per item",
                    },
                    "shipping_cost": {"type": "string", "description": "Shipping cost"},
                    "margin": {
                        "type": "number",
                        "description": "avg_90d minus per_item_cost",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full URL to the eBay listing",
                    },
                },
                "required": [
                    "title",
                    "per_item_cost",
                    "shipping_cost",
                    "margin",
                    "url",
                ],
            },
        },
        "no_deals_reason": {
            "type": "string",
            "description": "If no deals found, explain why",
        },
    },
    "required": ["deals"],
}


def _roundtrip_via_sdk(schema: dict) -> dict:
    """Simulate the SDK path: schema → generated model → dict."""
    sdk_obj = AgentMapOperationResponseSchemaType0.from_dict(schema)
    return sdk_obj.to_dict()


class TestSchemaPassthrough:
    """The SDK should pass the schema dict through without modification."""

    def test_ebay_deals_schema_preserved(self):
        """The exact schema from the failing eBay CPAP session."""
        result = _roundtrip_via_sdk(EBAY_DEALS_SCHEMA)
        deals = result["properties"]["deals"]
        assert deals["type"] == "array"
        assert deals["items"]["type"] == "object"
        assert "title" in deals["items"]["properties"]
        assert "url" in deals["items"]["properties"]
        assert deals["items"]["required"] == [
            "title",
            "per_item_cost",
            "shipping_cost",
            "margin",
            "url",
        ]

    def test_array_of_objects_items_preserved(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": "number"},
                        },
                        "required": ["name"],
                    },
                }
            },
            "required": ["items"],
        }
        result = _roundtrip_via_sdk(schema)
        assert (
            result["properties"]["items"]["items"]["properties"]["name"]["type"]
            == "string"
        )
        assert result["properties"]["items"]["items"]["required"] == ["name"]

    def test_array_of_primitives_preserved(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tags"],
        }
        result = _roundtrip_via_sdk(schema)
        assert result["properties"]["tags"]["items"]["type"] == "string"

    def test_nested_object_properties_preserved(self):
        schema = {
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                }
            },
            "required": ["metadata"],
        }
        result = _roundtrip_via_sdk(schema)
        assert (
            result["properties"]["metadata"]["properties"]["source"]["type"] == "string"
        )

    def test_schema_is_json_serializable(self):
        """The schema must be JSON-serializable for the HTTP request."""
        result = _roundtrip_via_sdk(EBAY_DEALS_SCHEMA)
        json.dumps(result)  # should not raise
