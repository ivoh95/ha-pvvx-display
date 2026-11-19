# PVVX MiThermometer Display

Home Assistant integration that pushes sensor values to a PVVX/ATC MiThermometer's LCD over Bluetooth. No ESPHome bridge required.

It only writes to the display. Use BTHome, Xiaomi BLE or similar to read the thermometer's own measurements.

## Requirements

- A display thermometer (e.g. LYWSD03MMC, MHO-C401) on [ATC_MiThermometer](https://github.com/pvvx/ATC_MiThermometer) firmware, with **Show ext.data** enabled in the configurator.
- Firmware **v4.4+** for the "only external data" mode (otherwise the LCD alternates its own readings every 2.5 s).
- Home Assistant Bluetooth with an adapter or proxy that allows connections.
- The thermometer's Bluetooth address.

## Install

HACS → custom repository, or copy `custom_components/pvvx_display` into your `custom_components` folder. Restart HA, then add **PVVX MiThermometer Display** and enter the Bluetooth address.

## Configure

Open **Configure** on the device:

- **Big / Small number sensor** — any `sensor` entity to show (e.g. temperature, humidity). A sensor overrides its fallback number.
- **Show only Home Assistant data** (default on) — show only the pushed values, until the device reboots. Needs firmware v4.4+.
- **Automatically update the display** (default on) — push on sensor change + a periodic refresh. No automation needed.
- **Keep the Bluetooth connection open** (default off) — reuse one connection for every update instead of reconnecting. Use it for frequent updates or if other Bluetooth integrations are affected; it occupies one connection slot and keeps the thermometer's radio active.
- **Minimum seconds between updates** (default 60) — throttle; rapid changes are coalesced, latest value wins.
- **Unit**, smiley, percent, battery, brackets — LCD indicators.
- **Validity / refresh period** — used only when "Show only Home Assistant data" is off: seconds before the LCD reverts to its own readings.

Value ranges: big `-99.5…1999.5` (0.1 steps), small `-9…99` (whole number; decimals are rounded). Sensor readings outside these are clamped, e.g. 100 % humidity shows as 99.

## Action

`pvvx_display.show` sends the configured values on demand; any field provided overrides the saved config for that call.

```yaml
action: pvvx_display.show
target:
  device_id: YOUR_DEVICE_ID
data:
  big_number_entity: sensor.room_temperature
  small_number_entity: sensor.room_humidity
  unit: celsius
  percent: true
```

## Notes

- Without keep-alive, each update is a short BLE connection. In permanent mode the integration connects only on sensor change (throttled) plus an hourly refresh.
- Unavailable or non-numeric source sensors are skipped (automatic updates) or raise an error (action).
- Thermometers with a Bluetooth bind key / PIN are not supported.
- The frame format matches ESPHome's `pvvx_mithermometer` display component.

Report issues on [GitHub](https://github.com/ivoh95/ha-pvvx-display/issues).

## License

[MIT](LICENSE)
