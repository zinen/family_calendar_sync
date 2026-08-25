"""Config flow for Calendar Sync."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import selector

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
    MIN_SYNC_INTERVAL_MINUTES,
)


def _calendar_entity_selector(multiple: bool) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="calendar", multiple=multiple)
    )


def _sync_settings_schema(defaults: dict[str, Any], *, include_to: bool) -> vol.Schema:
    """Build the shared schema for the create/options forms."""
    fields: dict[Any, Any] = {}

    # ``from_entities`` used to contain every source, while ``copy_all_from``
    # was a subset of it.  Keep that on-disk format for compatibility, but
    # present the two user decisions independently in the UI.
    copy_all_from = defaults.get(CONF_COPY_ALL_FROM, [])
    matching_from = [
        entity_id
        for entity_id in defaults.get(CONF_FROM_ENTITIES, [])
        if entity_id not in copy_all_from
    ]

    if include_to:
        fields[vol.Required(CONF_TO_ENTITY_ID)] = _calendar_entity_selector(
            multiple=False
        )

    fields.update(
        {
            vol.Optional(
                CONF_COPY_ALL_FROM, default=copy_all_from
            ): _calendar_entity_selector(multiple=True),
            vol.Optional(
                CONF_FROM_ENTITIES, default=matching_from
            ): _calendar_entity_selector(multiple=True),
            vol.Optional(
                CONF_KEYWORDS, default=defaults.get(CONF_KEYWORDS, [])
            ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            vol.Optional(
                CONF_IGNORE_PREFIX, default=defaults.get(CONF_IGNORE_PREFIX, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_DAYS_TO_SYNC,
                default=defaults.get(CONF_DAYS_TO_SYNC, DEFAULT_DAYS_TO_SYNC),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=365, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_DAYS_TO_SYNC_PAST,
                default=defaults.get(
                    CONF_DAYS_TO_SYNC_PAST, DEFAULT_DAYS_TO_SYNC_PAST
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=365, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_SYNC_INTERVAL_MINUTES,
                default=defaults.get(
                    CONF_SYNC_INTERVAL_MINUTES, DEFAULT_SYNC_INTERVAL_MINUTES
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SYNC_INTERVAL_MINUTES,
                    max=1440,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                )
            ),
        }
    )
    return vol.Schema(fields)


def _validate_sync_settings(
    user_input: dict[str, Any], *, to_entity_id: str
) -> dict[str, str]:
    """Cross-field validation shared by the config flow and options flow.

    Returns a dict of field -> error key, empty if valid.
    """
    errors: dict[str, str] = {}

    matching_from = set(user_input.get(CONF_FROM_ENTITIES, []))
    copy_all_from = set(user_input.get(CONF_COPY_ALL_FROM, []))
    keywords = [k for k in user_input.get(CONF_KEYWORDS, []) if k.strip()]
    all_sources = matching_from | copy_all_from

    if not all_sources:
        errors["base"] = "no_source_calendars_selected"
    elif to_entity_id in matching_from:
        errors[CONF_FROM_ENTITIES] = "to_cannot_be_from"
    elif to_entity_id in copy_all_from:
        errors[CONF_COPY_ALL_FROM] = "to_cannot_be_from"

    if not errors and matching_from & copy_all_from:
        errors[CONF_FROM_ENTITIES] = "calendar_in_both_sync_modes"

    if not errors and matching_from and not keywords:
        errors[CONF_KEYWORDS] = "keywords_required_for_matching_calendars"

    return errors


def _options_from_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Store the source union in the legacy-compatible options format."""
    keywords = [k.strip() for k in user_input.get(CONF_KEYWORDS, []) if k.strip()]
    copy_all_from = user_input.get(CONF_COPY_ALL_FROM, [])
    matching_from = user_input.get(CONF_FROM_ENTITIES, [])
    # dict preserves selection order while removing any duplicate defensively.
    from_entities = list(dict.fromkeys([*copy_all_from, *matching_from]))
    return {
        CONF_FROM_ENTITIES: from_entities,
        CONF_COPY_ALL_FROM: copy_all_from,
        CONF_KEYWORDS: keywords,
        CONF_IGNORE_PREFIX: user_input.get(CONF_IGNORE_PREFIX, ""),
        CONF_DAYS_TO_SYNC: user_input.get(CONF_DAYS_TO_SYNC, DEFAULT_DAYS_TO_SYNC),
        CONF_DAYS_TO_SYNC_PAST: user_input.get(
            CONF_DAYS_TO_SYNC_PAST, DEFAULT_DAYS_TO_SYNC_PAST
        ),
        CONF_SYNC_INTERVAL_MINUTES: user_input.get(
            CONF_SYNC_INTERVAL_MINUTES, DEFAULT_SYNC_INTERVAL_MINUTES
        ),
    }


class FamilyCalendarSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Calendar Sync (one entry per `to` calendar)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: pick the `to` calendar and its sync settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            to_entity_id = user_input[CONF_TO_ENTITY_ID]
            errors = _validate_sync_settings(user_input, to_entity_id=to_entity_id)

            if not errors:
                await self.async_set_unique_id(to_entity_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=to_entity_id,
                    data={CONF_TO_ENTITY_ID: to_entity_id},
                    options=_options_from_user_input(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_sync_settings_schema(user_input or {}, include_to=True),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return FamilyCalendarSyncOptionsFlow()


class FamilyCalendarSyncOptionsFlow(OptionsFlow):
    """Handle options (edit from-entities/keywords/schedule) for an existing entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the sync settings for this `to` calendar."""
        to_entity_id = self.config_entry.data[CONF_TO_ENTITY_ID]
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_sync_settings(user_input, to_entity_id=to_entity_id)
            if not errors:
                return self.async_create_entry(
                    title="", data=_options_from_user_input(user_input)
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_sync_settings_schema(
                user_input or dict(self.config_entry.options), include_to=False
            ),
            errors=errors,
            description_placeholders={"to_entity_id": to_entity_id},
        )
