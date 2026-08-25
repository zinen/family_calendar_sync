"""Module to handle syncing calendar events from `from` calendars to `to` calendars."""

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
import logging
import re

from homeassistant.components.calendar import CalendarEntity
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DEFAULT_DAYS_TO_SYNC, DEFAULT_DAYS_TO_SYNC_PAST, HASH_LENGTH

HASH_REGEX = re.compile(r"\[([a-z0-9]{8})\]", re.IGNORECASE)

MIN_EVENT_DURATION = timedelta(seconds=1)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SyncDateRange:
    """A dataclass for start and end dates for syncing."""

    start: datetime
    days_to_sync: int
    days_to_sync_past: int = 0

    @property
    def end(self) -> datetime:
        """Return the end datetime."""
        end_datetime = self.start + timedelta(days=self.days_to_sync)
        return dt_util.as_local(end_datetime)

    @property
    def start_including_past(self) -> datetime:
        """Return the start datetime including past boundary."""
        start_datetime = self.start - timedelta(days=self.days_to_sync_past)
        return dt_util.as_local(start_datetime)


@dataclass
class SyncStats:
    """Result of a single sync pass, used by the coordinator/sensors."""

    events_added: int = 0
    events_removed: int = 0
    errors: int = 0


class Event:
    """An event class to assist in managing dependent events."""

    def __init__(self, data: dict) -> None:
        """Initialize event object.

        Args:
            data (dict): event data from home assistant service call

        """
        if not isinstance(data, dict):
            raise TypeError(data)
        self._data: dict = data
        self._hashed_value: str | None = None
        self._description: str | None = None
        self._set_hashed_value()

    def add_hash_to_description(
        self,
        description: str | None,
        hashed_value: str,
    ) -> str | None:
        """Modify description by adding hashed value to it."""
        if description:
            return f"{description} \n[{hashed_value}]"
        return f"[{hashed_value}]"

    def get_data_for_event_creation(self) -> dict:
        """Get event data in the format to create a new HA event."""
        data = {}
        if self.is_all_day:
            data["start_date"] = self.start
            data["end_date"] = self.end
        else:
            data["start_date_time"] = self.start
            data["end_date_time"] = self.end
        data["summary"] = self.title
        data["description"] = self.add_hash_to_description(
            description=self.description,
            hashed_value=self.hashed_value,
        )
        if self.location is not None:
            data["location"] = self.location
        return data

    @property
    def is_all_day(self) -> bool:
        """Is event an all day event."""
        return not isinstance(self.data["start"], datetime)

    @property
    def hashed_value(self) -> str:
        """Return the hashed value of the event."""
        return self._hashed_value

    @property
    def data(self) -> dict:
        """Return the event data."""
        return self._data

    @property
    def title(self) -> str | None:
        """Return the event's title aka summary."""
        return self._data.get("summary", None)

    @property
    def description(self) -> str | None:
        """Return the event's description."""
        return self._data.get("description", None)

    @description.setter
    def description(self, value) -> None:
        self._data["description"] = value

    @property
    def location(self) -> str | None:
        """Return the event's location."""
        return self._data.get("location", None)

    @property
    def start(self) -> str | None:
        """Return the event's start date or datetime."""
        return self._data.get("start", None)

    @property
    def end(self) -> str | None:
        """Return the event's end date or datetime."""
        return self._data.get("end", None)

    @property
    def uid(self) -> str | None:
        """Return the event's uid, if any."""
        return self.data.get("uid")

    @uid.setter
    def uid(self, value) -> None:
        """Set the event's uid."""
        self._data["uid"] = value

    def _set_hashed_value(self) -> None:
        raise NotImplementedError


class ToEvent(Event):
    """An event that already exists on a `to` (destination) calendar."""

    def _set_hashed_value(self) -> str | None:
        """Extract the hashed_value from the event description field. None, if not found."""
        hashed_value = None
        if description := self.description:
            if match := HASH_REGEX.search(description):
                hashed_value = match.group(1)
        self._hashed_value = hashed_value


class FromEvent(Event):
    """An event pulled from a `from` (source) calendar."""

    def create_to_event(self) -> ToEvent:
        """Create the `ToEvent` that should be written to the destination calendar."""
        to_data = self.get_data_for_to_event()
        return ToEvent(to_data)

    def _set_hashed_value(self):
        """Calculate the hashed value of the event data."""
        data = f"{self.data}".encode()
        hashed_value = sha256(data).hexdigest()
        self._hashed_value = hashed_value[:HASH_LENGTH]

    def get_data_for_to_event(self) -> dict:
        """Create a dict of data for use in `ToEvent` creation."""
        event_data: dict = {
            "start": self.start,
            "end": self.end,
            "summary": self.title,
        }
        if description := self.description:
            # append the hashed_value to the description, which is where we will look for
            # the hashed value when attempting to sync events
            event_data["description"] = f"{description} [{self.hashed_value}]"
        else:
            event_data["description"] = f"[{self.hashed_value}]"

        if location := self.location:
            event_data["location"] = location

        return event_data


