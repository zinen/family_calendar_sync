"""Button platform for Family Calendar Sync - manual 'Sync now' trigger."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TO_ENTITY_ID, DOMAIN
from .coordinator import FamilyCalendarSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Family Calendar Sync 'Sync now' button for this entry."""
    coordinator: FamilyCalendarSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SyncNowButton(coordinator, entry)])


class SyncNowButton(CoordinatorEntity[FamilyCalendarSyncCoordinator], ButtonEntity):
    """A button that triggers an immediate sync for this entry."""

    _attr_has_entity_name = True
    _attr_translation_key = "sync_now"

    def __init__(
        self, coordinator: FamilyCalendarSyncCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_sync_now"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_TO_ENTITY_ID],
            entry_type="service",
        )

    async def async_press(self) -> None:
        """Trigger an immediate sync."""
        await self.coordinator.async_request_refresh()
