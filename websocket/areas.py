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
    area_id = msg["areaId"]

    area_reg = area_registry.async_get(hass)
    area = area_reg.async_get_area(area_id)

    if area is None:
        return ws_send_error(connection, msg, "Area not found")

    update_data = {}

    # Update icon
    if "icon" in msg:
        update_data["icon"] = msg["icon"]

    # Update floor (maps to floor_id in registry)
    if "floor" in msg:
        update_data["floor_id"] = msg["floor"]

    if not update_data:
        return ws_send_error(connection, msg, "No valid fields to update")

    area_reg.async_update(area_id, **update_data)

    connection.send_message(
        websocket_api.result_message(
            msg["id"], "Area updated successfully"
        )
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
    """Reorder areas in registry based on frontend order."""

    sort_data = msg["sortData"]

    area_reg = area_registry.async_get(hass)

    # Current areas
    current_areas = {area.id: area for area in area_reg.async_list_areas()}

    reordered = []

    for area_id in sort_data:
        if area_id in current_areas:
            reordered.append(current_areas.pop(area_id))

    reordered.extend(current_areas.values())

    # 🔥 IMPORTANT PART
    # Replace internal data structure
    area_reg.areas = {area.id: area for area in reordered}

    # Schedule save (do NOT await)
    area_reg.async_schedule_save()

    connection.send_message(
        websocket_api.result_message(
            msg["id"], "Area registry reordered successfully"
        )
    )