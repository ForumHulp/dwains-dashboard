import logging
import inspect
import sys
import yaml
import json
import os
import shutil

from .load_plugins import load_plugins
from .load_dashboard import load_dashboard
from .const import DOMAIN, VERSION
from .process_yaml import process_yaml, reload_configuration
from .notifications import async_setup_notifications
from .utils import handle_ws_yaml_update, async_load_yaml_from_dir, async_load_yaml_file
from datetime import datetime

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.config import ConfigType
from homeassistant.components import frontend, websocket_api
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from homeassistant.const import Platform

from collections import OrderedDict
from typing import Any, Mapping, MutableMapping, Optional

from homeassistant.helpers import discovery

from yaml.representer import Representer
import collections
import asyncio

_LOGGER = logging.getLogger(__name__)

areas = OrderedDict()
entities = OrderedDict()
devices = OrderedDict()
homepage_header = OrderedDict()

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the custom integration."""
    # Initialize data store
    hass.data[DOMAIN] = {
        "notifications": {},
        "commands": {},
        "latest_version": ""
    }

    # Automatically register all WebSocket commands defined in this module
    current_module = sys.modules[__name__]
    ws_commands = [
        func
        for name, func in inspect.getmembers(current_module, inspect.isfunction)
        if name.startswith(("ws_handle_", "websocket_"))
    ]

    # Sort commands alphabetically by function name for consistency
    for func in sorted(ws_commands, key=lambda f: f.__name__):
        websocket_api.async_register_command(hass, func)

    # Load plugins and notifications
    await load_plugins(hass, DOMAIN)
    async_setup_notifications(hass)

    return True

yaml.add_representer(collections.OrderedDict, Representer.represent_dict)

@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "dwains_dashboard/configuration/get"})
async def websocket_get_configuration(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Mapping[str, Any],
) -> None:
    """Return a list of configuration."""

    # Initialize all needed variables
    global areas
    global entities
    global devices
    global homepage_header

    areas = await async_load_yaml_file(hass, "dwains-dashboard/configs/areas.yaml")
    entities = await async_load_yaml_file(hass, "dwains-dashboard/configs/entities.yaml")
    devices = await async_load_yaml_file(hass, "dwains-dashboard/configs/devices.yaml")
    homepage_header = await async_load_yaml_file(hass, "dwains-dashboard/configs/settings.yaml")

    # Load card YAMLs
    area_cards = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/areas", nested=True)
    device_cards = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/devices", nested=True)
    entity_cards = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/entities", strip_ext=True)
    devices_card = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/devices_card", strip_ext=True)
    entities_popup = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/entities_popup", strip_ext=True)
    devices_popup = await async_load_yaml_from_dir(hass, "dwains-dashboard/configs/cards/devices_popup", strip_ext=True)

    # Load more_pages (special case: only if both page.yaml & config.yaml exist)
    more_pages = OrderedDict()
    more_pages_dir = hass.config.path("dwains-dashboard/configs/more_pages")
    if os.path.isdir(more_pages_dir):
        subdirs = [
            d for d in await hass.async_add_executor_job(os.listdir, more_pages_dir)
            if os.path.isdir(os.path.join(more_pages_dir, d))
        ]
        for subdir in subdirs:
            config_file = os.path.join(more_pages_dir, subdir, "config.yaml")
            page_file = os.path.join(more_pages_dir, subdir, "page.yaml")
            if os.path.exists(config_file) and os.path.exists(page_file):
                more_pages[subdir] = await async_load_yaml_file(hass, config_file)

    connection.send_result(
        msg["id"],
        {
            "areas": areas,
            "area_cards": area_cards,
            "device_cards": device_cards,
            "entity_cards": entity_cards,
            "entities_popup": entities_popup,
            "entities": entities,
            "devices": devices,
            "homepage_header": homepage_header,
            "more_pages": more_pages,
            "installed_version": VERSION,
            "devices_card": devices_card,
            "devices_popup": devices_popup,
        }
    )

#get_blueprints
#at callback -> websocket_api.async_response
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "dwains_dashboard/get_blueprints"})
async def websocket_get_blueprints(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: Mapping[str, Any],
) -> None:
    """Return a list of installed blueprints asynchronously."""

    blueprints = {}

    blueprints_dir = hass.config.path("dwains-dashboard/blueprints")

    #if os.path.isdir(hass.config.path("dwains-dashboard/blueprints")):
    if await hass.async_add_executor_job(os.path.isdir, blueprints_dir):
        #for fname in os.listdir(hass.config.path("dwains-dashboard/blueprints")):
        file_list = await hass.async_add_executor_job(os.listdir, blueprints_dir)

        for fname in file_list:
            if fname.endswith(".yaml"):
                file_path = os.path.join(blueprints_dir, fname)

                try:
                    # Open the file asynchronously by using async_add_executor_job
                    data = await hass.async_add_executor_job(open, file_path, "r")
                    with data as f:
                        filecontent = yaml.safe_load(f)
                        blueprints[fname] = filecontent

                except Exception as e:
                    _LOGGER.error(f"Error loading blueprint {fname}: {e}")

    connection.send_result(
        msg["id"],
        {
            "blueprints": blueprints,
        }
    )

#install_blueprint
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/install_blueprint",
        vol.Required("yamlCode"): str,
    }
)
@websocket_api.async_response
async def ws_handle_install_blueprint(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle save new blueprint."""

    #PR 817
    #filecontent = yaml.safe_load(json.loads(msg["yamlCode"]))
    filecontent = yaml.safe_load(msg["yamlCode"])

    if not filecontent.get("blueprint"):
        _LOGGER.warning('no blueprint data')
        connection.send_result(
            msg["id"],
            {
                "error": "Blueprint has invalid data"
            },
        )
        return

    if not filecontent.get("card"):
        _LOGGER.warning('no card')
        connection.send_result(
            msg["id"],
            {
                "error": "Blueprint has no card"
            },
        )
        return

    filename = slugify(filecontent["blueprint"]["name"])+".yaml"

    if filecontent.get("button_card_templates"):
        if not os.path.exists(hass.config.path("dwains-dashboard/button_card_templates/blueprints")):
            os.makedirs(hass.config.path("dwains-dashboard/button_card_templates/blueprints"))
        
        #with open(hass.config.path("dwains-dashboard/button_card_templates/blueprints/"+filename), 'w') as f:
        data = await hass.async_add_executor_job(open, hass.config.path("dwains-dashboard/button_card_templates/blueprints/"+filename), "w")
        with data as f:
            yaml.dump(filecontent.get("button_card_templates"), f, default_flow_style=False, sort_keys=False)

        filecontent.pop("button_card_templates")

    if filecontent.get("apexcharts_card_templates"):
        if not os.path.exists(hass.config.path("dwains-dashboard/apexcharts_card_templates/blueprints")):
            os.makedirs(hass.config.path("dwains-dashboard/apexcharts_card_templates/blueprints"))
        
        #with open(hass.config.path("dwains-dashboard/apexcharts_card_templates/blueprints/"+filename), 'w') as f:
        data = await hass.async_add_executor_job(open, hass.config.path("dwains-dashboard/apexcharts_card_templates/blueprints/"+filename), "w")
        with data as f:
            yaml.dump(filecontent.get("apexcharts_card_templates"), f, default_flow_style=False, sort_keys=False)

        filecontent.pop("apexcharts_card_templates")

    if not os.path.exists(hass.config.path("dwains-dashboard/blueprints")):
        os.makedirs(hass.config.path("dwains-dashboard/blueprints"))
    
    #with open(hass.config.path("dwains-dashboard/blueprints/"+filename), 'w') as f:
    data = await hass.async_add_executor_job(open, hass.config.path("dwains-dashboard/blueprints/"+filename), "w")
    with data as f:
        yaml.dump(filecontent, f, default_flow_style=False, sort_keys=False)

    connection.send_result(
        msg["id"],
        {
            "succesfull": filename
        },
    )

