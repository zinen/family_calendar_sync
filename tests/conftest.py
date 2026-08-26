"""Shared fixtures for Filtered Calendar Merger tests."""

from datetime import date, datetime, timedelta
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

if sys.platform == "win32":
    import pytest_socket

    # Windows' asyncio event loop needs an IPv4 socket pair. Keep the test
    # plugin's localhost-only connection guard, but do not replace
    # ``socket.socket`` itself as it does on Unix.
    def _allow_socket_creation(**_kwargs: object) -> None:
        """Leave socket creation available for the Windows event loop."""

    pytest_socket.disable_socket = _allow_socket_creation

from homeassistant.components.calendar import CalendarEvent
from homeassistant.util import dt as dt_util

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make this repo's custom_components/ loadable by every test."""
    yield


class FakeCalendarEntity:
    """A minimal stand-in for a real HA CalendarEntity."""

    def __init__(self, entity_id: str, events: list[CalendarEvent] | None = None):
        self.entity_id = entity_id
        self._events = events or []
        self.async_delete_event = AsyncMock()

    async def async_get_events(self, hass, start_date, end_date):
        return self._events


class FakeCalendarComponent:
    """A minimal stand-in for hass.data['calendar']."""

    def __init__(self):
        self._entities: dict[str, FakeCalendarEntity] = {}

    def add(self, entity: FakeCalendarEntity) -> None:
        self._entities[entity.entity_id] = entity

    def get_entity(self, entity_id: str):
        return self._entities.get(entity_id)


def make_fake_hass(entities: list[FakeCalendarEntity]) -> MagicMock:
    """Build a minimal fake `hass` object sufficient for filtered_calendar_merger.py.

    This intentionally does NOT use the real pytest-homeassistant-custom-component
    `hass` fixture: filtered_calendar_merger.py only touches `hass.data['calendar']` and
    `hass.services.async_call`, so a lightweight fake keeps these tests fast
    and focused on our own logic rather than HA's core setup.
    """
    fake_hass = MagicMock()
    component = FakeCalendarComponent()
    for entity in entities:
        component.add(entity)
    fake_hass.data = {"calendar": component}
    fake_hass.services.async_call = AsyncMock()
    return fake_hass


def timed_event(
    summary: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> CalendarEvent:
    """Build a CalendarEvent with a timed (non-all-day) start/end."""
    start = start or dt_util.as_local(datetime(2026, 1, 1, 9, 0, 0))
    end = end or start + timedelta(hours=1)
    return CalendarEvent(
        start=start, end=end, summary=summary, description=description, uid=uid
    )


def all_day_event(
    summary: str,
    *,
    start: date | None = None,
    end: date | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> CalendarEvent:
    """Build an all-day CalendarEvent (date, not datetime, start/end)."""
    start = start or date(2026, 1, 1)
    end = end or start
    return CalendarEvent(
        start=start, end=end, summary=summary, description=description, uid=uid
    )
