"""EPS dts.responses $ref 解引用测试"""

from app.modules.base.service.eps_service import _fix_dts_types, _inline_response_refs

OPENAPI = {
    "components": {
        "schemas": {
            "UserRead": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
            "MenuTree": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/MenuTree"},
                    },
                },
            },
        }
    }
}


def _response_schema(responses: dict) -> dict:
    return responses["200"]["content"]["application/json"]["schema"]


def test_ref_resolved_inline():
    responses = {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserRead"}}}}}
    data = _fix_dts_types(_inline_response_refs(OPENAPI, responses))
    schema = _response_schema(data)
    assert schema["type"] == "object"
    # integer 已归一为 number
    assert schema["properties"]["id"]["type"] == "number"
    assert schema["properties"]["name"]["type"] == "string"
    # 原 components 不被改写
    assert OPENAPI["components"]["schemas"]["UserRead"]["properties"]["id"]["type"] == "integer"


def test_circular_ref_breaks_to_object():
    responses = {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/MenuTree"}}}}}
    data = _inline_response_refs(OPENAPI, responses)
    items = _response_schema(data)["properties"]["children"]["items"]
    assert items == {"type": "object"}


def test_anyof_union_passthrough():
    """menu add 的 MenuRead | list[MenuRead] → anyOf 两支均需解引用"""
    responses = {
        "200": {
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/UserRead"},
                            {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/UserRead"},
                            },
                        ]
                    }
                }
            }
        }
    }
    data = _inline_response_refs(OPENAPI, responses)
    schema = _response_schema(data)
    assert schema["anyOf"][0]["type"] == "object"
    assert schema["anyOf"][1]["items"]["type"] == "object"


def test_dangling_ref_degrades_to_object():
    responses = {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NotFound"}}}}}
    data = _inline_response_refs(OPENAPI, responses)
    assert _response_schema(data) == {"type": "object"}


def test_scalar_passthrough():
    responses = {"200": {"schema": {"type": "integer"}}}
    assert _inline_response_refs(OPENAPI, responses) == {"200": {"schema": {"type": "integer"}}}


def test_empty_components():
    assert _inline_response_refs({}, {"200": {"schema": {"$ref": "#/components/schemas/X"}}}) == {
        "200": {"schema": {"type": "object"}}
    }
