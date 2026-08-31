"""The Filtered Calendar Merger integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SERVICE_SYNC
from .coordinator import FilteredCalendarMergerCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
    }
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Filtered Calendar Merger from a config entry."""
    coordinator = FilteredCalendarMergerCoordinator(hass, entry)
    if coordinator.update_interval is not None:
        # DataUpdateCoordinator only schedules periodic refreshes while it has
        # listeners. The sync itself is integration work, so it must not stop
        # when the optional sensor/button entities are disabled or unavailable.
        entry.async_on_unload(coordinator.async_add_listener(lambda: None))
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_service(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SYNC)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. new sync interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_service(hass: HomeAssistant) -> None:
    """Register the `filtered_calendar_merger.sync` action, once."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC):
        return

    async def handle_sync(call: ServiceCall) -> None:
        """Trigger an immediate sync for one entry, or all entries if none given."""
        target_entry_id = call.data.get("config_entry_id")
        coordinators: list[FilteredCalendarMergerCoordinator] = list(
            hass.data.get(DOMAIN, {}).values()
        )

        if target_entry_id:
            coordinator = hass.data.get(DOMAIN, {}).get(target_entry_id)
            if coordinator is None:
                raise ValueError(
                    f"No Filtered Calendar Merger config entry with id {target_entry_id}"
                )
            coordinators = [coordinator]

        for coordinator in coordinators:
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SYNC, handle_sync, schema=SERVICE_SYNC_SCHEMA
    )
