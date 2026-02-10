import json
import os
import shutil
import logging
from datetime import datetime
from collections import OrderedDict
from typing import Any, Mapping

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api
from homeassistant.util import slugify

from .const import DOMAIN, VERSION
from .utils import (
    config_path,
    handle_ws_yaml_update,
    async_load_yaml_from_dir,
    async_load_yaml_file,
    async_remove_file_or_folder,
    async_save_yaml,
    async_load_yaml
)
from .process_yaml import reload_configuration

_LOGGER = logging.getLogger(__name__)

# Reload event constants
RELOAD_HOME = "dwains_dashboard_homepage_card_reload"
RELOAD_DEVICES = "dwains_dashboard_devicespage_card_reload"

WS_PREFIX = "dwains_dashboard/"

# -----------------------------
# Configuration / Version
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): f"{WS_PREFIX}configuration/get"})
async def ws_get_configuration(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Mapping[str, Any]) -> None:
    """Return full configuration for dashboard."""
    areas = await async_load_yaml_file(hass, config_path(hass, "areas.yaml"))
    entities = await async_load_yaml_file(hass, config_path(hass, "entities.yaml"))
    devices = await async_load_yaml_file(hass, config_path(hass, "devices.yaml"))
    entries = hass.config_entries.async_entries(DOMAIN)
    if entries:
        # Convert mappingproxy to dict and filter out unwanted keys
        homepage_header = {k: v for k, v in dict(entries[0].options).items()
                   if k not in ("sidepanel_icon", "sidepanel_title")}
    else:
        homepage_header = {}
    #homepage_header = await async_load_yaml_file(hass, config_path(hass, "settings.yaml"))

    area_cards = await async_load_yaml_from_dir(hass, config_path(hass, "cards/areas"), nested=True)
    device_cards = await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices"), nested=True)
    entity_cards = await async_load_yaml_from_dir(hass, config_path(hass, "cards/entities"), strip_ext=True)
    devices_card = await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices_card"), strip_ext=True)
    entities_popup = await async_load_yaml_from_dir(hass, config_path(hass, "cards/entities_popup"), strip_ext=True)
    devices_popup = await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices_popup"), strip_ext=True)

    # Load more_pages if both page.yaml & config.yaml exist
    more_pages = OrderedDict()
    more_pages_dir = config_path(hass, "more_pages")
    if os.path.isdir(more_pages_dir):
        subdirs = [
            d for d in await hass.async_add_executor_job(os.listdir, more_pages_dir)
            if os.path.isdir(os.path.join(more_pages_dir, d))
        ]
        for subdir in subdirs:
            config_file = os.path.join(more_pages_dir, subdir, "config.yaml")
            page_file = os.path.join(more_pages_dir, subdir, "page.yaml")
            if os.path.exists(config_file) and os.path.exists(page_file):
                more_pages[subdir] = await async_load_yaml_file(hass, config_file)

    connection.send_result(
        msg["id"],
        {
            "areas": areas,
            "area_cards": area_cards,
            "device_cards": device_cards,
            "entity_cards": entity_cards,
            "entities_popup": entities_popup,
            "entities": entities,
            "devices": devices,
            "homepage_header": homepage_header,
            "more_pages": more_pages,
            "installed_version": VERSION,
            "devices_card": devices_card,
            "devices_popup": devices_popup,
        }
    )

