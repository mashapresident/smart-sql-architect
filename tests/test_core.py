"""
tests/test_core.py — Юніт-тести для Smart SQL Architect.

Запуск:  pytest -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sql_architect.core import (
    SQLArchitect,
    _cache_key,
    _schema_to_text,
    _strip_markdown_fences,
)
from sql_architect.schemas import (
    DatabaseSchema,
    SQLColumn,
    SQLQueryResult,
    SQLTable,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def simple_schema() -> DatabaseSchema:
    return DatabaseSchema(
        database_name="test_db",
        dialect="PostgreSQL",
        tables=[
            SQLTable(
                name="users",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="name", data_type="VARCHAR(100)", nullable=False),
                    SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
                ],
            ),
            SQLTable(
                name="orders",
                columns=[
                    SQLColumn(name="id", data_type="SERIAL", primary_key=True, nullable=False),
                    SQLColumn(name="user_id", data_type="INTEGER", nullable=False, foreign_key="users.id"),
                    SQLColumn(name="total", data_type="DECIMAL(10,2)", nullable=False),
                    SQLColumn(name="created_at", data_type="TIMESTAMP", nullable=False),
                ],
            ),
        ],
    )


VALID_RESULT_DICT = {
    "sql_query": "SELECT id, name FROM users LIMIT 10;",
    "explanation": "Повертає перших 10 користувачів.",
    "tables_used": ["users"],
    "estimated_complexity": "simple",
    "warnings": [],
    "alternative_approaches": None,
}


# ──────────────────────────────────────────────────────────────────────────────
# _schema_to_text
# ──────────────────────────────────────────────────────────────────────────────


def test_schema_to_text_contains_database_name(simple_schema):
    text = _schema_to_text(simple_schema)
    assert "test_db" in text
    assert "PostgreSQL" in text


def test_schema_to_text_contains_all_tables(simple_schema):
    text = _schema_to_text(simple_schema)
    assert "users" in text
    assert "orders" in text


def test_schema_to_text_marks_primary_key(simple_schema):
    text = _schema_to_text(simple_schema)
    assert "PK" in text


def test_schema_to_text_marks_foreign_key(simple_schema):
    text = _schema_to_text(simple_schema)
    assert "FK→users.id" in text


def test_schema_to_text_marks_not_null(simple_schema):
    text = _schema_to_text(simple_schema)
    assert "NOT NULL" in text


# ──────────────────────────────────────────────────────────────────────────────
# _cache_key
# ──────────────────────────────────────────────────────────────────────────────


def test_cache_key_deterministic():
    k1 = _cache_key("show top users", "abc123")
    k2 = _cache_key("show top users", "abc123")
    assert k1 == k2


def test_cache_key_differs_by_question():
    k1 = _cache_key("show top users", "abc123")
    k2 = _cache_key("show all products", "abc123")
    assert k1 != k2


def test_cache_key_differs_by_schema_hash():
    k1 = _cache_key("show top users", "abc123")
    k2 = _cache_key("show top users", "xyz999")
    assert k1 != k2


def test_cache_key_case_insensitive():
    k1 = _cache_key("Show Top Users", "abc123")
    k2 = _cache_key("show top users", "abc123")
    assert k1 == k2


def test_cache_key_strips_whitespace():
    k1 = _cache_key("  show top users  ", "abc123")
    k2 = _cache_key("show top users", "abc123")
    assert k1 == k2


# ──────────────────────────────────────────────────────────────────────────────
# _strip_markdown_fences
# ──────────────────────────────────────────────────────────────────────────────


def test_strip_fences_plain_json():
    raw = '{"key": "value"}'
    assert _strip_markdown_fences(raw) == raw


def test_strip_fences_removes_json_fence():
    raw = "```json\n{\"key\": \"value\"}\n```"
    result = _strip_markdown_fences(raw)
    assert result == '{"key": "value"}'


def test_strip_fences_removes_plain_fence():
    raw = "```\n{\"key\": \"value\"}\n```"
    result = _strip_markdown_fences(raw)
    assert result == '{"key": "value"}'


# ──────────────────────────────────────────────────────────────────────────────
# SQLArchitect._parse_response
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_response_valid_json():
    raw = json.dumps(VALID_RESULT_DICT)
    result = SQLArchitect._parse_response(raw)
    assert isinstance(result, SQLQueryResult)
    assert result.estimated_complexity == "simple"
    assert result.tables_used == ["users"]


def test_parse_response_with_markdown_fence():
    raw = "```json\n" + json.dumps(VALID_RESULT_DICT) + "\n```"
    result = SQLArchitect._parse_response(raw)
    assert result.sql_query == VALID_RESULT_DICT["sql_query"]


def test_parse_response_invalid_json_raises():
    with pytest.raises(ValueError, match="не-JSON"):
        SQLArchitect._parse_response("Це не JSON взагалі.")


def test_parse_response_wrong_schema_raises():
    bad = {"unexpected_field": "hello"}
    with pytest.raises(ValueError):
        SQLArchitect._parse_response(json.dumps(bad))


def test_parse_response_with_warnings():
    data = {**VALID_RESULT_DICT, "warnings": ["Попередження 1", "Попередження 2"]}
    result = SQLArchitect._parse_response(json.dumps(data))
    assert len(result.warnings) == 2


def test_parse_response_with_alternatives():
    data = {**VALID_RESULT_DICT, "alternative_approaches": ["Варіант A", "Варіант B"]}
    result = SQLArchitect._parse_response(json.dumps(data))
    assert result.alternative_approaches is not None
    assert len(result.alternative_approaches) == 2


# ──────────────────────────────────────────────────────────────────────────────
# SQLArchitect integration (mocked Gemini)
# ──────────────────────────────────────────────────────────────────────────────


@patch("sql_architect.core.genai.GenerativeModel")
@patch("sql_architect.core.genai.configure")
def test_generate_sql_returns_result(mock_configure, mock_model_cls, simple_schema):
    """generate_sql() повинен повертати SQLQueryResult при успішній відповіді."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(VALID_RESULT_DICT)

    mock_chat = MagicMock()
    mock_chat.send_message.return_value = mock_response

    mock_model_instance = MagicMock()
    mock_model_instance.start_chat.return_value = mock_chat
    mock_model_cls.return_value = mock_model_instance

    architect = SQLArchitect(api_key="fake-key", use_cache=False)
    result = architect.generate_sql("Покажи перших 10 користувачів", simple_schema)

    assert isinstance(result, SQLQueryResult)
    assert result.tables_used == ["users"]
    mock_configure.assert_called_once_with(api_key="fake-key")


