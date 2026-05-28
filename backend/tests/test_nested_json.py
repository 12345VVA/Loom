import json
from app.modules.workflow.service.compiler import render_template
from app.modules.workflow.service.workflow_service import (
    _build_json_schema_from_fields,
    _render_output_field_recursive
)


def test_build_json_schema_nested():
    # 1. Test flat schema
    fields = [
        {"name": "title", "type": "string", "description": "The title"}
    ]
    schema = _build_json_schema_from_fields(fields)
    assert schema["json_schema"]["schema"]["properties"]["title"] == {
        "type": "string",
        "description": "The title"
    }

    # 2. Test object schema
    fields = [
        {
            "name": "user",
            "type": "object",
            "description": "User info",
            "children": [
                {"name": "name", "type": "string", "description": "User name"},
                {"name": "age", "type": "number"}
            ]
        }
    ]
    schema = _build_json_schema_from_fields(fields)
    user_schema = schema["json_schema"]["schema"]["properties"]["user"]
    assert user_schema["type"] == "object"
    assert user_schema["properties"]["name"] == {"type": "string", "description": "User name"}
    assert user_schema["properties"]["age"] == {"type": "number"}
    assert user_schema["required"] == ["name", "age"]

    # 3. Test array schema (legacy compatibility)
    fields = [
        {
            "name": "tags",
            "type": "array",
            "description": "List of tags",
            "children": [
                {"name": "[Item]", "type": "string", "description": "Tag item"}
            ]
        }
    ]
    schema = _build_json_schema_from_fields(fields)
    tags_schema = schema["json_schema"]["schema"]["properties"]["tags"]
    assert tags_schema["type"] == "array"
    assert tags_schema["items"] == {"type": "string", "description": "Tag item"}

    # 4. Test Array<Object> (array_object)
    fields = [
        {
            "name": "stories",
            "type": "array_object",
            "description": "List of stories",
            "children": [
                {"name": "story_id", "type": "number"},
                {"name": "title", "type": "string"}
            ]
        }
    ]
    schema = _build_json_schema_from_fields(fields)
    stories_schema = schema["json_schema"]["schema"]["properties"]["stories"]
    assert stories_schema["type"] == "array"
    assert stories_schema["items"]["type"] == "object"
    assert stories_schema["items"]["properties"]["story_id"] == {"type": "number"}
    assert stories_schema["items"]["properties"]["title"] == {"type": "string"}
    assert stories_schema["items"]["required"] == ["story_id", "title"]

    # 5. Test Array<String> (array_string)
    fields = [
        {
            "name": "keywords",
            "type": "array_string",
            "description": "List of keywords"
        }
    ]
    schema = _build_json_schema_from_fields(fields)
    keywords_schema = schema["json_schema"]["schema"]["properties"]["keywords"]
    assert keywords_schema["type"] == "array"
    assert keywords_schema["items"] == {"type": "string"}


def test_render_template_list_index():
    variables = {
        "llm_node": {
            "scores": [95, 80, 75],
            "nested": [
                {"name": "Alice"},
                {"name": "Bob"}
            ]
        }
    }
    # Test index access
    assert render_template("Score is {llm_node.scores.0}", variables) == "Score is 95"
    assert render_template("Score is {llm_node.scores.1}", variables) == "Score is 80"
    assert render_template("Name is {llm_node.nested.0.name}", variables) == "Name is Alice"
    
    # Test fallback to empty string
    assert render_template("Score is {llm_node.scores.5}", variables) == "Score is "
    assert render_template("Score is {llm_node.scores.abc}", variables) == "Score is "


def test_render_output_field_recursive():
    variables = {
        "start": {"input_name": "Alice"},
        "llm_node": {
            "score": 98,
            "items": ["art", "science"]
        }
    }
    
    # End node style nested fields definition
    fields = [
        {
            "name": "result",
            "type": "object",
            "children": [
                {"name": "userName", "type": "string", "value": "{start.input_name}"},
                {
                    "name": "scores",
                    "type": "array",
                    "children": [
                        {"name": "[0]", "type": "number", "value": "{llm_node.score}"},
                        {"name": "[1]", "type": "string", "value": "{llm_node.items}"}
                    ]
                }
            ]
        }
    ]
    
    result = {}
    for f in fields:
        result[f["name"]] = _render_output_field_recursive(f, variables)
        
    assert result == {
        "result": {
            "userName": "Alice",
            "scores": [
                98,
                ["art", "science"]
            ]
        }
    }
