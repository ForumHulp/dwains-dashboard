from collections import OrderedDict
from typing import Any, Mapping, Callable, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DOMAIN
from .helpers import ws_send_success, ws_send_error

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_entities"


async def async_handle_ws_storage_update(
    hass: HomeAssistant,
    connection,
    msg: Mapping[str, Any],
    *,
    updates: Any = None,
    key: Optional[str] = None,
    reload_events: Optional[list[str]] = None,
    success_msg: Optional[str] = None,
):
    """Storage-based replacement for handle_ws_yaml_update."""

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    data = await store.async_load()
    if data is None:
        data = OrderedDict()

    # --------------------------------
    # Apply updates
    # --------------------------------
    try:
        if callable(updates):
            data = updates(data)

        elif key:
            entity_data = data.setdefault(key, OrderedDict())
            if isinstance(updates, dict):
                for k, v in updates.items():
                    if v is not None:
                        entity_data[k] = v

        elif isinstance(updates, dict):
            for k, v in updates.items():
                if v is not None:
                    data[k] = v

    except Exception as err:
        return ws_send_error(connection, msg, "storage_update_failed", str(err))

    # --------------------------------
    # Save to .storage
    # --------------------------------
    await store.async_save(data)

    # --------------------------------
    # Fire reload events
    # --------------------------------
    if reload_events:
        for event in reload_events:
            hass.bus.async_fire(event)

    if success_msg:
        ws_send_success(connection, msg, success_msg)

    return data