@patch("sql_architect.core.genai.GenerativeModel")
@patch("sql_architect.core.genai.configure")
def test_generate_sql_propagates_resource_exhausted(
    mock_configure, mock_model_cls, simple_schema
):
    """generate_sql() повинен прокидати ResourceExhausted з коротким повідомленням."""
    from google.api_core.exceptions import ResourceExhausted as RE

    mock_model_instance = MagicMock()
    mock_chat = MagicMock()
    mock_chat.send_message.side_effect = RE("quota exceeded")
    mock_model_instance.start_chat.return_value = mock_chat
    mock_model_cls.return_value = mock_model_instance

    architect = SQLArchitect(api_key="fake-key", use_cache=False)
    with pytest.raises(RE, match="Free Tier"):
        architect.generate_sql("будь-який запит", simple_schema)


@patch("sql_architect.core.genai.GenerativeModel")
@patch("sql_architect.core.genai.configure")
def test_generate_sql_propagates_invalid_argument(
    mock_configure, mock_model_cls, simple_schema
):
    """generate_sql() повинен прокидати InvalidArgument з коротким повідомленням."""
    from google.api_core.exceptions import InvalidArgument as IA

    mock_model_instance = MagicMock()
    mock_chat = MagicMock()
    mock_chat.send_message.side_effect = IA("bad key")
    mock_model_instance.start_chat.return_value = mock_chat
    mock_model_cls.return_value = mock_model_instance

    architect = SQLArchitect(api_key="bad-key", use_cache=False)
    with pytest.raises(IA, match="Невірний"):
        architect.generate_sql("будь-який запит", simple_schema)