@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}edit_homepage_header",
        vol.Optional("disableClock"): bool,
        vol.Optional("amPmClock"): bool,
        vol.Optional("disableWelcomeMessage"): bool,
        vol.Optional("v2Mode"): bool,
        vol.Optional("disableSensorGraph"): bool,
        vol.Optional("weatherEntity"): str,
        vol.Optional("invertCover"): bool,
        vol.Optional("alarmEntity"): str,
    }
)
async def ws_edit_homepage_header(hass, connection, msg):
    """Update homepage header options via config entry."""

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_result(msg["id"], {"success": False, "error": "No config entry found"})
        return

    entry = entries[0]

    # Map frontend keys to options keys
    updates = {
        "disable_clock": msg.get("disableClock"),
        "am_pm_clock": msg.get("amPmClock"),
        "disable_welcome_message": msg.get("disableWelcomeMessage"),
        "v2_mode": msg.get("v2Mode"),
        "disable_sensor_graph": msg.get("disableSensorGraph"),
        "invert_cover": msg.get("invertCover"),
        "weather_entity": msg.get("weatherEntity"),
        "alarm_entity": msg.get("alarmEntity"),
    }

    # Remove None values (keys not sent by frontend)
    updates = {k: v for k, v in updates.items() if v is not None}

    # Merge with existing options
    new_options = {**entry.options, **updates}
    hass.config_entries.async_update_entry(entry, options=new_options)

    # Fire reload if needed
    hass.bus.async_fire(RELOAD_HOME)

    connection.send_result(msg["id"], {"success": True, "message": "Homepage header saved"})

@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): f"{WS_PREFIX}get_version"})
async def ws_get_version(hass, connection, msg):
    """Return installed dashboard version."""
    connection.send_result(msg["id"], {"version": VERSION})

# -----------------------------
# Blueprints
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): f"{WS_PREFIX}get_blueprints"})
async def ws_get_blueprints(hass, connection, msg):
    """Return all installed blueprints."""
    blueprints_dir = hass.config.path("dwains-dashboard/blueprints")
    blueprints = {}
    if not os.path.isdir(blueprints_dir):
        connection.send_result(msg["id"], {"blueprints": blueprints})
        return

    for fname in os.listdir(blueprints_dir):
        if not fname.endswith(".yaml"):
            continue
        path = os.path.join(blueprints_dir, fname)
        try:
            blueprints[fname] = await async_load_yaml_file(hass, path)
        except Exception as e:
            _LOGGER.error("Failed to load blueprint %s: %s", fname, e)

    connection.send_result(msg["id"], {"blueprints": blueprints})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}install_blueprint",
    vol.Required("filename"): str,
    vol.Required("data"): vol.Any(dict, list),
})
async def ws_install_blueprint(hass, connection, msg):
    """Install a blueprint."""
    filename = msg["filename"]
    data = msg["data"]
    blueprints_dir = hass.config.path("dwains-dashboard/blueprints")
    filepath = os.path.join(blueprints_dir, filename)
    try:
        await async_save_yaml(hass, filepath, data)
    except Exception as err:
        _LOGGER.error("Failed to install blueprint %s: %s", filename, err)
        connection.send_error(msg["id"], "install_failed", f"Failed to install blueprint {filename}")
        return
    connection.send_result(msg["id"], {"success": True, "filename": filename})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}delete_blueprint",
    vol.Required("blueprint"): str,
})
async def ws_delete_blueprint(hass, connection, msg):
    """Delete a blueprint."""
    filename = msg["blueprint"]
    path = hass.config.path("dwains-dashboard/blueprints", filename)
    try:
        await async_remove_file_or_folder(hass, path)
    except Exception as err:
        _LOGGER.error("Failed to delete blueprint %s: %s", filename, err)
        connection.send_error(msg["id"], "delete_failed", f"Failed to delete blueprint {filename}")
        return
    connection.send_result(msg["id"], {"success": True, "filename": filename})

