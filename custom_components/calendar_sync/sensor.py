"""Sensor platform for Calendar Sync - shows the status of the last sync."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TO_ENTITY_ID, DOMAIN
from .coordinator import FamilyCalendarSyncCoordinator, SyncRunResult


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Calendar Sync sensor for this entry."""
    coordinator: FamilyCalendarSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LastSyncSensor(coordinator, entry)])


class LastSyncSensor(CoordinatorEntity[FamilyCalendarSyncCoordinator], SensorEntity):
    """Reports the timestamp of the most recent sync, with counts as attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: FamilyCalendarSyncCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_TO_ENTITY_ID],
            entry_type="service",
        )

    @property
    def native_value(self):
        """Return the timestamp of the last completed sync."""
        result: SyncRunResult | None = self.coordinator.data
        return result.last_sync if result else None

    @property
    def extra_state_attributes(self) -> dict:
        """Return event counts from the last sync run."""
        result: SyncRunResult | None = self.coordinator.data
        if result is None:
            return {}
        return {
            "events_added": result.events_added,
            "events_removed": result.events_removed,
            "errors": result.errors,
        }
