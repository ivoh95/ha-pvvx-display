"""Home Assistant integration for PVVX MiThermometer displays."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from bleak import BleakClient, BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    clear_cache,
    close_stale_connections_by_address,
    establish_connection,
)
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr, selector
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started

from .const import (
    CHARACTERISTIC_UUID,
    CONF_AUTO_UPDATE,
    CONF_BATTERY,
    CONF_BIG_NUMBER,
    CONF_BIG_NUMBER_ENTITY,
    CONF_BRACKET,
    CONF_HAPPY,
    CONF_KEEP_ALIVE,
    CONF_MIN_UPDATE_INTERVAL,
    CONF_PERCENT,
    CONF_PERMANENT,
    CONF_SAD,
    CONF_SMALL_NUMBER,
    CONF_SMALL_NUMBER_ENTITY,
    CONF_UNIT,
    CONF_VALIDITY_PERIOD,
    DEFAULT_MIN_UPDATE_INTERVAL,
    DEFAULT_VALIDITY_PERIOD,
    DISCONNECT_DELAY_SECONDS,
    DISCONNECT_TIMEOUT_SECONDS,
    DOMAIN,
    MIN_REFRESH_SECONDS,
    PERMANENT_KEEPALIVE_SECONDS,
    PERMANENT_VALIDITY_PERIOD,
    REFRESH_MARGIN_SECONDS,
    SERVICE_SHOW,
    UNIT_VALUES,
    WRITE_TIMEOUT_SECONDS,
)
from .protocol import encode_display_frame
from .sensor_state import parse_sensor_state

try:
    # Home Assistant 2026.9+; optional so older cores still load.
    from homeassistant.components.bluetooth import BluetoothReachabilityIntent
except ImportError:  # pragma: no cover
    BluetoothReachabilityIntent = None

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type PvvxConfigEntry = ConfigEntry["PvvxRuntimeData"]


@dataclass
class PvvxRuntimeData:
    """Runtime state for a configured thermometer."""

    address: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Open connection reused between writes in keep-alive mode (None otherwise).
    client: BleakClient | None = None

    def handle_disconnect(self, client: BleakClient) -> None:
        """Forget the kept-open connection once it drops so the next push reconnects."""
        if self.client is client:
            self.client = None


def _service_schema() -> vol.Schema:
    """Build the show-service schema."""
    return vol.Schema(
        {
            vol.Required("device_id"): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration=DOMAIN)
            ),
            vol.Optional(CONF_BIG_NUMBER): vol.All(
                vol.Coerce(float), vol.Range(min=-99.5, max=1999.5)
            ),
            vol.Optional(CONF_BIG_NUMBER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_SMALL_NUMBER): vol.All(
                vol.Coerce(float), vol.Range(min=-9, max=99)
            ),
            vol.Optional(CONF_SMALL_NUMBER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_PERMANENT): cv.boolean,
            vol.Optional(CONF_VALIDITY_PERIOD): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional(CONF_UNIT): vol.In(UNIT_VALUES),
            vol.Optional(CONF_HAPPY): cv.boolean,
            vol.Optional(CONF_SAD): cv.boolean,
            vol.Optional(CONF_BRACKET): cv.boolean,
            vol.Optional(CONF_PERCENT): cv.boolean,
            vol.Optional(CONF_BATTERY): cv.boolean,
        }
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the display service."""

    async def async_show_display(call: ServiceCall) -> None:
        entry = _entry_from_service_call(hass, call)
        runtime = entry.runtime_data
        payload = _build_payload(hass, entry.options, call.data)
        keep_alive = entry.options.get(CONF_KEEP_ALIVE, False)
        async with runtime.lock:
            await _async_write_display(hass, runtime, payload, keep_alive)

    hass.services.async_register(
        DOMAIN, SERVICE_SHOW, async_show_display, schema=_service_schema()
    )
    return True