# -----------------------------
# Areas
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_area_button",
    vol.Optional("icon"): str,
    vol.Optional("areaId"): str,
    vol.Optional("floor"): str,
    vol.Optional("disableArea"): bool,
})
async def ws_edit_area_button(hass, connection, msg):
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "areas.yaml"),
        updates={
            "icon": msg.get("icon"),
            "floor": msg.get("floor"),
            "disabled": msg.get("disableArea")
        },
        key=msg["areaId"],
        reload_events=[RELOAD_HOME],
        success_msg="Area button saved"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_area_bool_value",
    vol.Required("areaId"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_area_bool_value(hass, connection, msg):
    key = msg.get("key")
    if not key:
        connection.send_result(msg["id"], {"error": "Missing key"})
        return
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "areas.yaml"),
        updates={key: msg.get("value")},
        key=msg["areaId"],
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Area bool value set successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_area_button",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_area_button(hass, connection, msg):
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return
    areas = await async_load_yaml(hass, config_path(hass, "areas.yaml"))
    for num, area_id in enumerate(sort_data, start=1):
        areas.setdefault(area_id, OrderedDict())[msg["sortType"]] = num
    await async_save_yaml(hass, config_path(hass, "areas.yaml"), areas)
    connection.send_result(msg["id"], {"successful": "Area buttons sorted successfully"})

# -----------------------------
# Devices
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_button",
    vol.Optional("icon"): str,
    vol.Optional("device"): str,
    vol.Optional("showInNavbar"): bool,
})
async def ws_edit_device_button(hass, connection, msg):
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "devices.yaml"),
        updates={
            "icon": msg.get("icon"),
            "show_in_navbar": msg.get("showInNavbar")
        },
        key=msg["device"],
        reload_events=[RELOAD_DEVICES, "dwains_dashboard_navigation_card_reload"],
        success_msg="Device button saved"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_card",
    vol.Required("cardData"): str,
    vol.Required("domain"): str,
})
async def ws_edit_device_card(hass, connection, msg):
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return
    try:
        card_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid card data")
        return
    filepath = config_path(hass, "cards/devices_card", f"{domain}.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates=card_data,
        reload_events=[RELOAD_DEVICES],
        success_msg="Device card saved successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_device_card",
    vol.Required("domain"): str,
})
async def ws_remove_device_card(hass, connection, msg):
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return
    filepath = config_path(hass, "cards/devices_card", f"{domain}.yaml")
    await async_remove_file_or_folder(hass, filepath)
    hass.bus.async_fire(RELOAD_DEVICES)
    connection.send_result(msg["id"], {"successful": "Device card removed successfully"})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_popup",
    vol.Required("cardData"): str,
    vol.Required("domain"): str,
})
async def ws_edit_device_popup(hass, connection, msg):
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return
    try:
        popup_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid card data")
        return
    filepath = config_path(hass, "cards/devices_popup", f"{domain}.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates=popup_data,
        reload_events=["dwains_dashboard_reload"],
        success_msg="Device popup saved successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_device_popup",
    vol.Required("domain"): str,
})
async def ws_remove_device_popup(hass, connection, msg):
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return
    filepath = config_path(hass, "cards/devices_popup", f"{domain}.yaml")
    await async_remove_file_or_folder(hass, filepath)
    hass.bus.async_fire("dwains_dashboard_reload")
    connection.send_result(msg["id"], {"successful": "Device popup removed successfully"})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_bool_value",
    vol.Required("device"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_device_bool_value(hass, connection, msg):
    key = msg.get("key")
    if not key:
        connection.send_result(msg["id"], {"error": "Missing key"})
        return
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "devices.yaml"),
        updates={key: msg.get("value")},
        key=msg["device"],
        reload_events=[RELOAD_DEVICES],
        success_msg="Device bool value set successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_device_button",
    vol.Required("sortData"): str,
})
async def ws_sort_device_button(hass, connection, msg):
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return
    devices = await async_load_yaml(hass, config_path(hass, "devices.yaml"))
    for num, device_id in enumerate(sort_data, start=1):
        devices.setdefault(device_id, OrderedDict())["sort_order"] = num
    await async_save_yaml(hass, config_path(hass, "devices.yaml"), devices)
    connection.send_result(msg["id"], {"successful": "Device buttons sorted successfully"})

