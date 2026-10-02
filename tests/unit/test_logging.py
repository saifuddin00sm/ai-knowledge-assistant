"""The JSON formatter and the `extra` collision guard."""

from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, log_fields, request_id_var


def format_record(**fields: object) -> dict[str, object]:
    logger = logging.getLogger("test.logging")
    record = logger.makeRecord(
        logger.name, logging.INFO, "f.py", 1, "event_name", None, None, extra=fields
    )
    parsed: dict[str, object] = json.loads(JsonFormatter().format(record))
    return parsed


def test_domain_fields_are_merged_into_the_json_payload() -> None:
    payload = format_record(document_id="abc", chunks=3)
    assert payload["message"] == "event_name"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logging"
    assert payload["document_id"] == "abc"
    assert payload["chunks"] == 3


def test_record_internals_are_not_leaked() -> None:
    payload = format_record(document_id="abc")
    assert "args" not in payload
    assert "levelno" not in payload
    assert "msg" not in payload


def test_request_id_is_attached_when_set() -> None:
    token = request_id_var.set("req-123")
    try:
        assert format_record()["request_id"] == "req-123"
    finally:
        request_id_var.reset(token)


def test_log_fields_renames_keys_that_shadow_logrecord() -> None:
    # `logging` raises KeyError for these, which would turn a log line into a 500.
    fields = log_fields(filename="handbook.md", module="ingest", document_id="abc")
    assert fields == {
        "ctx_filename": "handbook.md",
        "ctx_module": "ingest",
        "document_id": "abc",
    }


def test_logging_with_a_shadowing_key_succeeds_through_the_guard() -> None:
    payload = format_record(**log_fields(filename="handbook.md"))
    assert payload["ctx_filename"] == "handbook.md"


def test_logging_with_a_raw_shadowing_key_would_raise() -> None:
    import pytest

    with pytest.raises(KeyError, match="filename"):
        format_record(filename="handbook.md")