def _entry_from_service_call(
    hass: HomeAssistant, call: ServiceCall
) -> PvvxConfigEntry:
    """Resolve the config entry targeted by a service call."""
    device_ids = call.data["device_id"]
    if isinstance(device_ids, str):
        device_ids = [device_ids]
    if len(device_ids) != 1:
        raise HomeAssistantError("Select exactly one PVVX display")

    device = dr.async_get(hass).async_get(device_ids[0])
    if device is None:
        raise HomeAssistantError("The selected PVVX device is no longer registered")

    entry = next(
        (
            config_entry
            for entry_id in device.config_entries
            if (config_entry := hass.config_entries.async_get_entry(entry_id))
            and config_entry.domain == DOMAIN
        ),
        None,
    )
    if entry is None:
        raise HomeAssistantError(
            "The selected device is not configured as a PVVX display"
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise HomeAssistantError("The selected PVVX display is not loaded")
    return entry


def _build_payload(
    hass: HomeAssistant,
    options: dict[str, Any],
    overrides: dict[str, Any],
) -> bytes:
    """Build the display frame from configured defaults and optional overrides."""
    big_number = _resolve_number(hass, overrides, options, CONF_BIG_NUMBER)
    small_number = _resolve_number(hass, overrides, options, CONF_SMALL_NUMBER)
    try:
        return encode_display_frame(
            big_number,
            small_number,
            _resolve_validity_period(overrides, options),
            overrides.get(CONF_UNIT, options.get(CONF_UNIT, "none")),
            overrides.get(CONF_HAPPY, options.get(CONF_HAPPY, False)),
            overrides.get(CONF_SAD, options.get(CONF_SAD, False)),
            overrides.get(CONF_BRACKET, options.get(CONF_BRACKET, False)),
            overrides.get(CONF_PERCENT, options.get(CONF_PERCENT, False)),
            overrides.get(CONF_BATTERY, options.get(CONF_BATTERY, False)),
        )
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err


def _resolve_number(
    hass: HomeAssistant,
    overrides: dict[str, Any],
    options: dict[str, Any],
    key: str,
) -> float:
    """Resolve a number from service overrides or the configured device defaults.

    Precedence: a literal override, then an override sensor entity, then the
    configured sensor entity, then the configured fallback number.
    """
    literal = overrides.get(key)
    entity_id = overrides.get(f"{key}_entity")
    if literal is not None and entity_id is not None:
        raise HomeAssistantError(f"Provide either {key} or {key}_entity, not both")

    if literal is not None:
        return literal
    if not entity_id:
        entity_id = options.get(f"{key}_entity")
    if not entity_id:
        return options.get(key, 0)

    sensor = hass.states.get(entity_id)
    try:
        return parse_sensor_state(entity_id, sensor.state if sensor else None)
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err


def _resolve_validity_period(
    overrides: dict[str, Any], options: dict[str, Any]
) -> int:
    """Return the validity time to send (the permanent sentinel in permanent mode)."""
    if overrides.get(CONF_PERMANENT, options.get(CONF_PERMANENT, True)):
        return PERMANENT_VALIDITY_PERIOD
    return overrides.get(
        CONF_VALIDITY_PERIOD,
        options.get(CONF_VALIDITY_PERIOD, DEFAULT_VALIDITY_PERIOD),
    )


async def async_setup_entry(hass: HomeAssistant, entry: PvvxConfigEntry) -> bool:
    """Set up a configured PVVX display."""
    address = entry.data[CONF_ADDRESS]
    runtime = PvvxRuntimeData(address)
    entry.runtime_data = runtime
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        manufacturer="PVVX",
        model="MiThermometer display",
        name=entry.title,
    )

    async def _async_close_connection() -> None:
        """Close a kept-open connection on unload or reload."""
        async with runtime.lock:
            client, runtime.client = runtime.client, None
        if client is not None and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT_SECONDS)
            except (BleakError, TimeoutError, OSError):
                _LOGGER.debug(
                    "Failed to disconnect PVVX display %s on unload",
                    address,
                    exc_info=True,
                )

    # Registered first so it runs last on unload, after the push listeners are gone.
    entry.async_on_unload(_async_close_connection)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _async_setup_auto_update(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PvvxConfigEntry) -> bool:
    """Unload a configured PVVX display.

    Listeners and timers registered with ``entry.async_on_unload`` are torn down
    automatically by Home Assistant once this returns ``True``.
    """
    return True