#delete_blueprint
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/delete_blueprint",
        vol.Required("blueprint"): str,
    }
)
@websocket_api.async_response
async def ws_handle_delete_blueprint(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle delete blueprint."""
    
    filename = hass.config.path("dwains-dashboard/blueprints/"+msg["blueprint"])

    if os.path.exists(filename):
        os.remove(filename)
    
    connection.send_result(
        msg["id"],
        {
            "succesfull": "Blueprint deleted succesfull"
        },
    )



#edit_area_button
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_area_button",
        vol.Optional("icon"): str,
        vol.Optional("areaId"): str,
        vol.Optional("floor"): str,
        vol.Optional("disableArea"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_area_button(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/areas.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates={
            "icon": msg["icon"],
            "floor": msg["floor"],
            "disabled": msg["disableArea"]
        },
        key=msg["areaId"],
        reload_events=["dwains_dashboard_homepage_card_reload"],
        success_msg="Area button saved"
    )
 
#edit_area_bool_value
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_area_bool_value",
        vol.Required("areaId"): str,
        vol.Optional("key"): str,
        vol.Optional("value"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_area_bool_value(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/areas.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates={msg["key"]: msg["value"]},
        key=msg["areaId"],
        reload_events=["dwains_dashboard_homepage_card_reload", "dwains_dashboard_devicespage_card_reload"],
        success_msg="Area bool value set successfully"
    )

#edit_homepage_header
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_homepage_header",
        vol.Optional("disableClock"): bool,
        vol.Optional("amPmClock"): bool,
        vol.Optional("disableWelcomeMessage"): bool,
        vol.Optional("v2Mode"): bool,
        vol.Optional("disableSensorGraph"): bool,
        vol.Optional("weatherEntity"): str,
        vol.Optional("invertCover"): bool,
        vol.Optional("alarmEntity"): str,

    }
)
@websocket_api.async_response
async def ws_handle_edit_homepage_header(hass, connection, msg):
    """Handle saving editing homepage header."""
    filepath = hass.config.path("dwains-dashboard/configs/settings.yaml")
    updates = {
        "disable_clock": msg["disableClock"],
        "am_pm_clock": msg["amPmClock"],
        "disable_welcome_message": msg["disableWelcomeMessage"],
        "v2_mode": msg["v2Mode"],
        "disable_sensor_graph": msg["disableSensorGraph"],
        "invert_cover": msg["invertCover"],
        "weather_entity": msg["weatherEntity"],
        "alarm_entity": msg["alarmEntity"],
    }

    await handle_ws_yaml_update(
        hass,
        connection,
        msg,
        filepath,
        updates=updates,
        reload_events=["dwains_dashboard_homepage_card_reload"],
        success_msg="Homepage header saved"
    )

#edit_device_button
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_device_button",
        vol.Optional("icon"): str,
        vol.Optional("device"): str,
        vol.Optional("showInNavbar"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_device_button(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/devices.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates={
            "icon": msg["icon"],
            "show_in_navbar": msg["showInNavbar"]
        },
        key=msg["device"],
        reload_events=["dwains_dashboard_devicespage_card_reload", "dwains_dashboard_navigation_card_reload"],
        success_msg="Device button saved"
    )

#edit_device_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_device_card",
        vol.Required("cardData"): str,
        vol.Required("domain"): str,
    }
)
@websocket_api.async_response
async def ws_handle_edit_device_card(hass, connection, msg):
    """Handle saving device card."""
    card_data = json.loads(msg.get("cardData", "{}"))
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return

    filepath = hass.config.path(f"dwains-dashboard/configs/cards/devices_card/{domain}.yaml")

    # Save the card YAML
    await async_save_yaml(hass, filepath, card_data)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Device card saved"})

#remove_device_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_device_card",
        vol.Required("domain"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_device_card(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle removing a device card YAML file."""
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return

    path = hass.config.path("dwains-dashboard/configs/cards/devices_card")
    filename = hass.config.path(path, f"{domain}.yaml")

    # Remove file if exists (async-safe)
    await hass.async_add_executor_job(lambda: os.remove(filename) if os.path.exists(filename) else None)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")
    
    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Device card removed successfully"})

#edit_device_popup
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_device_popup",
        vol.Required("cardData"): str,
        vol.Required("domain"): str,
    }
)
@websocket_api.async_response
async def ws_handle_edit_device_popup(hass, connection, msg):
    """Handle saving a device popup YAML file."""
    card_data = json.loads(msg.get("cardData", "{}"))
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return

    filepath = hass.config.path(f"dwains-dashboard/configs/cards/devices_popup/{domain}.yaml")

    # Save the YAML file (async-safe, ensures folder exists)
    await async_save_yaml(hass, filepath, card_data)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Device popup saved"})

