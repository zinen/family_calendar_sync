"""Tests for the Family Calendar Sync config flow and options flow."""

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.calendar_sync.const import (
    CONF_COPY_ALL_FROM,
    CONF_FROM_ENTITIES,
    CONF_KEYWORDS,
    CONF_SYNC_INTERVAL_MINUTES,
    CONF_TO_ENTITY_ID,
    DOMAIN,
)

VALID_USER_INPUT = {
    CONF_TO_ENTITY_ID: "calendar.kids",
    # parent1 is a full-sync source; parent2 is a filtered source.
    CONF_COPY_ALL_FROM: ["calendar.parent1"],
    CONF_FROM_ENTITIES: ["calendar.parent2"],
    CONF_KEYWORDS: ["soccer"],
    "days_to_sync": 14,
    "days_to_sync_past": 1,
    CONF_SYNC_INTERVAL_MINUTES: 30,
}


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_valid_data(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], VALID_USER_INPUT
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "calendar.kids"
    assert result2["data"] == {CONF_TO_ENTITY_ID: "calendar.kids"}
    assert result2["options"][CONF_FROM_ENTITIES] == [
        "calendar.parent1",
        "calendar.parent2",
    ]
    assert result2["options"][CONF_COPY_ALL_FROM] == ["calendar.parent1"]
    assert result2["options"][CONF_SYNC_INTERVAL_MINUTES] == 30


@pytest.mark.asyncio
async def test_user_flow_rejects_to_calendar_as_its_own_source(hass):
    bad_input = {
        **VALID_USER_INPUT,
        CONF_FROM_ENTITIES: ["calendar.kids"],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], bad_input
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"][CONF_FROM_ENTITIES] == "to_cannot_be_from"


@pytest.mark.asyncio
async def test_user_flow_requires_a_source_calendar(hass):
    bad_input = {
        **VALID_USER_INPUT,
        CONF_COPY_ALL_FROM: [],
        CONF_FROM_ENTITIES: [],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], bad_input
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "no_source_calendars_selected"


@pytest.mark.asyncio
async def test_user_flow_rejects_calendar_in_both_sync_modes(hass):
    bad_input = {
        **VALID_USER_INPUT,
        CONF_FROM_ENTITIES: ["calendar.parent1"],
        CONF_COPY_ALL_FROM: ["calendar.parent1"],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], bad_input
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"][CONF_FROM_ENTITIES] == "calendar_in_both_sync_modes"


@pytest.mark.asyncio
async def test_user_flow_requires_keywords_for_filtered_sources(hass):
    bad_input = {**VALID_USER_INPUT, CONF_COPY_ALL_FROM: [], CONF_KEYWORDS: []}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], bad_input
    )

    assert result2["type"] == FlowResultType.FORM
    assert (
        result2["errors"][CONF_KEYWORDS]
        == "keywords_required_for_matching_calendars"
    )


@pytest.mark.asyncio
async def test_duplicate_to_entity_is_rejected(hass):
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="calendar.kids",
        data={CONF_TO_ENTITY_ID: "calendar.kids"},
        options={
            CONF_FROM_ENTITIES: ["calendar.parent1"],
            CONF_COPY_ALL_FROM: ["calendar.parent1"],
            CONF_KEYWORDS: [],
        },
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], VALID_USER_INPUT
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_options_flow_updates_settings(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="calendar.kids",
        data={CONF_TO_ENTITY_ID: "calendar.kids"},
        options={
            CONF_FROM_ENTITIES: ["calendar.parent1"],
            CONF_COPY_ALL_FROM: ["calendar.parent1"],
            CONF_KEYWORDS: [],
            CONF_SYNC_INTERVAL_MINUTES: 15,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_COPY_ALL_FROM: ["calendar.parent1"],
            CONF_KEYWORDS: ["soccer"],
            CONF_FROM_ENTITIES: ["calendar.parent2"],
            "days_to_sync": 7,
            "days_to_sync_past": 0,
            CONF_SYNC_INTERVAL_MINUTES: 60,
        },
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_SYNC_INTERVAL_MINUTES] == 60
    assert result2["data"][CONF_KEYWORDS] == ["soccer"]
