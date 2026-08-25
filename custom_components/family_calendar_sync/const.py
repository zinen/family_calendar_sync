"""Constants for Family Calendar Sync component."""

from homeassistant.const import Platform

DOMAIN = "family_calendar_sync"
SERVICE_SYNC = "sync"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

# --- Config entry keys -------------------------------------------------
# entry.data (set at creation, not editable afterwards - part of unique_id)
CONF_TO_ENTITY_ID = "to_entity_id"

# entry.options (editable via the Options flow)
CONF_FROM_ENTITIES = "from_entities"
CONF_COPY_ALL_FROM = "copy_all_from"
CONF_KEYWORDS = "keywords"
CONF_DAYS_TO_SYNC = "days_to_sync"
CONF_DAYS_TO_SYNC_PAST = "days_to_sync_past"
CONF_IGNORE_PREFIX = "ignore_event_if_title_starts_with"
CONF_SYNC_INTERVAL_MINUTES = "sync_interval_minutes"

# --- Defaults ------------------------------------------------------------
DEFAULT_DAYS_TO_SYNC = 7
DEFAULT_DAYS_TO_SYNC_PAST = 0
DEFAULT_SYNC_INTERVAL_MINUTES = 15
MIN_SYNC_INTERVAL_MINUTES = 5

HASH_LENGTH = 8