#remove_device_popup
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_device_popup",
        vol.Required("domain"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_device_popup(hass, connection, msg):
    """Handle removing a device popup YAML file."""
    domain = msg.get("domain")
    if not domain:
        connection.send_result(msg["id"], {"error": "Missing domain"})
        return

    filepath = hass.config.path(f"dwains-dashboard/configs/cards/devices_popup/{domain}.yaml")

    # Remove the file (async-safe)
    await async_remove_file_or_folder(hass, filepath)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_reload")
    
    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Device popup removed successfully"})

#remove_entity_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_entity_card",
        vol.Required("entityId"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_entity_card(hass, connection, msg):
    """Handle removing an entity card YAML file."""
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return

    filepath = hass.config.path(f"dwains-dashboard/configs/cards/entities/{entity_id}.yaml")

    # Remove the file (async-safe)
    await async_remove_file_or_folder(hass, filepath)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")
    
    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Entity card removed successfully"})

#remove_entity_popup
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_entity_popup",
        vol.Required("entityId"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_entity_popup(hass, connection, msg):
    """Handle removing an entity popup YAML file."""
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return

    filepath = hass.config.path(f"dwains-dashboard/configs/cards/entities_popup/{entity_id}.yaml")

    # Remove the file (async-safe)
    await async_remove_file_or_folder(hass, filepath)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Entity popup removed successfully"})

#edit_entity
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entity",
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
    }
)
@websocket_api.async_response
async def ws_handle_edit_entity(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/entities.yaml")
    updates = {
        "hidden": msg["hideEntity"],
        "excluded": msg["excludeEntity"],
        "disabled": msg["disableEntity"],
        "friendly_name": msg["friendlyName"],
        "col_span": msg["colSpan"],
        "row_span": msg["rowSpan"],
        "col_span_lg": msg["colSpanLg"],
        "row_span_lg": msg["rowSpanLg"],
        "col_span_xl": msg["colSpanXl"],
        "row_span_xl": msg["rowSpanXl"],
        "custom_card": msg["customCard"],
        "custom_popup": msg["customPopup"]
    }
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates=updates,
        key=msg["entity"],
        reload_events=["dwains_dashboard_homepage_card_reload", "dwains_dashboard_devicespage_card_reload"],
        success_msg="Entity saved"
    )

#edit_entity_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entity_card",
        vol.Required("cardData"): str,
        vol.Required("entityId"): str,
    }
)
@websocket_api.async_response
async def ws_handle_edit_entity_card(hass, connection, msg):
    """Handle editing an entity card and enabling custom card."""
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return

    # Save card YAML
    card_data = json.loads(msg.get("cardData", "{}"))
    card_file = hass.config.path(f"dwains-dashboard/configs/cards/entities/{entity_id}.yaml")
    await handle_ws_yaml_update(hass, card_file, card_data)

    # Update entities.yaml to enable custom_card
    entities_file = hass.config.path("dwains-dashboard/configs/entities.yaml")

    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_card"] = True
        return data

    await handle_ws_yaml_update(hass, entities_file, update_entities, default=OrderedDict)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Card added successfully"})

