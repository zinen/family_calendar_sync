"""Unit tests for the core sync engine in calendar_sync.py.

These tests build a lightweight fake `hass` (see conftest.py) rather than
the full pytest-homeassistant-custom-component `hass` fixture, since
calendar_sync.py only touches hass.data['calendar'] and
hass.services.async_call. This keeps the tests fast and focused on our own
logic.
"""

from dataclasses import asdict
from datetime import date, datetime, timedelta

import pytest

from homeassistant.util import dt as dt_util

from custom_components.calendar_sync.calendar_sync import (
    FromEvent,
    SyncDateRange,
    SyncWorker,
    ToCalendar,
    ToEvent,
    sync_family_calendar,
)

from .conftest import FakeCalendarEntity, all_day_event, make_fake_hass, timed_event


def _base_options() -> dict:
    return {
        "days_to_sync": 30,
        "days_to_sync_past": 30,
        "ignore_event_if_title_starts_with": None,
    }


# --- Sync range -------------------------------------------------------------


def test_sync_date_range_uses_whole_calendar_days():
    """Zero past days includes events from earlier on the current date."""
    sync_range = SyncDateRange(
        start=datetime(2026, 3, 1, 15, 30),
        days_to_sync=7,
        days_to_sync_past=0,
    )

    assert sync_range.start_including_past == dt_util.start_of_local_day(
        sync_range.start
    )
    assert sync_range.end == dt_util.start_of_local_day(
        sync_range.start
    ) + timedelta(days=8)


def test_sync_date_range_extends_by_complete_past_days():
    sync_range = SyncDateRange(
        start=datetime(2026, 3, 1, 15, 30),
        days_to_sync=0,
        days_to_sync_past=2,
    )

    assert sync_range.start_including_past == dt_util.start_of_local_day(
        sync_range.start
    ) - timedelta(days=2)
    assert sync_range.end == dt_util.start_of_local_day(sync_range.start) + timedelta(
        days=1
    )


# --- Event / hashing -------------------------------------------------------


def test_from_event_hash_roundtrips_through_to_event():
    """The hash embedded in a synced event's description must be recoverable."""
    event = FromEvent(
        {
            "start": datetime(2026, 3, 1, 9, 0),
            "end": datetime(2026, 3, 1, 10, 0),
            "summary": "Soccer practice",
            "description": "bring cleats",
            "uid": "source-uid-1",
        }
    )
    to_data = event.get_data_for_to_event()
    to_event = ToEvent(to_data)

    assert to_event.hashed_value == event.hashed_value
    assert f"[{event.hashed_value}]" in to_data["description"]


def test_from_event_hash_changes_when_event_content_changes():
    """Different event content must hash differently (used to detect edits)."""
    base = {
        "start": datetime(2026, 3, 1, 9, 0),
        "end": datetime(2026, 3, 1, 10, 0),
        "summary": "Soccer practice",
        "description": None,
        "uid": "source-uid-1",
    }
    event_a = FromEvent(dict(base))
    event_b = FromEvent({**base, "summary": "Soccer practice (rescheduled)"})

    assert event_a.hashed_value != event_b.hashed_value


# --- Keyword matching --------------------------------------------------------


def test_keyword_match_respects_word_boundaries():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass,
        entity_id="calendar.kids",
        sync_date_range=None,
        keywords=["art"],
    )
    assert to_cal.is_a_keyword_match("Art class") is True
    # "art" must not match as a substring inside "party"
    assert to_cal.is_a_keyword_match("Birthday party") is False


def test_keyword_match_is_case_insensitive():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass,
        entity_id="calendar.kids",
        sync_date_range=None,
        keywords=["Soccer"],
    )
    assert to_cal.is_a_keyword_match("SOCCER practice") is True


def test_keyword_match_supports_multi_word_phrases():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass,
        entity_id="calendar.kids",
        sync_date_range=None,
        keywords=["with kids"],
    )
    assert to_cal.is_a_keyword_match("Dinner With Kids!") is True
    assert to_cal.is_a_keyword_match("Dinner without children") is False


