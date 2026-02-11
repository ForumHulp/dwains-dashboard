import os
import json
import logging
from collections import OrderedDict
from typing import Mapping, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import WS_PREFIX, RELOAD_DEVICES
from ..utils import (
    config_path,
    async_save_yaml,
    async_remove_file_or_folder,
)
from .helpers import ws_send_success, ws_send_error, handle_ws_yaml_update

_LOGGER = logging.getLogger(__name__)

# -----------------------------
# Edit Device Button
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_button",
    vol.Optional("icon"): str,
    vol.Optional("device"): str,
    vol.Optional("showInNavbar"): bool,
})
async def ws_edit_device_button(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit device button metadata."""
    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "devices.yaml"),
        updates={
            "icon": msg.get("icon"),
            "show_in_navbar": msg.get("showInNavbar")
        },
        key=msg.get("device"),
        reload_events=[RELOAD_DEVICES, "dwains_dashboard_navigation_card_reload"],
        success_msg="Device button saved"
    )

# -----------------------------
# Edit Device Card
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_card",
    vol.Required("cardData"): str,
    vol.Required("domain"): str,
})
async def ws_edit_device_card(hass, connection, msg):
    """Update existing device card YAML instead of creating a new one."""
    domain = msg.get("domain")
    if not domain:
        return ws_send_error(connection, msg, "missing_domain", "Missing domain")

    try:
        card_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid card data")

    card_file = config_path(hass, "cards/devices_card", f"{domain}.yaml")

    await handle_ws_yaml_update(
        hass, connection, msg, card_file,
        updates=card_data,
        reload_events=[RELOAD_DEVICES],
        success_msg="Device card updated successfully"
    )

# -----------------------------
# Remove Device Card
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_device_card",
    vol.Required("domain"): str,
})
async def ws_remove_device_card(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Remove device card YAML file."""
    domain = msg.get("domain")
    if not domain:
        return ws_send_error(connection, msg, "Missing domain")

    filepath = config_path(hass, "cards/devices_card", f"{domain}.yaml")
    await async_remove_file_or_folder(hass, filepath)
    hass.bus.async_fire(RELOAD_DEVICES)
    ws_send_success(connection, msg, "Device card removed successfully")

# -----------------------------
# Edit Device Popup
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_popup",
    vol.Required("cardData"): str,
    vol.Required("domain"): str,
})
async def ws_edit_device_popup(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit device popup YAML."""
    domain = msg.get("domain")
    if not domain:
        return ws_send_error(connection, msg, "Missing domain")

    try:
        popup_data = json.loads(msg.get("cardData", "{}"))
    except json.JSONDecodeError:
        return ws_send_error(connection, msg, "invalid_json", "Invalid popup data")

    filepath = config_path(hass, "cards/devices_popup", f"{domain}.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates=popup_data,
        reload_events=["dwains_dashboard_reload"],
        success_msg="Device popup saved successfully"
    )

# -----------------------------
# Remove Device Popup
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_device_popup",
    vol.Required("domain"): str,
})
async def ws_remove_device_popup(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Remove device popup YAML."""
    domain = msg.get("domain")
    if not domain:
        return ws_send_error(connection, msg, "Missing domain")

    filepath = config_path(hass, "cards/devices_popup", f"{domain}.yaml")
    await async_remove_file_or_folder(hass, filepath)
    hass.bus.async_fire("dwains_dashboard_reload")
    ws_send_success(connection, msg, "Device popup removed successfully")

# -----------------------------
# Edit Device Bool Value
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}edit_device_bool_value",
    vol.Required("device"): str,
    vol.Optional("key"): str,
    vol.Optional("value"): bool,
})
async def ws_edit_device_bool_value(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Edit a boolean property for a device."""
    key = msg.get("key")
    if not key:
        return ws_send_error(connection, msg, "Missing key")

    await handle_ws_yaml_update(
        hass, connection, msg, config_path(hass, "devices.yaml"),
        updates={key: msg.get("value")},
        key=msg.get("device"),
        reload_events=[RELOAD_DEVICES],
        success_msg="Device bool value set successfully"
    )
