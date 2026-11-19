"""Tests for PVVX sensor values and display frame encoding."""

import sys
import unittest
from importlib import import_module
from pathlib import Path
from types import ModuleType

# Load the pure protocol module without importing the HA-dependent integration setup.
component_path = Path(__file__).parents[1] / "custom_components" / "pvvx_display"
package_name = "custom_components.pvvx_display"
package = ModuleType(package_name)
package.__path__ = [str(component_path)]
sys.modules[package_name] = package

encode_display_frame = import_module(
    "custom_components.pvvx_display.protocol"
).encode_display_frame
parse_sensor_state = import_module(
    "custom_components.pvvx_display.sensor_state"
).parse_sensor_state


class TestDisplayFrame(unittest.TestCase):
    """Check the external display command payload."""

    def test_encodes_values_and_flags(self) -> None:
        frame = encode_display_frame(
            23.1,
            45,
            validity_period=300,
            unit="celsius",
            happy=True,
            percent=True,
        )

        self.assertEqual(frame, bytes.fromhex("22 e7 00 2d 00 2c 01 a9"))

    def test_encodes_negative_values_as_signed_little_endian(self) -> None:
        frame = encode_display_frame(-12.3, -4)

        self.assertEqual(frame, bytes.fromhex("22 85 ff fc ff 2c 01 00"))

    def test_truncates_toward_zero_like_esphome_cast(self) -> None:
        # ESPHome uses static_cast<int16_t>(value * 10), which truncates toward
        # zero; Python int() must match for both small positive and negative values.
        self.assertEqual(encode_display_frame(-0.07, 0)[1:3], bytes.fromhex("00 00"))
        self.assertEqual(encode_display_frame(0.07, 0)[1:3], bytes.fromhex("00 00"))

    def test_encodes_display_extremes(self) -> None:
        frame = encode_display_frame(1999.5, 99, unit="fahrenheit", battery=True)

        self.assertEqual(frame, bytes.fromhex("22 1b 4e 63 00 2c 01 70"))

    def test_unit_occupies_top_three_flag_bits(self) -> None:
        frame = encode_display_frame(0, 0, unit="degree_e")

        self.assertEqual(frame[-1], 7 << 5)

    def test_encodes_permanent_validity_sentinel(self) -> None:
        # 65535 is the "show only external data permanently" value (firmware v4.4+).
        frame = encode_display_frame(0, 0, validity_period=65535)

        self.assertEqual(frame[5:7], bytes.fromhex("ff ff"))

    def test_rounds_non_integer_small_number(self) -> None:
        # The small field has no decimal digit, so a float humidity is rounded.
        self.assertEqual(encode_display_frame(10, 48.3)[3:5], bytes.fromhex("30 00"))
        self.assertEqual(encode_display_frame(10, 48.7)[3:5], bytes.fromhex("31 00"))

    def test_clamps_big_number_to_display_range(self) -> None:
        # 2000 clamps to 1999.5 -> 19995 tenths (0x4e1b), -200 clamps to -99.5
        # -> -995 tenths (0xfc1d).
        self.assertEqual(encode_display_frame(2000, 10)[1:3], bytes.fromhex("1b 4e"))
        self.assertEqual(encode_display_frame(-200, 10)[1:3], bytes.fromhex("1d fc"))

    def test_clamps_small_number_to_display_range(self) -> None:
        # 100 % humidity shows as 99 rather than failing the whole update.
        self.assertEqual(encode_display_frame(21.0, 100)[3:5], bytes.fromhex("63 00"))
        self.assertEqual(encode_display_frame(21.0, -20)[3:5], bytes.fromhex("f7 ff"))

    def test_rejects_non_finite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "big_number"):
            encode_display_frame(float("inf"), 10)
        with self.assertRaisesRegex(ValueError, "small_number"):
            encode_display_frame(10, float("nan"))

    def test_rejects_validity_period_outside_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "validity_period"):
            encode_display_frame(0, 0, validity_period=0)


class TestSensorState(unittest.TestCase):
    """Check numeric sensor state validation."""

    def test_parses_finite_numeric_state(self) -> None:
        self.assertEqual(parse_sensor_state("sensor.room_temperature", "21.7"), 21.7)

    def test_rejects_unavailable_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "no available state"):
            parse_sensor_state("sensor.room_temperature", "unavailable")

    def test_rejects_non_numeric_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "not have a numeric state"):
            parse_sensor_state("sensor.room_temperature", "warming")

    def test_rejects_infinite_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite numeric state"):
            parse_sensor_state("sensor.room_temperature", "inf")


if __name__ == "__main__":
    unittest.main()
