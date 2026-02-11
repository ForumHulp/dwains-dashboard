"""
WebSocket commands for Dwains Dashboard blueprints.
"""

import os
import logging
from typing import Any, Mapping

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api

from ..const import WS_PREFIX
from ..utils import async_save_yaml, async_load_yaml_file, async_remove_file_or_folder
from .helpers import ws_send_success, ws_send_error, ws_safe_json_load

_LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Get installed blueprints
# ------------------------------------------------------------------
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): f"{WS_PREFIX}get_blueprints"})
async def ws_get_blueprints(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Return all installed blueprints."""
    blueprints_dir = hass.config.path("dwains-dashboard/blueprints")
    blueprints = {}

    if not os.path.isdir(blueprints_dir):
        ws_send_success(connection, msg["id"], {"blueprints": blueprints})
        return

    try:
        for fname in os.listdir(blueprints_dir):
            if not fname.endswith(".yaml"):
                continue
            path = os.path.join(blueprints_dir, fname)
            blueprints[fname] = await async_load_yaml_file(hass, path)
    except Exception as e:
        _LOGGER.error("Failed to load blueprints: %s", e)
        ws_send_error(connection, msg["id"], "load_failed", str(e))
        return

    ws_send_success(connection, msg["id"], {"blueprints": blueprints})


# ------------------------------------------------------------------
# Install a blueprint
# ------------------------------------------------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}install_blueprint",
    vol.Required("filename"): str,
    vol.Required("data"): vol.Any(dict, list),
})
async def ws_install_blueprint(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Install a blueprint."""
    filename = msg["filename"]
    data = msg["data"]
    blueprints_dir = hass.config.path("dwains-dashboard/blueprints")
    os.makedirs(blueprints_dir, exist_ok=True)
    filepath = os.path.join(blueprints_dir, filename)

    try:
        await async_save_yaml(hass, filepath, data)
    except Exception as err:
        _LOGGER.error("Failed to install blueprint %s: %s", filename, err)
        ws_send_error(connection, msg["id"], "install_failed", f"Failed to install {filename}")
        return

    ws_send_success(connection, msg["id"], {"success": True, "filename": filename})


# ------------------------------------------------------------------
# Delete a blueprint
# ------------------------------------------------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}delete_blueprint",
    vol.Required("blueprint"): str,
})
async def ws_delete_blueprint(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Delete a blueprint."""
    filename = msg["blueprint"]
    path = hass.config.path("dwains-dashboard/blueprints", filename)

    try:
        await async_remove_file_or_folder(hass, path)
    except Exception as err:
        _LOGGER.error("Failed to delete blueprint %s: %s", filename, err)
        ws_send_error(connection, msg["id"], "delete_failed", f"Failed to delete {filename}")
        return

    ws_send_success(connection, msg["id"], {"success": True, "filename": filename})