class Calendar:
    """Calendar object to manage Events."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        sync_date_range: SyncDateRange,
        cal_type: str,
    ) -> None:
        """Initialize Calendar object."""
        self._hass = hass
        self._entity_id = entity_id
        self._sync_date_range = sync_date_range
        self._type = cal_type
        self._events: list[Event] = []
        self._hash_map: dict[str, Event] = {}
        calendar_component = hass.data.get("calendar")
        self._entity: CalendarEntity | None = (
            calendar_component.get_entity(self.entity_id)
            if calendar_component
            else None
        )

    async def async_setup(self) -> None:
        """Set up async stuff."""
        if self.entity:
            await self.async_load_events()
        else:
            _LOGGER.error("Could not load Entity for %s", self.entity_id)

    @property
    def entity(self) -> CalendarEntity | None:
        """Return the entity."""
        return self._entity

    @property
    def events(self) -> list[Event]:
        """Return the events."""
        return self._events

    @events.setter
    def events(self, value: list[Event]):
        self._events = value

    @property
    def hash_map(self) -> dict:
        """Return the hash map."""
        return self._hash_map

    @property
    def entity_id(self) -> str:
        """Return the entity_id."""
        return self._entity_id

    @property
    def type(self) -> str:
        """Return the calendar type: 'from' or 'to'."""
        return self._type

    @property
    def hash_set(self) -> set[str]:
        """Return the hashes."""
        return set(self.hash_map.keys())

    def remove_events_to_ignore(self) -> None:
        """Remove events from that need to be ignored."""
        raise NotImplementedError

    async def async_load_events(self) -> bool:
        """Get events using hass object and load into calendar object."""
        if self.entity:
            events_data = await self.entity.async_get_events(
                self._hass,
                self._sync_date_range.start_including_past,
                self._sync_date_range.end,
            )

            event_cls = FromEvent if self.type == "from" else ToEvent
            for event_data in events_data:
                self._events.append(event_cls(asdict(event_data)))

        if self.type == "from":
            self.remove_events_to_ignore()
        self._create_hash_map()
        return True

    def _create_hash_map(self):
        for event in self.events:
            # not all events will have hashes
            # ex: events created manually on the destination calendar
            if (hashed_value := event.hashed_value) is not None:
                self._hash_map[hashed_value] = event

    def get_event_with_hash(self, hashed_value: str) -> Event | None:
        """Get the Event with the corresponding hash, if any."""
        return self.hash_map.get(hashed_value, None)

    def is_event_in_calendar_with_hash(self, hashed_value: str) -> bool:
        """Indicate if event with hash is already in calendar."""
        return self.get_event_with_hash(hashed_value=hashed_value) is not None


class FromCalendar(Calendar):
    """A source calendar that events are read from."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        sync_date_range: SyncDateRange,
        ignore_string: str | None = None,
    ) -> None:
        """Initialize FromCalendar object."""
        super().__init__(
            hass=hass,
            entity_id=entity_id,
            sync_date_range=sync_date_range,
            cal_type="from",
        )
        self._ignore_string = ignore_string

    @property
    def ignore_string(self) -> str | None:
        """Return ignore_string."""
        return self._ignore_string

    def remove_events_to_ignore(self) -> None:
        """Remove events whose title starts with the string we are to ignore."""
        if self.ignore_string:
            self.events = [
                event
                for event in self.events
                if not (event.title or "").startswith(self._ignore_string)
            ]


