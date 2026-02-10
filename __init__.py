import logging
import inspect
import yaml
import collections

from yaml.representer import Representer
from homeassistant.core import HomeAssistant
from homeassistant.config import ConfigType
from homeassistant.components import frontend, websocket_api

from . import websocket as ws_module
from .const import DOMAIN
from .load_plugins import load_plugins
from .load_dashboard import load_dashboard
from .process_yaml import process_yaml
from .notifications import async_setup_notifications

yaml.add_representer(collections.OrderedDict, Representer.represent_dict)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the custom integration."""
    # Initialize data store
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {
            "notifications": {},
            "commands": {},
            "latest_version": ""
        }

    # Automatically register all WebSocket commands defined in this module
    ws_commands = [
        func
        for name, func in inspect.getmembers(ws_module, inspect.isfunction)
        if name.startswith(("ws_", "websocket_"))
    ]

    # Sort commands alphabetically by function name for consistency
    for func in sorted(ws_commands, key=lambda f: f.__name__):
        websocket_api.async_register_command(hass, func)

    # Load plugins and notifications
    await load_plugins(hass, DOMAIN)
    async_setup_notifications(hass)

    return True

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