# -----------------------------
# Entities
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity",
    vol.Required("entity"): str,
    vol.Optional("friendlyName"): str,
    vol.Optional("disableEntity"): bool,
    vol.Optional("hideEntity"): bool,
    vol.Optional("excludeEntity"): bool,
    vol.Optional("rowSpan"): str,
    vol.Optional("colSpan"): str,
    vol.Optional("rowSpanLg"): str,
    vol.Optional("colSpanLg"): str,
    vol.Optional("rowSpanXl"): str,
    vol.Optional("colSpanXl"): str,
    vol.Optional("customCard"): bool,
    vol.Optional("customPopup"): bool,
})
async def ws_edit_entity(hass, connection, msg):
    updates = {
        "hidden": msg.get("hideEntity"),
        "excluded": msg.get("excludeEntity"),
        "disabled": msg.get("disableEntity"),
        "friendly_name": msg.get("friendlyName"),
        "col_span": msg.get("colSpan"),
        "row_span": msg.get("rowSpan"),
        "col_span_lg": msg.get("colSpanLg"),
        "row_span_lg": msg.get("rowSpanLg"),
        "col_span_xl": msg.get("colSpanXl"),
        "row_span_xl": msg.get("rowSpanXl"),
        "custom_card": msg.get("customCard"),
        "custom_popup": msg.get("customPopup")
    }
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=updates,
        key=msg["entity"],
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entity saved"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_card",
    vol.Required("cardData"): str,
    vol.Required("entityId"): str,
})
async def ws_edit_entity_card(hass, connection, msg):
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return
    try:
        card_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid card data")
        return
    card_file = config_path(hass, "cards/entities", f"{entity_id}.yaml")

    await handle_ws_yaml_update(
        hass, connection, msg, card_file,
        updates=card_data,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Card added successfully"
    )

    # Enable custom card in entities.yaml
    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_card"] = True
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES]
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_popup",
    vol.Required("cardData"): str,
    vol.Required("entityId"): str,
})
async def ws_edit_entity_popup(hass, connection, msg):
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return
    try:
        popup_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid card data")
        return
    popup_file = config_path(hass, "cards/entities_popup", f"{entity_id}.yaml")

    await handle_ws_yaml_update(
        hass, connection, msg, popup_file,
        updates=popup_data,
        reload_events=["dwains_dashboard_reload"],
        success_msg="Popup added successfully"
    )

    # Enable custom popup in entities.yaml
    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_popup"] = True
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=["dwains_dashboard_reload"]
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_favorite",
    vol.Required("entityId"): str,
    vol.Optional("favorite"): bool,
})
async def ws_edit_entity_favorite(hass, connection, msg):
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return
    favorite_value = msg.get("favorite", False)

    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["favorite"] = favorite_value
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=[RELOAD_HOME]
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_bool_value",
    vol.Required("entityId"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_entity_bool_value(hass, connection, msg):
    key = msg.get("key")
    if not key:
        connection.send_result(msg["id"], {"error": "Missing key"})
        return
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates={key: msg.get("value")},
        key=msg["entityId"],
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entity bool value set successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entities_bool_value",
    vol.Required("entities"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_entities_bool_value(hass, connection, msg):
    entities_file = config_path(hass, "entities.yaml")
    try:
        entities_input = json.loads(msg.get("entities", "[]"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return
    key = msg.get("key")
    value = msg.get("value")
    if not key:
        connection.send_result(msg["id"], {"error": "Missing key"})
        return

    def update_entities(data):
        for entity_id in entities_input:
            data.setdefault(entity_id, OrderedDict())[key] = value
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, entities_file,
        updates=update_entities,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entities bool value set successfully"
    )

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_entity",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_entity(hass, connection, msg):
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return
    entities = await async_load_yaml_file(hass, config_path(hass, "entities.yaml"))
    for num, entity_id in enumerate(sort_data, start=1):
        entities.setdefault(entity_id, OrderedDict())[msg["sortType"]] = num
    await async_save_yaml(hass, config_path(hass, "entities.yaml"), entities)
    connection.send_result(msg["id"], {"successful": "Entity cards sorted successfully"})

# -----------------------------
# Cards
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}add_card",
    vol.Optional("card_data"): str,
    vol.Optional("area_id"): str,
    vol.Optional("domain"): str,
    vol.Optional("position"): str,
    vol.Optional("filename"): str,
    vol.Optional("page"): str,
    vol.Optional("rowSpan"): str,
    vol.Optional("colSpan"): str,
    vol.Optional("rowSpanLg"): str,
    vol.Optional("colSpanLg"): str,
    vol.Optional("rowSpanXl"): str,
    vol.Optional("colSpanXl"): str,
})
async def ws_add_card(hass, connection, msg):
    """Handle adding a new card."""
    try:
        card_data = json.loads(msg.get("card_data", "{}"))
        filename = msg.get("filename") or card_data.get("type")
        page = msg.get("page")

        if not filename or not page:
            connection.send_result(msg["id"], {"error": "Missing card type or page"})
            return

        # Add layout/position metadata
        for key, yaml_key in [
            ("rowSpan", "row_span"),
            ("colSpan", "col_span"),
            ("rowSpanLg", "row_span_lg"),
            ("colSpanLg", "col_span_lg"),
            ("rowSpanXl", "row_span_xl"),
            ("colSpanXl", "col_span_xl"),
            ("position", "position")
        ]:
            card_data[yaml_key] = msg.get(key, card_data.get(yaml_key))

        # Determine folder path
        if page == "areas":
            area_id = msg.get("area_id")
            if not area_id:
                connection.send_result(msg["id"], {"error": "Missing area_id"})
                return
            base_path = config_path(hass, "cards/areas", area_id)
        elif page == "devices":
            domain = msg.get("domain")
            if not domain:
                connection.send_result(msg["id"], {"error": "Missing domain"})
                return
            base_path = config_path(hass, "cards/devices", domain)
        else:
            connection.send_result(msg["id"], {"error": f"Unknown page: {page}"})
            return

        # Ensure folder exists
        await hass.async_add_executor_job(os.makedirs, base_path, True)

        # Determine final filename path
        filename_path = os.path.join(base_path, f"{filename}.yaml")
        exists = await hass.async_add_executor_job(os.path.exists, filename_path)
        if exists:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename_path = os.path.join(base_path, f"{filename}_{timestamp}.yaml")

        await handle_ws_yaml_update(
            hass, connection, msg, filename_path,
            updates=card_data,
            reload_events=[RELOAD_HOME, RELOAD_DEVICES],
            success_msg="Card added successfully"
        )

    except Exception as e:
        _LOGGER.error("Failed to add card: %s", e)
        connection.send_error(msg["id"], "add_card_failed", str(e))

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_card",
    vol.Optional("area_id"): str,
    vol.Optional("domain"): str,
    vol.Optional("filename"): str,
    vol.Optional("page"): str,
})
async def ws_remove_card(hass, connection, msg):
    """Handle removing a card YAML file."""
    try:
        filename = msg.get("filename")
        page = msg.get("page")

        if not filename or not page:
            connection.send_result(msg["id"], {"error": "Missing filename or page"})
            return

        if page == "areas":
            area_id = msg.get("area_id")
            if not area_id:
                connection.send_result(msg["id"], {"error": "Missing area_id"})
                return
            base_path = config_path(hass, "cards/areas", area_id)
        elif page == "devices":
            domain = msg.get("domain")
            if not domain:
                connection.send_result(msg["id"], {"error": "Missing domain"})
                return
            base_path = config_path(hass, "cards/devices", domain)
        else:
            connection.send_result(msg["id"], {"error": f"Unknown page: {page}"})
            return

        filename_path = os.path.join(base_path, f"{filename}.yaml")
        await async_remove_file_or_folder(hass, filename_path)

        hass.bus.async_fire(RELOAD_HOME)
        hass.bus.async_fire(RELOAD_DEVICES)
        connection.send_result(msg["id"], {"successful": "Card removed successfully"})

    except Exception as e:
        _LOGGER.error("Failed to remove card: %s", e)
        connection.send_error(msg["id"], "remove_card_failed", str(e))