class ToCalendar(Calendar):
    """A destination calendar that events are written to."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        sync_date_range: SyncDateRange,
        keywords: list[str],
    ) -> None:
        """Initialize ToCalendar object."""
        super().__init__(
            hass=hass,
            entity_id=entity_id,
            sync_date_range=sync_date_range,
            cal_type="to",
        )
        self._keywords = keywords
        if keywords:
            reg_string = r"\b(" + f"{'|'.join(re.escape(k) for k in keywords)}" + r")\b"
            self._regex_pattern = re.compile(reg_string, re.IGNORECASE | re.MULTILINE)
        else:
            self._regex_pattern = None

    @property
    def keywords(self) -> list[str]:
        """Return the keywords."""
        return self._keywords

    def is_a_keyword_match(self, title: str | None) -> bool:
        """Determine if a keyword is found in `title`."""
        if not title or not self._keywords or self._regex_pattern is None:
            return False
        return bool(self._regex_pattern.search(title))

    async def _async_delete_event_from_ha(self, hashed_value: str) -> None:
        """Delete the destination event from home assistant with matching `hashed_value`."""
        event = self.get_event_with_hash(hashed_value=hashed_value)
        if event is None or event.uid is None:
            _LOGGER.warning(
                "No deletable event found with hash %s in %s; skipping",
                hashed_value,
                self.entity_id,
            )
            return
        await self.entity.async_delete_event(event.uid)

    async def async_delete_event_from_ha(self, values: str | set[str]) -> int:
        """Delete the destination event(s) from home assistant with matching hash(es).

        A failure deleting one event is logged and does not stop the rest
        from being processed. Returns the number of events actually removed.
        """
        if isinstance(values, set):
            hashes_to_remove = self.overlapping_hashes(values)
        elif isinstance(values, str):
            hashes_to_remove = [values] if values in self.hash_set else []
        else:
            raise TypeError(values)

        removed = 0
        for value in hashes_to_remove:
            try:
                await self._async_delete_event_from_ha(hashed_value=value)
                removed += 1
            except Exception as err:  # noqa: BLE001 - isolate one bad event from the rest
                _LOGGER.error(
                    "Failed to delete event (hash %s) from %s: %s",
                    value,
                    self.entity_id,
                    err,
                )
        return removed

    async def _async_add_event_to_ha(self, event: FromEvent) -> None:
        """Add the `FromEvent` to this `ToCalendar` in HA."""
        payload = event.get_data_for_event_creation()
        payload["entity_id"] = self.entity_id
        payload = self.ensure_min_duration(payload)
        _LOGGER.debug("Creating event on %s with payload %s", self.entity_id, payload)
        await self._hass.services.async_call(
            "calendar",
            "create_event",
            payload,
            blocking=True,
        )

    async def async_add_event(self, event: FromEvent) -> None:
        """Add the `FromEvent` to the `ToCalendar` in HA and in this object."""
        await self._async_add_event_to_ha(event=event)
        to_event = event.create_to_event()
        self._hash_map[to_event.hashed_value] = to_event
        self.events.append(to_event)

    def overlapping_hashes(self, hashed_values) -> list[str]:
        """Return list of hashed_values if they exist for this calendar."""
        return [
            hashed_value
            for hashed_value in hashed_values
            if hashed_value in self.hash_set
        ]

    def ensure_min_duration(self, payload: dict) -> dict:
        """Extend events that are less than minimum length to avoid errors."""
        if "start_date_time" in payload and "end_date_time" in payload:
            start = payload["start_date_time"]
            end = payload["end_date_time"]

            start_dt = dt_util.parse_datetime(start) if isinstance(start, str) else start
            end_dt = dt_util.parse_datetime(end) if isinstance(end, str) else end

            if start_dt and end_dt and end_dt <= start_dt:
                payload["end_date_time"] = start_dt + MIN_EVENT_DURATION

        if "start_date" in payload and "end_date" in payload:
            start_d = payload["start_date"]
            end_d = payload["end_date"]

            # Some backends may hand back ISO date strings instead of
            # `date` objects; normalize before doing arithmetic so this
            # doesn't raise TypeError: can only concatenate str.
            if isinstance(start_d, str):
                start_d = dt_util.parse_date(start_d)
            if isinstance(end_d, str):
                end_d = dt_util.parse_date(end_d)

            if start_d and end_d and end_d <= start_d:
                payload["start_date"] = start_d
                payload["end_date"] = start_d + timedelta(days=1)

        return payload


class SyncWorker:
    """Sync events from `from` calendars to `to` calendars."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize SyncWorker."""
        self._hass = hass
        self._config = config
        # to_entity_id -> set(from_entity_id, ...)
        self._copy_all_map: dict[str, set[str]] = {}
        self.stats = SyncStats()

        options = self._config.get("options") or {}
        days_to_sync = options.get("days_to_sync", DEFAULT_DAYS_TO_SYNC)
        days_to_sync_past = options.get("days_to_sync_past", DEFAULT_DAYS_TO_SYNC_PAST)
        self._ignore_event_if_title_starts_with = options.get(
            "ignore_event_if_title_starts_with"
        ) or None

        self._sync_date_range = SyncDateRange(
            start=dt_util.as_local(datetime.now()),
            days_to_sync=days_to_sync,
            days_to_sync_past=days_to_sync_past,
        )

        self._calendars: dict[str, list[Calendar]] = {"from": [], "to": []}

    @property
    def config(self) -> dict:
        """Return the config."""
        return self._config

    @property
    def calendars(self) -> dict[str, list[Calendar]]:
        """Return the calendars."""
        return self._calendars

    @property
    def num_of_from_calendars(self) -> int:
        """Return the number of `from` calendars."""
        return len(self.calendars["from"])

    @property
    def num_of_to_calendars(self) -> int:
        """Return the number of `to` calendars."""
        return len(self.calendars["to"])

    async def async_setup(self) -> None:
        """Set up async stuff, loading all `from` and `to` calendars concurrently."""
        from_configs = self.config.get("from") or []
        to_configs = self.config.get("to") or []

        async def _setup_from(cal_config: dict) -> FromCalendar:
            calendar = FromCalendar(
                hass=self._hass,
                entity_id=cal_config["entity_id"],
                sync_date_range=self._sync_date_range,
                ignore_string=self._ignore_event_if_title_starts_with,
            )
            await calendar.async_setup()
            return calendar

        async def _setup_to(cal_config: dict) -> ToCalendar:
            to_entity_id = cal_config["entity_id"]
            if copy_all_from := cal_config.get("copy_all_from"):
                # Normalize defensively in case something bypassed schema
                parents = (
                    {copy_all_from}
                    if isinstance(copy_all_from, str)
                    else set(copy_all_from)
                )
                self._copy_all_map[to_entity_id] = parents

            calendar = ToCalendar(
                hass=self._hass,
                entity_id=to_entity_id,
                sync_date_range=self._sync_date_range,
                keywords=cal_config.get("keywords") or [],
            )
            await calendar.async_setup()
            return calendar

        if from_configs:
            self.calendars["from"] = list(
                await asyncio.gather(*(_setup_from(c) for c in from_configs))
            )
        if to_configs:
            # copy_all_map must be populated before setup runs, and setup
            # for each `to` calendar is independent, so this can also run
            # concurrently.
            self.calendars["to"] = list(
                await asyncio.gather(*(_setup_to(c) for c in to_configs))
            )

        if self.num_of_from_calendars == 0 or self.num_of_to_calendars == 0:
            _LOGGER.error(
                "There need to be >0 for each 'from' and 'to' calendars. "
                "But got %s from, %s to.",
                self.num_of_from_calendars,
                self.num_of_to_calendars,
            )

    def _set_of_hashes_by_cal_type(self, cal_type: str) -> set:
        result: set[str] = set()
        for cal in self.calendars[cal_type]:
            result.update(cal.hash_set)
        return result

    async def _async_remove_events_from_to_cals(self, event_hashes: set[str]) -> None:
        """Remove stale events from `to` calendars."""
        for cal in self.calendars["to"]:
            self.stats.events_removed += await cal.async_delete_event_from_ha(
                event_hashes
            )

    async def _async_sync_pair(
        self, from_cal: FromCalendar, to_cal: ToCalendar
    ) -> None:
        """Sync events from a single `from` calendar into a single `to` calendar."""
        copy_all_parents = self._copy_all_map.get(to_cal.entity_id, set())
        should_add_all_events = from_cal.entity_id in copy_all_parents

        for from_event in from_cal.events:
            if not (
                to_cal.is_a_keyword_match(from_event.title) or should_add_all_events
            ):
                continue
            # make sure the event doesn't already exist in the destination calendar
            if to_cal.is_event_in_calendar_with_hash(from_event.hashed_value):
                continue
            try:
                await to_cal.async_add_event(from_event)
                self.stats.events_added += 1
            except Exception as err:  # noqa: BLE001 - one bad event shouldn't abort the run
                self.stats.errors += 1
                _LOGGER.error(
                    "Failed to add event %r to %s: %s",
                    from_event.title,
                    to_cal.entity_id,
                    err,
                )

    async def async_sync_calendars(self) -> SyncStats:
        """Sync `from` calendar events into `to` calendars. Returns run stats."""
        # compare hashes to find destination events whose source no longer exists
        from_hashes = self._set_of_hashes_by_cal_type("from")
        to_hashes = self._set_of_hashes_by_cal_type("to")
        need_removed = to_hashes - from_hashes
        # TODO: Need to reparse all events in case config has changed.
        # Can a previous config be saved to do a diff against?
        await self._async_remove_events_from_to_cals(need_removed)

        # Only sync `from` calendars into their designated `to` calendars
        for to_cal in self.calendars["to"]:
            copy_all_parents = self._copy_all_map.get(to_cal.entity_id, set())
            for from_cal in self.calendars["from"]:
                # Only sync if:
                # 1. This `from` calendar is designated as copy_all for this
                #    `to` calendar, OR
                # 2. The `to` calendar has keywords that might match events
                #    in this `from` calendar
                if from_cal.entity_id in copy_all_parents or to_cal.keywords:
                    await self._async_sync_pair(from_cal, to_cal)

        return self.stats


async def sync_family_calendar(hass: HomeAssistant, config: dict) -> dict:
    """Sync `from` calendar events into `to` calendars based on criteria.

    Returns a stats dict: {"events_added", "events_removed", "errors"}.
    """
    worker = SyncWorker(hass, config)
    await worker.async_setup()
    stats = await worker.async_sync_calendars()
    return {
        "events_added": stats.events_added,
        "events_removed": stats.events_removed,
        "errors": stats.errors,
    }