async def _async_options_updated(hass: HomeAssistant, entry: PvvxConfigEntry) -> None:
    """Reload the entry so updated options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_setup_auto_update(hass: HomeAssistant, entry: PvvxConfigEntry) -> None:
    """Push to the display automatically when source sensors change.

    Automatic updates are only wired up when at least one source sensor is
    configured, so a freshly added display with no sensors never pushes its
    fallback numbers on its own.
    """
    options = entry.options
    if not options.get(CONF_AUTO_UPDATE, True):
        return

    source_entities = [
        entity_id
        for key in (CONF_BIG_NUMBER_ENTITY, CONF_SMALL_NUMBER_ENTITY)
        if (entity_id := options.get(key))
    ]
    if not source_entities:
        return

    async def _push() -> None:
        # Skip while a source sensor is unavailable so the last value stays on screen.
        for entity_id in source_entities:
            state = hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Skipping PVVX update for %s: source %s is unavailable",
                    entry.runtime_data.address,
                    entity_id,
                )
                return
        try:
            payload = _build_payload(hass, entry.options, {})
            keep_alive = entry.options.get(CONF_KEEP_ALIVE, False)
            async with entry.runtime_data.lock:
                await _async_write_display(
                    hass, entry.runtime_data, payload, keep_alive
                )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Automatic PVVX display update for %s failed: %s",
                entry.runtime_data.address,
                err,
            )

    # All pushes share one debouncer: send immediately, then at most once per
    # cooldown with the latest value. Run in the background so a multi-second
    # Bluetooth write never blocks startup or shutdown.
    cooldown = options.get(CONF_MIN_UPDATE_INTERVAL, DEFAULT_MIN_UPDATE_INTERVAL)
    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=cooldown,
        immediate=True,
        function=_push,
        background=True,
    )
    entry.async_on_unload(debouncer.async_cancel)

    @callback
    def _request_push(*_args: Any) -> None:
        hass.async_create_background_task(
            debouncer.async_call(), f"pvvx display push {entry.runtime_data.address}"
        )

    @callback
    def _handle_source_event(event: Event) -> None:
        # Ignore attribute-only changes.
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if (
            new_state is not None
            and old_state is not None
            and new_state.state == old_state.state
        ):
            return
        _request_push()

    entry.async_on_unload(
        async_track_state_change_event(hass, source_entities, _handle_source_event)
    )
    # Periodic refresh: in permanent mode only to recover after a device reboot,
    # otherwise shortly before the pushed value expires.
    validity = options.get(CONF_VALIDITY_PERIOD, DEFAULT_VALIDITY_PERIOD)
    if options.get(CONF_PERMANENT, True):
        refresh = PERMANENT_KEEPALIVE_SECONDS
    else:
        refresh = max(validity - REFRESH_MARGIN_SECONDS, MIN_REFRESH_SECONDS)
    entry.async_on_unload(
        async_track_time_interval(hass, _request_push, timedelta(seconds=refresh))
    )
    # Initial push once Home Assistant has started (immediately if already running).
    entry.async_on_unload(async_at_started(hass, _request_push))


async def _async_acquire_client(
    hass: HomeAssistant,
    runtime: PvvxRuntimeData,
    keep_alive: bool,
    fresh: bool,
) -> BleakClient:
    """Return a connected client, reusing the kept-open one unless ``fresh`` is set."""
    address = runtime.address
    client = None if fresh else (runtime.client if keep_alive else None)
    if client is not None and not client.is_connected:
        client = runtime.client = None
    if client is not None:
        _LOGGER.debug("Reusing the open connection to PVVX display %s", address)
        return client

    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        if BluetoothReachabilityIntent is not None:
            reason = bluetooth.async_address_reachability_diagnostics(
                hass, address, BluetoothReachabilityIntent.CONNECTION
            )
            raise HomeAssistantError(f"No connectable Bluetooth path to {address}: {reason}")
        raise HomeAssistantError(
            f"No connectable Bluetooth path to {address}: the device is not "
            "currently reachable by a Bluetooth adapter or proxy that allows "
            "connections."
        )
    try:
        await close_stale_connections_by_address(address)
        # Cache the GATT for fast reconnects; a fresh connection forces rediscovery.
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            f"PVVX {address}",
            disconnected_callback=runtime.handle_disconnect if keep_alive else None,
            max_attempts=5,
            use_services_cache=not fresh,
        )
    except (BleakError, TimeoutError, OSError) as err:
        raise HomeAssistantError(
            f"Unable to connect to PVVX display {address}: {err}"
        ) from err
    _LOGGER.debug(
        "Opened a new connection to PVVX display %s (keep_alive=%s)", address, keep_alive
    )
    if keep_alive:
        runtime.client = client
    return client


async def _async_discard_client(
    runtime: PvvxRuntimeData, client: BleakClient, clear_gatt_cache: bool = False
) -> None:
    """Forget and disconnect a connection, optionally clearing its cached GATT."""
    runtime.client = None
    if clear_gatt_cache:
        # The device can report an incomplete GATT after a Service Changed
        # indication; clearing the cache forces a fresh discovery on reconnect.
        try:
            await clear_cache(runtime.address)
        except Exception:  # noqa: BLE001 - best effort, backend support varies
            _LOGGER.debug(
                "Could not clear GATT cache for PVVX display %s",
                runtime.address,
                exc_info=True,
            )
    try:
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT_SECONDS)
    except (BleakError, TimeoutError, OSError):
        _LOGGER.debug(
            "Failed to disconnect from PVVX display %s", runtime.address, exc_info=True
        )


async def _async_write_display(
    hass: HomeAssistant,
    runtime: PvvxRuntimeData,
    payload: bytes,
    keep_alive: bool,
) -> None:
    """Write the frame to the display. Callers must hold ``runtime.lock``.

    With keep_alive the connection stays open for the next write; otherwise it is
    closed after each write. If the write characteristic is missing (incomplete
    GATT after a Service Changed indication), reconnect fresh and retry once.
    """
    address = runtime.address
    for attempt in range(2):
        client = await _async_acquire_client(
            hass, runtime, keep_alive, fresh=attempt == 1
        )
        # Disconnected in the finally unless handed off or already discarded.
        owned = True
        try:
            characteristic = client.services.get_characteristic(CHARACTERISTIC_UUID)
            if characteristic is None:
                available = sorted(
                    str(char.uuid) for char in client.services.characteristics.values()
                )
                await _async_discard_client(runtime, client, clear_gatt_cache=True)
                owned = False
                if attempt == 0:
                    _LOGGER.debug(
                        "PVVX display %s reported an incomplete GATT (%s); reconnecting",
                        address,
                        available,
                    )
                    continue
                raise HomeAssistantError(
                    f"PVVX display {address} does not expose characteristic "
                    f"{CHARACTERISTIC_UUID}. Is this a display model running PVVX/ATC "
                    f"firmware? Characteristics found: {available}"
                )

            # Prefer write-without-response (as ESPHome does); BlueZ rejects it
            # unless the characteristic advertises it.
            properties = characteristic.properties
            if "write-without-response" in properties:
                response = False
            elif "write" in properties:
                response = True
            else:
                raise HomeAssistantError(
                    f"PVVX characteristic {CHARACTERISTIC_UUID} on {address} is not "
                    f"writable (properties: {properties})"
                )

            try:
                await asyncio.wait_for(
                    client.write_gatt_char(characteristic, payload, response=response),
                    WRITE_TIMEOUT_SECONDS,
                )
            except (BleakError, TimeoutError, OSError) as err:
                raise HomeAssistantError(
                    f"Unable to write to PVVX display {address}: {err}"
                ) from err

            _LOGGER.debug(
                "Sent display frame %s to PVVX device %s (response=%s, keep_alive=%s)",
                payload.hex(),
                address,
                response,
                keep_alive,
            )
            if keep_alive:
                owned = False  # hand off: keep the connection open for the next write
            else:
                await asyncio.sleep(DISCONNECT_DELAY_SECONDS)
            return
        finally:
            if owned:
                await _async_discard_client(runtime, client)
