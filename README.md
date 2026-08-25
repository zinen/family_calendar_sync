# family_calendar_sync

[Family Calendar Sync](https://github.com/McCroden/family_calendar_sync) is a custom component for Home Assistant that syncs events **from** one or more source calendars **to** one or more destination calendars, and keeps them in sync on a schedule you control.

You point it at one or more `from` calendar entities, and a `to` calendar entity to copy events into. You can copy every event, or only events whose title matches a keyword (e.g. a family member's name). It keeps things in sync by hashing each source event and storing the first 8 characters of that hash in the description of the copied event, so it can tell what it created, what changed, and what should be removed.

> **This fork replaces the original `parent`/`child` YAML configuration with a UI-based setup (`from`/`to` naming) and built-in scheduling.** See [What changed](#what-changed-in-this-fork) below if you're coming from the original project.

**Which Calendar Integrations Work?**

- CalDAV:
    - Only works as a `from` calendar - the integration can't create events.
- Google Calendar:
    - Works as both `from` and `to` if it's set up with two-way sync permissions.
- Local Calendar:
    - Works as both `from` and `to`.
- Remote Calendar:
    - Only works as a `from` calendar - events are read-only/imported.

## Background

I saw the Skylight calendar and thought it looked cool. But I didn't like that I'd have to use their app to attach the events to a child's calendars. My partner and I already have a good system in place that we like. I built this tool to automate it, so our kids can see their events.

### Our Family's Process

I have an iCloud calendar and I share it with my partner. My partner also has an iCloud calendar and shares it with me. This is useful because if my partner adds an event titled "Dentist," I know it's for them. This came in handy when designing this component too, because I can just say "copy all of the events from my shared calendar to my local calendar named dad" (see `Copy all events from` below).

When my partner or I create events for the kids, we put their name in the event. This component looks for keywords (e.g. their name) and copies those events to their calendars.

## Features

- Works with CalDAV (iCloud), Google Calendar, and Local Calendar entities
- **Configured entirely through the UI** - Settings -> Devices & Services -> Add Integration
- Copies events from one or more `from` calendars into a `to` calendar and keeps them in sync automatically on a schedule you set (in minutes)
- A **"Sync now" button** and a **"Last sync" sensor** (with events-added / events-removed / error counts) are created for every sync you configure
- A `family_calendar_sync.sync` action is still available for automations, and can target one sync or all of them
- If an event is added directly to a `to` calendar, it will not be touched by this integration
- Specify how many days into the future (and past) to sync
- Ignore source events whose title starts with a character you choose
- A `to` calendar can match on many keywords (e.g. a name, "family", "kids", etc.), and/or copy everything from specific `from` calendars via `copy_all_from`
- Only deletes a `to` event if this integration created it **and** the matching source event is gone or no longer matches
- A single bad event (e.g. a calendar backend rejecting one create call) is logged and skipped rather than aborting the whole sync run

## Install

This component is installed via [HACS](https://hacs.xyz).

1. Install HACS first
1. Go to **HACS** > **⁝** > **Custom repositories**
1. Add this repository and choose **Integration**, then click **ADD**
1. Go back to the main HACS landing page and search `family calendar sync`
1. Click on it, then click **Download**
1. Restart Home Assistant

## Configuration

Everything is configured through the UI - **YAML configuration is no longer supported** as of v0.2.0.

1. Go to **Settings -> Devices & Services -> Add Integration**
1. Search for **Family Calendar Sync**
1. For each destination calendar you want to sync events into, add a new instance:
   - **Sync to calendar** - the destination calendar (e.g. `calendar.snoop`)
   - **Sync from calendar(s)** - one or more source calendars to read events from
   - **Copy all events from these calendar(s)** *(optional)* - a subset of the "from" calendars whose events should *all* be copied, regardless of keywords
   - **Only copy events matching these keywords** *(optional)* - e.g. a name, "family", "kids". Matched case-insensitively against event titles, as whole words
   - **Ignore source events whose title starts with** *(optional)* - e.g. `!` for private events the kids don't need to see
   - **Days ahead / Days in the past to sync**
   - **Sync every (minutes)** - how often this sync runs automatically
1. Repeat for each destination calendar

> At least one of "keywords" or "copy all events from" is required - the UI will block saving a sync that would never copy anything.

Each configured sync gets its own device with two entities:
- `sensor.<to_calendar>_last_sync` - timestamp of the last run, with `events_added`, `events_removed`, and `errors` attributes
- `button.<to_calendar>_sync_now` - triggers an immediate sync

### Example setup

Family structure:
  - Napoleon Dynamite (dad) - `calendar.napoleon_dynamite`
  - Nomi Malone (mom) - `calendar.nomi_malone`
  - Snoop (kid) - `calendar.snoop`
  - Scott Pilgrim (kid) - `calendar.scott_pilgrim`
  - Cupid (kid) - `calendar.cupid`

You'd add **five** Family Calendar Sync instances, one per destination calendar:

| Sync to | Sync from | Copy all from | Keywords |
|---|---|---|---|
| `calendar.dad` | napoleon_dynamite, nomi_malone | napoleon_dynamite | dad, napoleon, family |
| `calendar.mom` | napoleon_dynamite, nomi_malone | nomi_malone | mom, nomi, family |
| `calendar.snoop` | napoleon_dynamite, nomi_malone | *(none)* | snoop, family, kids, kiddos |
| `calendar.scott_pilgrim` | napoleon_dynamite, nomi_malone | *(none)* | scott, family, kids, kiddos |
| `calendar.cupid` | napoleon_dynamite, nomi_malone | *(none)* | cupid, family, kids, kiddos |

Here is what the synced calendar looks like:

![screenshot](assets/screenshot.png)

### The `family_calendar_sync.sync` action

Since every sync already runs on its own schedule, you shouldn't need this for normal use - but it's there for automations that want to force an immediate sync (e.g. after a "I just added an event" trigger).

```yaml
# Sync everything
action: family_calendar_sync.sync

# Sync just one destination calendar's config entry
action: family_calendar_sync.sync
data:
  config_entry_id: 01ABCXYZ...   # find this on the sync's device page
```

Or just press its **Sync now** button instead.

## What changed in this fork

This fork restructures the original YAML-only integration into a config-flow-based (UI) integration, and renames `parent`/`child` to `from`/`to` throughout:

- **UI configuration** instead of `configuration.yaml` - one config entry per destination (`to`) calendar, added/edited from Settings -> Devices & Services
- **`parent` -> `from`, `child` -> `to`** in every setting, entity, and internal class name
- **Automatic scheduled syncing** with a configurable interval (previously required you to build your own automation calling the service on a timer)
- **`sensor.*_last_sync`** and **`button.*_sync_now`** entities for visibility and manual control per sync
- **Bug fix:** `copy_all_from` with no keywords previously never synced anything - a `set` was being compared to a `str` with `==` instead of checking membership with `in`. Fixed, and the config flow now refuses to save a sync that would never copy anything.
- **Bug fix:** all-day events whose start/end dates arrived as ISO strings instead of `date` objects would crash with `TypeError` when the integration tried to extend a zero-length event
- **Robustness:** one calendar backend rejecting a single event no longer aborts the rest of that sync run; failures are logged and counted instead
- **Robustness:** `from`/`to` calendars are loaded concurrently instead of one at a time
- **Test suite** using `pytest` + `pytest-homeassistant-custom-component` (see [Development](#development))

**This is a breaking change** if you're upgrading from a YAML-based install: your `family_calendar_sync:` YAML block is no longer read (you'll see a repair notice pointing you to the UI), and you'll need to recreate your syncs through **Add Integration**.

## Development

```bash
pip install -r requirements-test.txt
pytest
```

Tests are split by concern:
- `tests/test_calendar_sync.py` - the sync engine itself (hashing, keyword matching, date-handling edge cases, the `copy_all_from` regression, error isolation) against a lightweight fake `hass`
- `tests/test_config_flow.py` - the config flow and options flow, using the real Home Assistant test harness
- `tests/test_init.py` - entry setup/unload and the `family_calendar_sync.sync` action

## TODO

- [ ] Add check if `to` calendar is CalDAV and raise a clear error, since Home Assistant can't create events on a CalDAV entity
- [ ] Run sync when a source event changes, not just on the interval
- [ ] Case-sensitive keyword matching option
- [ ] Support to-do lists in addition to calendars
- [ ] Friendlier error surfaced in the UI if a `to` calendar can't accept created events (e.g. read-only CalDAV/Google without two-way sync)