def test_keyword_match_escapes_regex_special_characters():
    """A keyword containing regex metacharacters must be matched literally."""
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass,
        entity_id="calendar.kids",
        sync_date_range=None,
        keywords=["3.14 club"],
    )
    assert to_cal.is_a_keyword_match("3.14 club meetup") is True
    # A literal dot should not act as a wildcard and match "3X14 club"
    assert to_cal.is_a_keyword_match("3X14 club meetup") is False


def test_no_keywords_never_matches():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass, entity_id="calendar.kids", sync_date_range=None, keywords=[]
    )
    assert to_cal.is_a_keyword_match("Anything at all") is False


# --- ensure_min_duration -----------------------------------------------------


def test_ensure_min_duration_extends_zero_length_timed_event():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass, entity_id="calendar.kids", sync_date_range=None, keywords=[]
    )
    same_time = datetime(2026, 3, 1, 9, 0)
    payload = {
        "start_date_time": same_time,
        "end_date_time": same_time,
        "summary": "Instant event",
    }
    result = to_cal.ensure_min_duration(payload)
    assert result["end_date_time"] > same_time


def test_ensure_min_duration_extends_all_day_event_given_as_date_objects():
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass, entity_id="calendar.kids", sync_date_range=None, keywords=[]
    )
    same_day = date(2026, 3, 1)
    payload = {"start_date": same_day, "end_date": same_day, "summary": "All day"}
    result = to_cal.ensure_min_duration(payload)
    assert result["end_date"] == same_day + timedelta(days=1)


def test_ensure_min_duration_handles_all_day_event_given_as_iso_strings():
    """Regression test: date arithmetic must not crash on string dates.

    The original code did `start_d + timedelta(days=1)` without converting
    string dates first, which raised TypeError whenever a backend returned
    ISO date strings instead of `date` objects.
    """
    fake_hass = make_fake_hass([FakeCalendarEntity("calendar.kids")])
    to_cal = ToCalendar(
        hass=fake_hass, entity_id="calendar.kids", sync_date_range=None, keywords=[]
    )
    payload = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-01",
        "summary": "All day (string dates)",
    }
    result = to_cal.ensure_min_duration(payload)  # must not raise
    assert result["end_date"] == date(2026, 3, 1) + timedelta(days=1)


# --- SyncWorker: the copy_all_from regression -------------------------------


@pytest.mark.asyncio
async def test_copy_all_from_syncs_even_with_no_keywords():
    """Regression test for the original bug.

    A `to` calendar configured with `copy_all_from` and an empty keyword
    list must still receive every event from its designated `from`
    calendar. In the original code this silently synced nothing, because
    a set was compared to a string with `==` instead of `in`.
    """
    from_entity = FakeCalendarEntity(
        "calendar.parent1",
        events=[timed_event("Dentist"), timed_event("Piano lesson")],
    )
    to_entity = FakeCalendarEntity("calendar.kids")
    fake_hass = make_fake_hass([from_entity, to_entity])

    config = {
        "from": [{"entity_id": "calendar.parent1"}],
        "to": [
            {
                "entity_id": "calendar.kids",
                "keywords": [],
                "copy_all_from": ["calendar.parent1"],
            }
        ],
        "options": _base_options(),
    }

    result = await sync_family_calendar(fake_hass, config)

    assert result["events_added"] == 2
    assert result["errors"] == 0
    # the service call to actually create the events must have fired twice
    assert fake_hass.services.async_call.call_count == 2


@pytest.mark.asyncio
async def test_no_keywords_and_no_copy_all_from_syncs_nothing():
    """A `to` calendar with neither keywords nor copy_all_from should get nothing.

    (The config flow now blocks creating this configuration in the UI, but
    the sync engine itself should still behave sanely if it ever occurs,
    e.g. via a hand-edited config.)
    """
    from_entity = FakeCalendarEntity("calendar.parent1", events=[timed_event("Dentist")])
    to_entity = FakeCalendarEntity("calendar.kids")
    fake_hass = make_fake_hass([from_entity, to_entity])

    config = {
        "from": [{"entity_id": "calendar.parent1"}],
        "to": [{"entity_id": "calendar.kids", "keywords": [], "copy_all_from": []}],
        "options": _base_options(),
    }

    result = await sync_family_calendar(fake_hass, config)

    assert result["events_added"] == 0
    fake_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_keyword_match_only_copies_matching_events():
    from_entity = FakeCalendarEntity(
        "calendar.parent1",
        events=[timed_event("Soccer practice"), timed_event("Team meeting")],
    )
    to_entity = FakeCalendarEntity("calendar.kids")
    fake_hass = make_fake_hass([from_entity, to_entity])

    config = {
        "from": [{"entity_id": "calendar.parent1"}],
        "to": [
            {"entity_id": "calendar.kids", "keywords": ["soccer"], "copy_all_from": []}
        ],
        "options": _base_options(),
    }

    result = await sync_family_calendar(fake_hass, config)

    assert result["events_added"] == 1