#edit_entity_popup
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entity_popup",
        vol.Required("cardData"): str,
        vol.Required("entityId"): str,
    }
)
@websocket_api.async_response
async def ws_handle_edit_entity_popup(hass, connection, msg):
    """Handle editing an entity popup and enabling custom popup."""
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return

    # Save popup YAML
    popup_data = json.loads(msg.get("cardData", "{}"))
    popup_file = hass.config.path(f"dwains-dashboard/configs/cards/entities_popup/{entity_id}.yaml")
    await handle_ws_yaml_update(hass, popup_file, popup_data)

    # Update entities.yaml to enable custom_popup
    entities_file = hass.config.path("dwains-dashboard/configs/entities.yaml")

    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["custom_popup"] = True
        return data

    await handle_ws_yaml_update(hass, entities_file, update_entities, default=OrderedDict)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Popup added successfully"})

#edit_entity_favorite
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entity_favorite",
        vol.Required("entityId"): str,
        vol.Optional("favorite"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_entity_favorite(hass, connection, msg):
    """Handle editing the favorite status of an entity."""
    entity_id = msg.get("entityId")
    if not entity_id:
        connection.send_result(msg["id"], {"error": "Missing entityId"})
        return

    favorite_value = msg.get("favorite", False)
    entities_file = hass.config.path("dwains-dashboard/configs/entities.yaml")

    # Use a transform function to update YAML safely
    def update_entities(data):
        data.setdefault(entity_id, OrderedDict())["favorite"] = favorite_value
        return data

    await handle_ws_yaml_update(hass, entities_file, update_entities, default=OrderedDict)

    # Fire reload event
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Favorite status updated successfully"})
 
#edit_entity_bool_value
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entity_bool_value",
        vol.Required("entityId"): str,
        vol.Optional("key"): str,
        vol.Optional("value"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_entity_bool_value(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/entities.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates={msg["key"]: msg["value"]},
        key=msg["entityId"],
        reload_events=["dwains_dashboard_homepage_card_reload", "dwains_dashboard_devicespage_card_reload"],
        success_msg="Entity bool value set successfully"
    )

#edit_entities_bool_value
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_entities_bool_value",
        vol.Required("entities"): str,
        vol.Optional("key"): str,
        vol.Optional("value"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_entities_bool_value(hass, connection, msg):
    """Handle bulk edit of entity bool values."""

    entities_file = hass.config.path("dwains-dashboard/configs/entities.yaml")
    entities_input = json.loads(msg.get("entities", "[]"))
    key = msg.get("key")
    value = msg.get("value")

    if not key:
        connection.send_result(msg["id"], {"error": "Missing key"})
        return

    # Transform function for updating YAML
    def update_entities(data):
        for entity_id in entities_input:
            data.setdefault(entity_id, OrderedDict())[key] = value
        return data

    await handle_ws_yaml_update(hass, entities_file, update_entities, default=OrderedDict)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")

    connection.send_result(msg["id"], {"successful": "Entities bool value set successfully"})

#add_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/add_card",
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

    }
)
@websocket_api.async_response
async def ws_handle_add_card(hass, connection, msg):
    """Handle adding a new card."""
    filename = msg.get("filename")
    card_data = json.loads(msg.get("card_data", "{}"))

    if not filename:
        filename = card_data.get("type")

    if not filename:
        connection.send_result(msg["id"], {"error": "Missing card type or filename"})
        return

    # Add layout/position metadata
    for key in ["col_span", "row_span", "col_span_lg", "row_span_lg", "col_span_xl", "row_span_xl", "position"]:
        card_data[key] = msg.get(key, card_data.get(key))

    # Determine directory path
    page = msg.get("page")
    if page == "areas":
        base_path = hass.config.path(f"dwains-dashboard/configs/cards/areas/{msg.get('area_id')}")
    elif page == "devices":
        base_path = hass.config.path(f"dwains-dashboard/configs/cards/devices/{msg.get('domain')}")
    else:
        connection.send_result(msg["id"], {"error": f"Unknown page: {page}"})
        return

    # Determine filename path
    filename_path = hass.config.path(base_path, f"{filename}.yaml")

    # If no filename provided and file exists, create a timestamped file
    if not msg.get("filename") and os.path.exists(filename_path):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename_path = hass.config.path(base_path, f"{filename}_{timestamp}.yaml")

    # Write YAML asynchronously
    await handle_ws_yaml_update(hass, filename_path, lambda _: card_data, create_if_missing=True)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Card added successfully"})

#remove_card
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_card",
        vol.Optional("area_id"): str,
        vol.Optional("domain"): str,
        vol.Optional("filename"): str,
        vol.Optional("page"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_card(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle removing a card YAML file."""
    # Determine base path
    if msg.get("domain"):
        base_path = hass.config.path(f"dwains-dashboard/configs/cards/devices/{msg['domain']}")
    elif msg.get("area_id"):
        base_path = hass.config.path(f"dwains-dashboard/configs/cards/areas/{msg['area_id']}")
    else:
        connection.send_result(msg["id"], {"error": "Missing domain or area_id"})
        return

    filename = hass.config.path(base_path, f"{msg['filename']}.yaml")

    # Remove file async-safely
    await hass.async_add_executor_job(lambda: os.remove(filename) if os.path.exists(filename) else None)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")
    hass.bus.async_fire("dwains_dashboard_devicespage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "Card removed successfully"})

#edit_more_page_button
#NOT USED
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_more_page_button",
        vol.Optional("more_page"): str,
        vol.Optional("name"): str,
        vol.Optional("icon"): str,
        vol.Optional("showInNavbar"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_more_page_button(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle saving/editing a more page button."""
    more_page = msg.get("more_page")
    if not more_page:
        connection.send_result(msg["id"], {"error": "Missing more_page"})
        return

    config_dir = hass.config.path(f"dwains-dashboard/configs/more_pages/{more_page}")
    config_file = hass.config.path(config_dir, "config.yaml")

    # Ensure directory exists
    await hass.async_add_executor_job(lambda: os.makedirs(config_dir, exist_ok=True))

    # Load existing config
    if os.path.exists(config_file) and os.stat(config_file).st_size != 0:
        config_data = await hass.async_add_executor_job(
            lambda: yaml.safe_load(open(config_file, "r")) or OrderedDict()
        )
    else:
        config_data = OrderedDict()

    # Update the button config
    config_data.update({
        "name": msg.get("name"),
        "icon": msg.get("icon"),
        "show_in_navbar": msg.get("showInNavbar", True),
    })

    # Save back to YAML
    await hass.async_add_executor_job(
        lambda: yaml.dump(config_data, open(config_file, "w"), default_flow_style=False, sort_keys=False)
    )

    # Trigger reload
    hass.bus.async_fire("dwains_dashboard_homepage_card_reload")

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "More page button saved"})

#edit_more_page
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_more_page",
        vol.Optional("card_data"): str,
        vol.Optional("foldername"): str,
        vol.Optional("name"): str,
        vol.Optional("icon"): str,
        vol.Optional("showInNavbar"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_more_page(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle adding/editing a more page."""
    more_page_folder = msg.get("foldername") or slugify(msg.get("name", "new_page"))

    # Paths
    base_path = hass.config.path(f"dwains-dashboard/configs/more_pages/{more_page_folder}")
    page_file = hass.config.path(base_path, "page.yaml")
    config_file = hass.config.path(base_path, "config.yaml")

    # If no foldername and page.yaml exists, create timestamped folder
    if not msg.get("foldername") and os.path.exists(page_file) and os.stat(page_file).st_size != 0:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        more_page_folder += timestamp
        base_path = hass.config.path(f"dwains-dashboard/configs/more_pages/{more_page_folder}")
        page_file = hass.config.path(base_path, "page.yaml")
        config_file = hass.config.path(base_path, "config.yaml")

    # Ensure directories exist
    await hass.async_add_executor_job(lambda: os.makedirs(base_path, exist_ok=True))

    # Save page YAML
    page_data = json.loads(msg.get("card_data", "{}"))
    await hass.async_add_executor_job(lambda: yaml.dump(page_data, open(page_file, "w"), default_flow_style=False))

    # Save config.yaml
    config_data = {
        "name": msg.get("name"),
        "icon": msg.get("icon"),
        "show_in_navbar": msg.get("showInNavbar", True)
    }
    await hass.async_add_executor_job(lambda: yaml.dump(config_data, open(config_file, "w"), default_flow_style=False, sort_keys=False))

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_reload")
    hass.bus.async_fire("dwains_dashboard_navigation_card_reload")
    await reload_configuration(hass)

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "More page saved successfully"})

#remove_more_page
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/remove_more_page",
        vol.Required("foldername"): str,
    }
)
@websocket_api.async_response
async def ws_handle_remove_more_page(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle removing a more page folder and its contents."""
    foldername = msg.get("foldername")
    if not foldername:
        connection.send_result(msg["id"], {"error": "Missing foldername"})
        return

    base_path = hass.config.path(f"dwains-dashboard/configs/more_pages/{foldername}")
    page_file = hass.config.path(base_path, "page.yaml")

    # Check if page exists and remove folder
    if await hass.async_add_executor_job(os.path.exists, page_file):
        await hass.async_add_executor_job(shutil.rmtree, base_path, True)

    # Fire reload events
    hass.bus.async_fire("dwains_dashboard_navigation_card_reload")
    hass.bus.async_fire("dwains_dashboard_reload")
    await reload_configuration(hass)

    # Send confirmation
    connection.send_result(msg["id"], {"successful": "More page removed successfully"})

#add_more_page_to_navbar
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/add_more_page_to_navbar",
        vol.Required("more_page"): str,
    }
)
@websocket_api.async_response
async def ws_handle_add_more_page_to_navbar(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle add more page to navbar command."""

    #if os.path.exists(hass.config.path("dwains-dashboard/configs/more_pages/"+msg["more_page"]+"/config.yaml")):
    #    with open(hass.config.path("dwains-dashboard/configs/more_pages/"+msg["more_page"]+"/config.yaml")) as f:
    #        configFile = yaml.safe_load(f)
    #else:
    #    configFile = OrderedDict()
    #
    #    configFile.update({
    #        "show_in_navbar": "True"
    #    })
    #
    #    with open(hass.config.path("dwains-dashboard/configs/more_pages/"+msg["more_page"]+"/config.yaml"), 'w') as f:
    #        yaml.safe_dump(configFile, f, default_flow_style=False)

    #call reload config to rebuild the yaml for pages too
    hass.bus.async_fire("dwains_dashboard_reload")
    hass.bus.async_fire("dwains_dashboard_navigation_card_reload")

    await reload_configuration(hass)

    connection.send_result(
        msg["id"],
        {
            "succesful": "More page removed succesfully"
        },
    )

#sort_area_button
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/sort_area_button",
        vol.Required("sortData"): str,
        vol.Required("sortType"): str,
    }
)
@websocket_api.async_response
async def ws_handle_sort_area_button(hass, connection, msg):
    sort_data = json.loads(msg["sortData"])
    filepath = hass.config.path("dwains-dashboard/configs/areas.yaml")
    areas = await async_load_yaml(hass, filepath)
    for num, area_id in enumerate(sort_data, start=1):
        areas.setdefault(area_id, OrderedDict())[msg["sortType"]] = num
    await async_save_yaml(hass, filepath, areas)
    connection.send_result(msg["id"], {"successful": "Area buttons sorted successfully"})

#edit_device_bool_value
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/edit_device_bool_value",
        vol.Required("device"): str,
        vol.Optional("key"): str,
        vol.Optional("value"): bool,
    }
)
@websocket_api.async_response
async def ws_handle_edit_device_bool_value(hass, connection, msg):
    filepath = hass.config.path("dwains-dashboard/configs/devices.yaml")
    await handle_ws_yaml_update(
        hass, connection, msg, filepath,
        updates={msg["key"]: msg["value"]},
        key=msg["device"],
        reload_events=["dwains_dashboard_devicespage_card_reload"],
        success_msg="Device bool value set successfully"
    )

#sort_device_button
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/sort_device_button",
        vol.Required("sortData"): str,
    }
)
@websocket_api.async_response
async def ws_handle_sort_device_button(hass, connection, msg):
    sort_data = json.loads(msg["sortData"])
    filepath = hass.config.path("dwains-dashboard/configs/devices.yaml")
    devices = await async_load_yaml(hass, filepath)
    for num, device_id in enumerate(sort_data, start=1):
        devices.setdefault(device_id, OrderedDict())["sort_order"] = num
    await async_save_yaml(hass, filepath, devices)
    connection.send_result(msg["id"], {"successful": "Device buttons sorted successfully"})

#sort_entity
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/sort_entity",
        vol.Required("sortData"): str,
        vol.Required("sortType"): str,
    }
)
@websocket_api.async_response
async def ws_handle_sort_entity(hass, connection, msg):
    sort_data = json.loads(msg["sortData"])
    filepath = hass.config.path("dwains-dashboard/configs/entities.yaml")
    entities = await async_load_yaml(hass, filepath)
    for num, entity_id in enumerate(sort_data, start=1):
        entities.setdefault(entity_id, OrderedDict())[msg["sortType"]] = num
    await async_save_yaml(hass, filepath, entities)
    connection.send_result(msg["id"], {"successful": "Entity cards sorted successfully"})

#sort_more_page
@websocket_api.websocket_command(
    {
        vol.Required("type"): "dwains_dashboard/sort_more_page",
        vol.Required("sortData"): str,
    }
)
@websocket_api.async_response
async def ws_handle_sort_more_page(hass, connection, msg):
    sort_data = json.loads(msg["sortData"])
    for num, more_page in enumerate(sort_data, start=1):
        config_file = hass.config.path(f"dwains-dashboard/configs/more_pages/{more_page}/config.yaml")
        await async_update_yaml(hass, config_file, {"sort_order": num})
    connection.send_result(msg["id"], {"successful": "More pages sorted successfully"})

async def async_setup_entry(hass, config_entry):
    await process_yaml(hass, config_entry)

    load_dashboard(hass, config_entry)

    config_entry.add_update_listener(_update_listener)

    #hass.async_add_job( # Deprecated, trying with hass.async_create_task() ...
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(
            config_entry, ["sensor"]
        )
    )
    async_setup_notifications(hass)
    return True

async def async_remove_entry(hass, config_entry):
    _LOGGER.warning("Dwains Dashboard is now uninstalled.")
    frontend.async_remove_panel(hass, "dwains-dashboard")

async def _update_listener(hass, config_entry):
    _LOGGER.debug('Update_listener called')
    await process_yaml(hass, config_entry)
    hass.bus.async_fire("dwains_dashboard_reload")
    return True