# -----------------------------
# More Pages
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_more_page",
    vol.Optional("card_data"): str,
    vol.Optional("foldername"): str,
    vol.Optional("name"): str,
    vol.Optional("icon"): str,
    vol.Optional("showInNavbar"): bool,
})
async def ws_edit_more_page(hass, connection, msg):
    more_page_folder = msg.get("foldername") or slugify(msg.get("name", "new_page"))
    base_path = config_path(hass, "more_pages", more_page_folder)
    page_file = os.path.join(base_path, "page.yaml")
    config_file = os.path.join(base_path, "config.yaml")

    if not msg.get("foldername") and os.path.exists(page_file) and os.stat(page_file).st_size != 0:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        more_page_folder += timestamp
        base_path = config_path(hass, "more_pages", more_page_folder)
        page_file = os.path.join(base_path, "page.yaml")
        config_file = os.path.join(base_path, "config.yaml")

    await hass.async_add_executor_job(os.makedirs, base_path, True)

    try:
        page_data = json.loads(msg.get("card_data", "{}"))
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return
    await async_save_yaml(hass, page_file, page_data)

    config_data = {
        "name": msg.get("name"),
        "icon": msg.get("icon"),
        "show_in_navbar": msg.get("showInNavbar", True)
    }
    await async_save_yaml(hass, config_file, config_data)

    hass.bus.async_fire("dwains_dashboard_reload")
    hass.bus.async_fire("dwains_dashboard_navigation_card_reload")
    await reload_configuration(hass)
    connection.send_result(msg["id"], {"successful": "More page saved successfully"})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_more_page",
    vol.Required("foldername"): str,
})
async def ws_remove_more_page(hass, connection, msg):
    foldername = msg.get("foldername")
    if not foldername:
        connection.send_result(msg["id"], {"error": "Missing foldername"})
        return

    base_path = config_path(hass, "more_pages", foldername)
    page_file = os.path.join(base_path, "page.yaml")

    if await hass.async_add_executor_job(os.path.exists, page_file):
        await hass.async_add_executor_job(shutil.rmtree, base_path, True)

    hass.bus.async_fire("dwains_dashboard_navigation_card_reload")
    hass.bus.async_fire("dwains_dashboard_reload")
    await reload_configuration(hass)

    connection.send_result(msg["id"], {"successful": "More page removed successfully"})