# --- SyncWorker: stale event removal ----------------------------------------


@pytest.mark.asyncio
async def test_stale_to_event_is_removed_when_source_event_is_gone():
    from_entity = FakeCalendarEntity("calendar.parent1", events=[])

    # Build a "to" event that looks like it was synced from a `from` event
    # that no longer exists (i.e. its hash isn't in any `from` calendar).
    stale_source = FromEvent(
        {
            "start": datetime(2026, 3, 1, 9, 0),
            "end": datetime(2026, 3, 1, 10, 0),
            "summary": "Cancelled trip",
            "description": None,
            "uid": "gone",
        }
    )
    stale_to_data = stale_source.get_data_for_to_event()
    stale_to_data["uid"] = "to-uid-1"
    stale_calendar_event = timed_event(
        "Cancelled trip", description=stale_to_data["description"], uid="to-uid-1"
    )
    to_entity = FakeCalendarEntity("calendar.kids", events=[stale_calendar_event])
    fake_hass = make_fake_hass([from_entity, to_entity])

    config = {
        "from": [{"entity_id": "calendar.parent1"}],
        "to": [
            {
                "entity_id": "calendar.kids",
                "keywords": [],
                "copy_all_from": ["calendar.parent1"],
            }
        ],
        "options": _base_options(),
    }

    result = await sync_family_calendar(fake_hass, config)

    assert result["events_removed"] == 1
    to_entity.async_delete_event.assert_awaited_once_with("to-uid-1")


@pytest.mark.asyncio
async def test_stale_to_event_is_removed_when_it_no_longer_matches_filter():
    """A source event that remains present must be removed when deselected."""
    source_calendar_event = timed_event("Dentist", uid="source-uid-1")
    source_event = FromEvent(asdict(source_calendar_event))
    copied_description = source_event.get_data_for_to_event()["description"]

    from_entity = FakeCalendarEntity(
        "calendar.parent1", events=[source_calendar_event]
    )
    to_entity = FakeCalendarEntity(
        "calendar.kids",
        events=[
            timed_event(
                "Dentist", description=copied_description, uid="to-uid-1"
            )
        ],
    )
    fake_hass = make_fake_hass([from_entity, to_entity])

    result = await sync_family_calendar(
        fake_hass,
        {
            "from": [{"entity_id": "calendar.parent1"}],
            "to": [
                {
                    "entity_id": "calendar.kids",
                    "keywords": ["soccer"],
                    "copy_all_from": [],
                }
            ],
            "options": _base_options(),
        },
    )

    assert result["events_removed"] == 1
    to_entity.async_delete_event.assert_awaited_once_with("to-uid-1")


# --- SyncWorker: error isolation ---------------------------------------------


@pytest.mark.asyncio
async def test_one_failing_event_does_not_abort_the_rest():
    """A single event create failure must not stop the other events syncing."""
    from_entity = FakeCalendarEntity(
        "calendar.parent1",
        events=[timed_event("Good event 1"), timed_event("Good event 2")],
    )
    to_entity = FakeCalendarEntity("calendar.kids")
    fake_hass = make_fake_hass([from_entity, to_entity])
    fake_hass.services.async_call.side_effect = [Exception("boom"), None]

    worker = SyncWorker(
        fake_hass,
        {
            "from": [{"entity_id": "calendar.parent1"}],
            "to": [
                {
                    "entity_id": "calendar.kids",
                    "keywords": [],
                    "copy_all_from": ["calendar.parent1"],
                }
            ],
            "options": _base_options(),
        },
    )
    await worker.async_setup()
    stats = await worker.async_sync_calendars()

    assert stats.events_added == 1
    assert stats.errors == 1
