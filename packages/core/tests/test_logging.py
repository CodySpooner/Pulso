import json
import logging

from pulso_core.logging import JsonFormatter


def test_formatter_emits_named_extras_and_drops_the_rest() -> None:
    record = logging.makeLogRecord(
        {"name": "pulso.fixture", "msg": "fixture", "projected_points": 1, "body": "fixture-secret"}
    )
    line = JsonFormatter().format(record)
    assert json.loads(line)["projected_points"] == 1
    assert "body" not in json.loads(line) and "fixture-secret" not in line
