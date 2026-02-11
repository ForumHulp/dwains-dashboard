import os
import json
import logging
from datetime import datetime
from typing import Mapping, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import WS_PREFIX, RELOAD_HOME, RELOAD_DEVICES
from ..utils import config_path, async_save_yaml, async_remove_file_or_folder
from .helpers import ws_send_success, ws_send_error, handle_ws_yaml_update

_LOGGER = logging.getLogger(__name__)

# -----------------------------
# Add Card
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
    """Add or update a card YAML file, overwrite if it exists."""
    try:
        card_data = json.loads(msg.get("card_data", "{}"))
        card_type = card_data.get("type", "default")
        filename = msg.get("filename") or f"custom_{card_type}"
        page = msg.get("page")

        if not filename or not page:
            return ws_send_error(connection, msg, "missing_data", "Missing card type or page")

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
                return ws_send_error(connection, msg, "missing_area", "Missing area_id")
            base_path = config_path(hass, "cards/areas", area_id)
        elif page == "devices":
            domain = msg.get("domain")
            if not domain:
                return ws_send_error(connection, msg, "missing_domain", "Missing domain")
            base_path = config_path(hass, "cards/devices", domain)
        else:
            return ws_send_error(connection, msg, "unknown_page", f"Unknown page: {page}")

        # Ensure folder exists (fixed)
        await hass.async_add_executor_job(lambda: os.makedirs(base_path, exist_ok=True))

        # Final file path
        filename_path = os.path.join(base_path, f"{filename}.yaml")

        # Overwrite or create
        await handle_ws_yaml_update(
            hass, connection, msg, filename_path,
            updates=card_data,
            reload_events=[RELOAD_HOME, RELOAD_DEVICES],
            success_msg="Card added or updated successfully"
        )

    except Exception as e:
        _LOGGER.error("Failed to add/update card: %s", e)
        return ws_send_error(connection, msg, "add_card_failed", str(e))


# -----------------------------
# Remove Card
# -----------------------------
@websocket_api.async_response
@websocket_api.websocket_command({
    vol.Required("type"): f"{WS_PREFIX}remove_card",
    vol.Optional("area_id"): str,
    vol.Optional("domain"): str,
    vol.Optional("filename"): str,
    vol.Optional("page"): str,
})
async def ws_remove_card(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
    """Remove a card YAML file from dashboard."""
    try:
        filename = msg.get("filename")
        page = msg.get("page")

        if not filename or not page:
            return ws_send_error(connection, msg, "missing_data", "Missing filename or page")

        if page == "areas":
            area_id = msg.get("area_id")
            if not area_id:
                return ws_send_error(connection, msg, "missing_area", "Missing area_id")
            base_path = config_path(hass, "cards/areas", area_id)
        elif page == "devices":
            domain = msg.get("domain")
            if not domain:
                return ws_send_error(connection, msg, "missing_domain", "Missing domain")
            base_path = config_path(hass, "cards/devices", domain)
        else:
            return ws_send_error(connection, msg, "unknown_page", f"Unknown page: {page}")

        filename_path = os.path.join(base_path, f"{filename}.yaml")
        await async_remove_file_or_folder(hass, filename_path)

        # Fire reload events
        hass.bus.async_fire(RELOAD_HOME)
        hass.bus.async_fire(RELOAD_DEVICES)

        ws_send_success(connection, msg, "Card removed successfully")

    except Exception as e:
        _LOGGER.error("Failed to remove card: %s", e)
        ws_send_error(connection, msg, "remove_card_failed", str(e))