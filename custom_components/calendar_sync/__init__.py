"""The Calendar Sync integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, PLATFORMS, SERVICE_SYNC
from .coordinator import FamilyCalendarSyncCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML, if present.

    YAML configuration is no longer supported - everything is configured
    through the UI (Settings -> Devices & Services -> Add Integration).
    If legacy YAML config is found, raise a repair issue pointing the user
    at the UI instead of silently ignoring their configuration.
    """
    if DOMAIN in config:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "yaml_no_longer_supported",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="yaml_no_longer_supported",
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Calendar Sync from a config entry."""
    coordinator = FamilyCalendarSyncCoordinator(hass, entry)
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
    """Register the `calendar_sync.sync` action, once."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC):
        return

    async def handle_sync(call: ServiceCall) -> None:
        """Trigger an immediate sync for one entry, or all entries if none given."""
        target_entry_id = call.data.get("config_entry_id")
        coordinators: list[FamilyCalendarSyncCoordinator] = list(
            hass.data.get(DOMAIN, {}).values()
        )

        if target_entry_id:
            coordinator = hass.data.get(DOMAIN, {}).get(target_entry_id)
            if coordinator is None:
                raise ValueError(
                    f"No Calendar Sync config entry with id {target_entry_id}"
                )
            coordinators = [coordinator]

        for coordinator in coordinators:
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SYNC, handle_sync, schema=SERVICE_SYNC_SCHEMA
    )
