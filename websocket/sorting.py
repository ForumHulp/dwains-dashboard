from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api

from ..const import WS_PREFIX
from ..utils import config_path
from .helpers import ws_send_success, ws_send_error, ws_safe_json_load, ws_yaml_edit_command

SORT_AREA_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}sort_area_button",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
}

SORT_DEVICE_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}sort_device_button",
    vol.Required("sortData"): str,
}

SORT_ENTITY_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}sort_entity",
    vol.Required("sortData"): str,
    vol.Required("sortType"): str,
}


@websocket_api.async_response
@websocket_api.websocket_command(SORT_AREA_SCHEMA)
async def ws_sort_area(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    await ws_sort_yaml(
        hass,
        connection,
        msg,
        config_path(hass, "areas.yaml"),
        msg["sortType"],
    )


@websocket_api.async_response
@websocket_api.websocket_command(SORT_DEVICE_SCHEMA)
async def ws_sort_device(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    await ws_sort_yaml(
        hass,
        connection,
        msg,
        config_path(hass, "devices.yaml"),
        "sort_order",
    )


@websocket_api.async_response
@websocket_api.websocket_command(SORT_ENTITY_SCHEMA)
async def ws_sort_entity(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    await ws_sort_yaml(
        hass,
        connection,
        msg,
        config_path(hass, "entities.yaml"),
        msg["sortType"],
    )
