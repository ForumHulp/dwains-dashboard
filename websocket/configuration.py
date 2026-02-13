"""
WebSocket configuration commands for Dashboard.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Mapping

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry
from homeassistant.components import websocket_api

from ..const import DOMAIN, VERSION, WS_PREFIX, RELOAD_HOME, RELOAD_DEVICES
from ..utils import config_path, async_load_yaml_file, async_load_yaml_from_dir
from ..process_yaml import reload_configuration
from .helpers import ws_send_success, ws_send_error, ws_safe_json_load, ws_yaml_edit_command

# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

GET_CONFIGURATION_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}configuration/get",
}

GET_VERSION_SCHEMA = {
    vol.Required("type"): f"{WS_PREFIX}get_version",
}

async def get_areas_config(hass):
    area_reg = area_registry.async_get(hass)

    result = {}

    for area in area_reg.async_list_areas():
        result[area.id] = {
            "icon": area.icon or "",
            "floor": area.floor_id or "",
            "disabled": False,
        }

    return result
# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------

@websocket_api.async_response
@websocket_api.websocket_command(GET_CONFIGURATION_SCHEMA)
async def ws_get_configuration(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    """Return full dashboard configuration."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        homepage_header = (
            {k: v for k, v in dict(entries[0].options).items()
             if k not in ("sidepanel_icon", "sidepanel_title")}
            if entries else {}
        )

        more_pages = OrderedDict()
        more_pages_dir = config_path(hass, "more_pages")

        if os.path.isdir(more_pages_dir):
            dirs = await hass.async_add_executor_job(os.listdir, more_pages_dir)
            for folder in dirs:
                cfg = os.path.join(more_pages_dir, folder, "config.yaml")
                page = os.path.join(more_pages_dir, folder, "page.yaml")
                if os.path.exists(cfg) and os.path.exists(page):
                    more_pages[folder] = await async_load_yaml_file(hass, cfg)

        connection.send_result(
            msg["id"],
            {
                "areas": await get_areas_config(hass),
                "entities": await async_load_yaml_file(hass, config_path(hass, "entities.yaml")),
                "devices": await async_load_yaml_file(hass, config_path(hass, "devices.yaml")),
                "area_cards": await async_load_yaml_from_dir(hass, config_path(hass, "cards/areas"), nested=True),
                "device_cards": await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices"), nested=True),
                "entity_cards": await async_load_yaml_from_dir(hass, config_path(hass, "cards/entities"), strip_ext=True),
                "devices_card": await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices_card"), strip_ext=True),
                "entities_popup": await async_load_yaml_from_dir(hass, config_path(hass, "cards/entities_popup"), strip_ext=True),
                "devices_popup": await async_load_yaml_from_dir(hass, config_path(hass, "cards/devices_popup"), strip_ext=True),
                "homepage_header": homepage_header,
                "more_pages": more_pages,
                "installed_version": VERSION,
            },
        )
    except Exception as err:
        ws_send_error(connection, msg["id"], "load_error", f"Failed to get configuration: {err}")


@websocket_api.async_response
@websocket_api.websocket_command(GET_VERSION_SCHEMA)
async def ws_get_version(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
) -> None:
    """Return installed integration version."""
    try:
        ws_send_success(connection, msg["id"], VERSION)
    except Exception as err:
        ws_send_error(connection, msg["id"], "version_error", f"Failed to get version: {err}")


# Areas
ws_edit_area_button = ws_yaml_edit_command(
    ws_type=f"{WS_PREFIX}edit_area_button",
    yaml_path=lambda hass: config_path(hass, "areas.yaml"),
    key_field="areaId",
    updates_map={
        "icon": "icon",
        "floor": "floor",
        "disabled": "disableArea",
    },
    reload_events=[RELOAD_HOME],
    success_msg="Area saved",
)

# Devices
ws_edit_device_button = ws_yaml_edit_command(
    ws_type=f"{WS_PREFIX}edit_device_button",
    yaml_path=lambda hass: config_path(hass, "devices.yaml"),
    key_field="device",
    updates_map={
        "icon": "icon",
        "show_in_navbar": "showInNavbar",
    },
    reload_events=[RELOAD_DEVICES, f"{DOMAIN}_navigation_card_reload"],
    success_msg="Device saved",
)

# Entities
ws_edit_entity = ws_yaml_edit_command(
    ws_type=f"{WS_PREFIX}edit_entity",
    yaml_path=lambda hass: config_path(hass, "entities.yaml"),
    key_field="entity",
    updates_map={
        "hidden": "hideEntity",
        "excluded": "excludeEntity",
        "disabled": "disableEntity",
        "friendly_name": "friendlyName",
        "custom_card": "customCard",
        "custom_popup": "customPopup",
    },
    reload_events=[RELOAD_HOME, RELOAD_DEVICES],
    success_msg="Entity saved",
)