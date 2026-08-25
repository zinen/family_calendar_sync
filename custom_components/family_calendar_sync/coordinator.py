"""DataUpdateCoordinator for Family Calendar Sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .calendar_sync import sync_family_calendar
from .const import (
    CONF_COPY_ALL_FROM,
    CONF_DAYS_TO_SYNC,
    CONF_DAYS_TO_SYNC_PAST,
    CONF_FROM_ENTITIES,
    CONF_IGNORE_PREFIX,
    CONF_KEYWORDS,
    CONF_SYNC_INTERVAL_MINUTES,
    CONF_TO_ENTITY_ID,
    DEFAULT_DAYS_TO_SYNC,
    DEFAULT_DAYS_TO_SYNC_PAST,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SyncRunResult:
    """Result of the most recent sync run, exposed to sensors/buttons."""

    events_added: int = 0
    events_removed: int = 0
    errors: int = 0
    last_sync: datetime | None = field(default=None)


def build_sync_config(entry: ConfigEntry) -> dict:
    """Translate a config entry (data + options) into the dict `SyncWorker` expects."""
    options = entry.options
    to_entity_id = entry.data[CONF_TO_ENTITY_ID]
    from_entities = options.get(CONF_FROM_ENTITIES, [])

    return {
        "from": [{"entity_id": entity_id} for entity_id in from_entities],
        "to": [
            {
                "entity_id": to_entity_id,
                "keywords": options.get(CONF_KEYWORDS, []),
                "copy_all_from": options.get(CONF_COPY_ALL_FROM, []),
            }
        ],
        "options": {
            "days_to_sync": options.get(CONF_DAYS_TO_SYNC, DEFAULT_DAYS_TO_SYNC),
            "days_to_sync_past": options.get(
                CONF_DAYS_TO_SYNC_PAST, DEFAULT_DAYS_TO_SYNC_PAST
            ),
            "ignore_event_if_title_starts_with": options.get(CONF_IGNORE_PREFIX, ""),
        },
    }


class FamilyCalendarSyncCoordinator(DataUpdateCoordinator[SyncRunResult]):
    """Coordinator that runs the sync on an interval and on manual request."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        interval_minutes = entry.options.get(
            CONF_SYNC_INTERVAL_MINUTES, DEFAULT_SYNC_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_TO_ENTITY_ID]}",
            update_interval=timedelta(minutes=interval_minutes),
        )

    async def _async_update_data(self) -> SyncRunResult:
        """Run one sync pass. Raised errors surface as `unavailable` sensors."""
        config = build_sync_config(self.entry)
        try:
            result = await sync_family_calendar(hass=self.hass, config=config)
        except Exception as err:  # noqa: BLE001 - surface any failure via the coordinator
            raise UpdateFailed(f"Family calendar sync failed: {err}") from err

        return SyncRunResult(
            events_added=result["events_added"],
            events_removed=result["events_removed"],
            errors=result["errors"],
            last_sync=dt_util.utcnow(),
        )