# -----------------------------
# Sorting
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_area_button",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_area_button(hass, connection, msg):
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return

    areas = await async_load_yaml(hass, config_path(hass, "areas.yaml"))
    for num, area_id in enumerate(sort_data, start=1):
        areas.setdefault(area_id, OrderedDict())[msg["sortType"]] = num
    await async_save_yaml(hass, config_path(hass, "areas.yaml"), areas)
    connection.send_result(msg["id"], {"successful": "Area buttons sorted successfully"})

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_device_button",
    vol.Required("sortData"): str,
})
async def ws_sort_device_button(hass, connection, msg):
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return

    devices = await async_load_yaml(hass, config_path(hass, "devices.yaml"))
    for num, device_id in enumerate(sort_data, start=1):
        devices.setdefault(device_id, OrderedDict())["sort_order"] = num
    await async_save_yaml(hass, config_path(hass, "devices.yaml"), devices)
    connection.send_result(msg["id"], {"successful": "Device buttons sorted successfully"})

# -----------------------------
# Entity sorting
# -----------------------------

@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_entity",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_entity(hass, connection, msg):
    """Handle sorting entity cards."""
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        connection.send_error(msg["id"], "invalid_json", "Invalid sort data")
        return

    entities = await async_load_yaml_file(hass, config_path(hass, "entities.yaml"))
    for num, entity_id in enumerate(sort_data, start=1):
        entities.setdefault(entity_id, OrderedDict())[msg["sortType"]] = num

    await async_save_yaml(hass, config_path(hass, "entities.yaml"), entities)
    connection.send_result(msg["id"], {"successful": "Entity cards sorted successfully"})

# End of module
