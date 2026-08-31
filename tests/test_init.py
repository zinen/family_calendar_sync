"""Tests for integration setup/unload and the `filtered_calendar_merger.sync` service."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.filtered_calendar_merger.const import (
    CONF_COPY_ALL_FROM,
    CONF_FROM_ENTITIES,
    CONF_KEYWORDS,
    CONF_SYNC_INTERVAL_MINUTES,
    CONF_TO_ENTITY_ID,
    DOMAIN,
    SERVICE_SYNC,
)

SYNC_RESULT = {"events_added": 1, "events_removed": 0, "errors": 0}


def _make_entry(
    to_entity: str = "calendar.kids",
    sync_interval_minutes: int | None = None,
    *,
    disable_polling: bool = False,
) -> MockConfigEntry:
    options = {
        CONF_FROM_ENTITIES: ["calendar.parent1"],
        CONF_COPY_ALL_FROM: ["calendar.parent1"],
        CONF_KEYWORDS: [],
    }
    if sync_interval_minutes is not None:
        options[CONF_SYNC_INTERVAL_MINUTES] = sync_interval_minutes

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=to_entity,
        data={CONF_TO_ENTITY_ID: to_entity},
        options=options,
        pref_disable_polling=disable_polling,
    )


@pytest.mark.asyncio
async def test_setup_entry_creates_coordinator_and_registers_service(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
        AsyncMock(return_value=SYNC_RESULT),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.services.has_service(DOMAIN, SERVICE_SYNC)


@pytest.mark.asyncio
async def test_unload_entry_cleans_up_and_removes_service_when_last(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
        AsyncMock(return_value=SYNC_RESULT),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert not hass.services.has_service(DOMAIN, SERVICE_SYNC)


@pytest.mark.asyncio
async def test_zero_sync_interval_requires_a_manual_sync(hass):
    entry = _make_entry(sync_interval_minutes=0)
    entry.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with patch(
        "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
        sync_mock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.update_interval is None
        sync_mock.assert_not_awaited()

        await hass.services.async_call(DOMAIN, SERVICE_SYNC, {}, blocking=True)
        await hass.async_block_till_done()

    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_nonzero_sync_interval_runs_repeatedly_without_entity_listeners(hass):
    entry = _make_entry(sync_interval_minutes=1)
    entry.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with (
        patch(
            "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
            sync_mock,
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        calls_after_setup = sync_mock.call_count
        now = dt_util.utcnow()
        for minutes in (1, 2):
            async_fire_time_changed(hass, now + timedelta(minutes=minutes))
            await hass.async_block_till_done()

    assert sync_mock.call_count == calls_after_setup + 2


@pytest.mark.asyncio
async def test_periodic_sync_stops_when_entry_is_unloaded(hass):
    entry = _make_entry(sync_interval_minutes=1)
    entry.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with (
        patch(
            "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
            sync_mock,
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        calls_after_setup = sync_mock.call_count

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

    assert sync_mock.call_count == calls_after_setup


@pytest.mark.asyncio
async def test_periodic_sync_honors_disabled_polling_preference(hass):
    entry = _make_entry(sync_interval_minutes=1, disable_polling=True)
    entry.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with (
        patch(
            "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
            sync_mock,
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        calls_after_setup = sync_mock.call_count

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

    assert sync_mock.call_count == calls_after_setup


@pytest.mark.asyncio
async def test_sync_service_triggers_refresh_for_all_entries_by_default(hass):
    entry_a = _make_entry("calendar.kids_a")
    entry_b = _make_entry("calendar.kids_b")
    entry_a.add_to_hass(hass)
    entry_b.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with patch(
        "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
        sync_mock,
    ):
        # Setting up the first entry for a domain also bootstraps every
        # other existing entry for that domain in the same call.
        assert await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

        calls_before = sync_mock.call_count
        await hass.services.async_call(DOMAIN, SERVICE_SYNC, {}, blocking=True)
        await hass.async_block_till_done()

    # one refresh call per entry
    assert sync_mock.call_count == calls_before + 2


@pytest.mark.asyncio
async def test_sync_service_targets_a_single_entry(hass):
    entry_a = _make_entry("calendar.kids_a")
    entry_b = _make_entry("calendar.kids_b")
    entry_a.add_to_hass(hass)
    entry_b.add_to_hass(hass)

    sync_mock = AsyncMock(return_value=SYNC_RESULT)
    with patch(
        "custom_components.filtered_calendar_merger.coordinator.sync_filtered_calendar_merger",
        sync_mock,
    ):
        assert await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

        calls_before = sync_mock.call_count
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SYNC,
            {"config_entry_id": entry_a.entry_id},
            blocking=True,
        )
        await hass.async_block_till_done()

    # only entry_a's coordinator should have refreshed
    assert sync_mock.call_count == calls_before + 1
