import os
import json
import logging
from collections import OrderedDict
from typing import Mapping, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import WS_PREFIX, RELOAD_HOME, RELOAD_DEVICES
from ..utils import config_path, async_save_yaml
from .helpers import ws_send_success, ws_send_error, handle_ws_yaml_update

_LOGGER = logging.getLogger(__name__)

# -----------------------------
# Edit Entity Metadata
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
async def ws_edit_entity(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit entity metadata."""
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
        "custom_popup": msg.get("customPopup"),
    }
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=updates,
        key=msg["entity"],
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entity saved"
    )

# -----------------------------
# Edit Entity Card
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_card",
    vol.Required("cardData"): str,
    vol.Required("entityId"): str,
})
async def ws_edit_entity_card(hass, connection, msg):
    """Update existing entity card YAML instead of creating a new one."""
    entity_id = msg.get("entityId")
    if not entity_id:
        return ws_send_error(connection, msg, "missing_entity", "Missing entityId")

    try:
        card_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid card data")

    card_file = config_path(hass, "cards/entities", f"{entity_id}.yaml")

    # Always overwrite existing file
    await handle_ws_yaml_update(
        hass, connection, msg, card_file,
        updates=card_data,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Card updated successfully"
    )

    # Make sure the entity YAML marks it as custom_card
    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_card"] = True
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES]
    )

# -----------------------------
# Edit Entity Popup
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_popup",
    vol.Required("cardData"): str,
    vol.Required("entityId"): str,
})
async def ws_edit_entity_popup(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit entity popup YAML."""
    entity_id = msg.get("entityId")
    if not entity_id:
        return ws_send_error(connection, msg, "Missing entityId")

    try:
        popup_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid card data")

    popup_file = config_path(hass, "cards/entities_popup", f"{entity_id}.yaml")

    await handle_ws_yaml_update(
        hass, connection, msg, popup_file,
        updates=popup_data,
        reload_events=["dwains_dashboard_reload"],
        success_msg="Entity popup saved successfully"
    )

    # Enable custom popup flag in entities.yaml
    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_popup"] = True
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=["dwains_dashboard_reload"]
    )

# -----------------------------
# Edit Entity Favorite
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_favorite",
    vol.Required("entityId"): str,
    vol.Optional("favorite"): bool,
})
async def ws_edit_entity_favorite(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    entity_id = msg.get("entityId")
    if not entity_id:
        return ws_send_error(connection, msg, "Missing entityId")

    favorite_value = msg.get("favorite", False)

    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["favorite"] = favorite_value
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=[RELOAD_HOME]
    )

# -----------------------------
# Edit Entity Bool Value
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entity_bool_value",
    vol.Required("entityId"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_entity_bool_value(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    key = msg.get("key")
    if not key:
        return ws_send_error(connection, msg, "Missing key")

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates={key: msg.get("value")},
        key=msg.get("entityId"),
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entity bool value set successfully"
    )

# -----------------------------
# Edit Multiple Entities Bool Value
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_entities_bool_value",
    vol.Required("entities"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_entities_bool_value(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    try:
        entities_input = json.loads(msg.get("entities", "[]"))
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid entities data")

    key = msg.get("key")
    value = msg.get("value")
    if not key:
        return ws_send_error(connection, msg, "Missing key")

    def update_entities(data):
        for entity_id in entities_input:
            data.setdefault(entity_id, OrderedDict())[key] = value
        return data

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "entities.yaml"),
        updates=update_entities,
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Entities bool value set successfully"
    )

# -----------------------------
# Sort Entity Cards
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_entity",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_entity(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Handle sorting entity cards."""
    try:
        sort_data = json.loads(msg["sortData"])
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid sort data")

    entities = await handle_ws_yaml_update(hass, connection, msg, config_path(hass, "entities.yaml"), dry_run=True)
    if entities is None:
        entities = OrderedDict()

    for num, entity_id in enumerate(sort_data, start=1):
        entities.setdefault(entity_id, OrderedDict())[msg["sortType"]] = num

    await async_save_yaml(hass, config_path(hass, "entities.yaml"), entities)
    ws_send_success(connection, msg, "Entity cards sorted successfully")
