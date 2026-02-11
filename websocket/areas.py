import os
import json
import logging
from collections import OrderedDict
from typing import Mapping, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry

from ..const import WS_PREFIX, RELOAD_HOME, RELOAD_DEVICES
from ..utils import config_path, async_save_yaml
from .helpers import ws_send_success, ws_send_error, handle_ws_yaml_update

_LOGGER = logging.getLogger(__name__)

# -----------------------------
# Edit Area Button
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_area_button",
    vol.Optional("icon"): str,
    vol.Optional("areaId"): str,
    vol.Optional("floor"): str,
    vol.Optional("disableArea"): bool,
})
async def ws_edit_area_button(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit an area button's metadata."""
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "areas.yaml"),
        updates={
            "icon": msg.get("icon"),
            "floor": msg.get("floor"),
            "disabled": msg.get("disableArea")
        },
        key=msg.get("areaId"),
        reload_events=[RELOAD_HOME],
        success_msg="Area button saved"
    )

# -----------------------------
# Edit Area Bool Value
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_area_bool_value",
    vol.Required("areaId"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_area_bool_value(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit a boolean value in areas.yaml."""
    key = msg.get("key")
    if not key:
        return ws_send_error(connection, msg, "Missing key")
    
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "areas.yaml"),
        updates={key: msg.get("value")},
        key=msg.get("areaId"),
        reload_events=[RELOAD_HOME, RELOAD_DEVICES],
        success_msg="Area bool value set successfully"
    )

# -----------------------------
# Sort Area Buttons
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}sort_area_button",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
})
async def ws_sort_area_button(hass, connection, msg: Mapping[str, Any]):
    """Sort Dwain areas by front-end order while keeping all attributes."""
    try:
        sort_data = json.loads(msg["sortData"])
        if not isinstance(sort_data, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        connection.send_message(
            websocket_api.error_message(msg["id"], "invalid_json", "Invalid sort data")
        )
        return

    # Load existing area registry entries
    area_reg = hass.data.get("area_registry_storage")  # or your helper
    if not area_reg:
        from homeassistant.helpers import area_registry
        area_reg = area_registry.async_get(hass)

    # Build a dict keyed by area id containing all existing attributes
    current_areas = {a.id: a for a in area_reg.async_list_areas()}

    # Build new ordered list based on front-end sortData
    new_ordered = []
    for area_id in sort_data:
        if area_id in current_areas:
            new_ordered.append(current_areas[area_id])

    # Append any areas not included in sortData
    for area_id, area in current_areas.items():
        if area_id not in sort_data:
            new_ordered.append(area)

    # Convert AreaEntry objects to dicts suitable for storage/JSON
    def area_to_dict(a):
        return {
            "aliases": list(a.aliases),
            "floor_id": a.floor_id,
            "humidity_entity_id": a.humidity_entity_id,
            "icon": a.icon,
            "id": a.id,
            "labels": list(a.labels),
            "name": a.name,
            "picture": a.picture,
            "temperature_entity_id": a.temperature_entity_id,
            "created_at": a.created_at.isoformat(),
            "modified_at": a.modified_at.isoformat(),
        }

    areas_json_list = [area_to_dict(a) for a in new_ordered]

    # Build final structure like core.area_registry storage
    final_registry = {
        "version": 1,
        "minor_version": 9,
        "key": "core.area_registry",
        "data": {
            "areas": areas_json_list
        }
    }

    # Save to storage file
    store = area_registry.Store(hass, 1, "core.area_registry")
    await store.async_save(final_registry["data"])

    # Respond to frontend
    connection.send_message(
        websocket_api.result_message(msg["id"], "Area buttons sorted successfully")
    )