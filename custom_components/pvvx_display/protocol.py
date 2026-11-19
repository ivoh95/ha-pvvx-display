"""PVVX external display command encoding."""

from __future__ import annotations

import math
import struct

from .const import UNIT_VALUES

COMMAND_DISPLAY = 0x22

# Ranges the LCD fields can actually display.
BIG_MIN, BIG_MAX = -99.5, 1999.5
SMALL_MIN, SMALL_MAX = -9, 99


def encode_display_frame(
    big_number: float,
    small_number: float,
    validity_period: int = 300,
    unit: str = "none",
    happy: bool = False,
    sad: bool = False,
    bracket: bool = False,
    percent: bool = False,
    battery: bool = False,
) -> bytes:
    """Encode the eight-byte external display command.

    Values are clamped to the LCD ranges, so an out-of-range reading (e.g. 100 %
    humidity) still updates the display.
    """
    if not math.isfinite(big_number):
        raise ValueError("big_number must be a finite number")
    if not math.isfinite(small_number):
        raise ValueError("small_number must be a finite number")

    if not 1 <= validity_period <= 65535:
        raise ValueError("validity_period must be between 1 and 65535 seconds")
    if unit not in UNIT_VALUES:
        raise ValueError(f"Unsupported unit: {unit}")

    flags = (
        int(happy)
        | (int(sad) << 1)
        | (int(bracket) << 2)
        | (int(percent) << 3)
        | (int(battery) << 4)
        | (UNIT_VALUES[unit] << 5)
    )

    # ESPHome stores the large value in tenths and truncates toward zero.
    scaled_big_number = int(min(max(big_number, BIG_MIN), BIG_MAX) * 10)
    # The small field has no decimal digit, so round to the nearest integer
    # (48.3 % -> 48) and clamp to what it can show (100 % -> 99).
    small_value = min(max(round(small_number), SMALL_MIN), SMALL_MAX)
    return struct.pack(
        "<BhhHB",
        COMMAND_DISPLAY,
        scaled_big_number,
        small_value,
        validity_period,
        flags,
    )
