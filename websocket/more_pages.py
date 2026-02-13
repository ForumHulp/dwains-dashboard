"""
WebSocket commands for managing Dashboard 'More Pages'.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Mapping

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api
from homeassistant.util import slugify

from ..const import DOMAIN, WS_PREFIX, RELOAD_HOME, RELOAD_DEVICES
from ..utils import config_path, async_remove_file_or_folder, async_save_yaml
from ..process_yaml import reload_configuration
from .helpers import ws_send_success, ws_send_error, ws_safe_json_load, ws_yaml_edit_command

EDIT_MORE_PAGE_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}edit_more_page",
    vol.Optional("card_data"): str,
    vol.Optional("foldername"): str,
    vol.Optional("name"): str,
    vol.Optional("icon"): str,
    vol.Optional("showInNavbar"): bool,
}

REMOVE_MORE_PAGE_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}remove_more_page",
    vol.Required("foldername"): str,
}

# Use ws_yaml_edit_command for editing/creating more pages
def ws_edit_more_page_factory():
    async def yaml_path(hass: HomeAssistant) -> str:
        """
        Determine folder and return base path for page.yaml/config.yaml.
        This path will be used by ws_yaml_edit_command for saving.
        """
        # Get folder or generate from name
        folder = msg.get("foldername") or slugify(msg.get("name", "new_page"))
        base_path = config_path(hass, "more_pages", folder)

        # If creating new and folder exists, append timestamp
        if not msg.get("foldername") and os.path.exists(base_path):
            folder += datetime.now().strftime("%Y%m%d%H%M%S")
            base_path = config_path(hass, "more_pages", folder)

        os.makedirs(base_path, exist_ok=True)
        return base_path

    async def handler(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
        # Load card_data
        page_data = ws_safe_json_load(connection, msg, "card_data")
        if page_data is None:
            return

        folder = msg.get("foldername") or slugify(msg.get("name", "new_page"))
        base_path = config_path(hass, "more_pages", folder)
        os.makedirs(base_path, exist_ok=True)

        # Save YAML files
        from ..utils import async_save_yaml

        await async_save_yaml(hass, os.path.join(base_path, "page.yaml"), page_data)
        await async_save_yaml(
            hass,
            os.path.join(base_path, "config.yaml"),
            {
                "name": msg.get("name"),
                "icon": msg.get("icon"),
                "show_in_navbar": msg.get("showInNavbar", True),
            },
        )

        # Reload events
        #hass.bus.async_fire("{{ DOMAIN }}.reload")
        await hass.services.async_call(DOMAIN, "reload")
        hass.bus.async_fire(f"{DOMAIN}.navigation_card_reload")
        await reload_configuration(hass)

        ws_send_success(connection, msg["id"], "More page saved")

    # Return handler wrapped as websocket command
    from homeassistant.components import websocket_api
    return websocket_api.async_response(
        websocket_api.websocket_command(EDIT_MORE_PAGE_SCHEMA)(handler)
    )

ws_edit_more_page = ws_edit_more_page_factory()





@websocket_api.async_response
@websocket_api.websocket_command(REMOVE_MORE_PAGE_SCHEMA)
async def ws_remove_more_page(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    """Remove a 'More Page'."""
    try:
        await async_remove_file_or_folder(
            hass,
            config_path(hass, "more_pages", msg["foldername"]),
        )

        hass.bus.async_fire(RELOAD_EVENT)
        hass.bus.async_fire(RELOAD_NAV_EVENT)
        await reload_configuration(hass)

        ws_send_success(connection, msg["id"], "More page removed")
    except Exception as err:
        ws_send_error(connection, msg["id"], "remove_more_page_error", str(err))
