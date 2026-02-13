"""
Shared WebSocket helpers for Dashboard.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Mapping, Callable

from homeassistant.core import HomeAssistant

from ..utils import async_load_yaml, async_save_yaml, handle_ws_yaml_update

def ws_send_success(connection, msg_id: int, message: str = "Success") -> None:
    """Send standardized success response."""
    connection.send_result(msg_id, {"successful": message})

def ws_send_error(connection, msg_id: int, code: str, message: str) -> None:
    """Send standardized error response."""
    connection.send_error(msg_id, code, message)
    
# ------------------------------------------------------------------
# JSON helpers
# ------------------------------------------------------------------

def ws_safe_json_load(
    connection,
    msg: Mapping[str, Any],
    key: str,
    default: str = "{}",
):
    """Safely load JSON from websocket message."""
    try:
        return json.loads(msg.get(key, default))
    except json.JSONDecodeError:
        ws_send_error(
            connection,
            msg["id"],
            "invalid_json",
            f"Invalid JSON in '{key}'",
        )
        return None


# ------------------------------------------------------------------
# Generic YAML Sorting
# ------------------------------------------------------------------

async def ws_sort_yaml(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
    yaml_file: str,
    sort_key: str,
) -> None:
    """Generic YAML sorting handler."""

    if "sortData" not in msg:
        ws_send_error(connection, msg["id"], "invalid_format", "Missing sortData")
        return

    order = ws_safe_json_load(connection, msg, "sortData")
    if order is None:
        return

    yaml_data = await async_load_yaml(hass, yaml_file) or {}

    for index, item_id in enumerate(order, start=1):
        yaml_data.setdefault(item_id, OrderedDict())[sort_key] = index

    await async_save_yaml(hass, yaml_file, yaml_data)
    ws_send_success(connection, msg["id"], "Sorted successfully")


# ------------------------------------------------------------------
# Generic YAML Edit Command Factory
# ------------------------------------------------------------------

def ws_yaml_edit_command(
    *,
    ws_type: str,
    yaml_path: Callable[[HomeAssistant], str],
    key_field: str | None = None,
    updates_map: dict[str, str] | None = None,
    reload_events: list[str] | None = None,
    success_msg: str = "Saved",
):

    reload_events = reload_events or []

    from homeassistant.components import websocket_api

    @websocket_api.async_response
    @websocket_api.websocket_command({ "type": ws_type })
    async def handler(hass: HomeAssistant, connection, msg: Mapping[str, Any]):
        updates = {}

        # Map message keys to YAML keys
        if updates_map:
            for yaml_key, msg_key in updates_map.items():
                if msg_key in msg:
                    updates[yaml_key] = msg[msg_key]

        # Handle update using shared utils
        try:
            await handle_ws_yaml_update(
                hass,
                connection,
                msg,
                yaml_path(hass),
                updates=updates,
                key=msg.get(key_field) if key_field else None,
                reload_events=reload_events,
                success_msg=success_msg,
            )
        except Exception as err:
            ws_send_error(connection, msg["id"], "yaml_edit_error", str(err))

    return handler
