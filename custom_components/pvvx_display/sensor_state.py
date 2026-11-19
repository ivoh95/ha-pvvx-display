"""Helpers for reading numeric Home Assistant sensor states."""

from __future__ import annotations

import math


def parse_sensor_state(entity_id: str, state: str | None) -> float:
    """Return a finite numeric sensor state or raise a useful validation error."""
    if state is None or state in {"unknown", "unavailable"}:
        raise ValueError(f"Sensor {entity_id} has no available state")

    try:
        value = float(state)
    except ValueError as err:
        raise ValueError(f"Sensor {entity_id} does not have a numeric state") from err

    if not math.isfinite(value):
        raise ValueError(f"Sensor {entity_id} does not have a finite numeric state")
    return value
