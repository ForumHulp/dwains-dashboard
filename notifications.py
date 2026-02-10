"""
Dwains Dashboard Notifications Backend with Sensor
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any
import re

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import async_generate_entity_id

from .const import (
    DOMAIN,
    DATA_NOTIFICATIONS,
    ATTR_CREATED_AT,
    ATTR_MESSAGE,
    ATTR_TITLE,
    ATTR_NOTIFICATION_ID,
    ATTR_STATUS,
    STATUS_UNREAD,
    STATUS_READ,
    EVENT_NOTIFICATIONS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
DEFAULT_OBJECT_ID = "notification"
STATE = "notifying"

# ─── Local slugify function ───────────────────────────────────
def slugify(value: str) -> str:
    """Slugify a string for entity_id."""
    value = str(value).lower()
    value = re.sub(r"[^a-z0-9_]+", "_", value)  # allow letters, numbers, underscore
    value = re.sub(r"__+", "_", value)          # collapse multiple underscores
    value = value.strip("_")
    return value


@callback
def async_setup_notifications(hass: HomeAssistant):
    """Set up Dwains Dashboard notifications backend with sensor."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_NOTIFICATIONS] = OrderedDict()
    notifications_dict = hass.data[DOMAIN][DATA_NOTIFICATIONS]

    # ─── Helper: update summary sensor ─────────────────────────────
    @callback
    def _update_sensor():
        hass.states.async_set(
            "sensor.dwains_notifications",
            len(notifications_dict),
            {
                "notifications": list(notifications_dict.values())
            }
        )

    # ─── Service: create notification ─────────────────────────────
    @callback
    def handle_create(call):
        title: Template | None = call.data.get(ATTR_TITLE)
        message: Template = call.data[ATTR_MESSAGE]
        notification_id: str | None = call.data.get(ATTR_NOTIFICATION_ID)

        # Generate ID if missing
        if notification_id is None:
            notification_id = str(int(dt_util.utcnow().timestamp() * 1000))

        entity_id = ENTITY_ID_FORMAT.format(slugify(notification_id))

        # Render templates
        try:
            if isinstance(message, Template):
                message.hass = hass
                message = message.async_render()
        except Exception as err:
            _LOGGER.error("Error rendering message: %s", err)
            message = str(message)

        try:
            if title is not None and isinstance(title, Template):
                title.hass = hass
                title = title.async_render()
        except Exception as err:
            _LOGGER.error("Error rendering title: %s", err)
            title = str(title)

        created_at = dt_util.utcnow()

        # Overwrite or create
        hass.states.async_set(
            entity_id,
            STATE,
            {
                ATTR_NOTIFICATION_ID: notification_id,
                ATTR_MESSAGE: message,
                ATTR_TITLE: title,
                ATTR_STATUS: STATUS_UNREAD,
                ATTR_CREATED_AT: created_at,
            },
        )

        notifications_dict[entity_id] = {
            ATTR_NOTIFICATION_ID: notification_id,
            ATTR_MESSAGE: message,
            ATTR_TITLE: title,
            ATTR_STATUS: STATUS_UNREAD,
            ATTR_CREATED_AT: created_at,
        }

        hass.bus.async_fire(EVENT_NOTIFICATIONS_UPDATED)
        _update_sensor()

    # ─── Service: dismiss notification ───────────────────────────
    @callback
    def handle_dismiss(call):
        notification_id = call.data.get(ATTR_NOTIFICATION_ID)

        if notification_id:
            # Dismiss a single notification
            entity_id = ENTITY_ID_FORMAT.format(slugify(notification_id))
            if entity_id in notifications_dict:
                hass.states.async_remove(entity_id)
                del notifications_dict[entity_id]
                hass.bus.async_fire(EVENT_NOTIFICATIONS_UPDATED, {
                    "action": "dismiss",
                    "notification_id": notification_id,
                })
                _LOGGER.info("Dwains notification dismissed: %s", notification_id)
            else:
                _LOGGER.warning("Notification %s not found", notification_id)
        else:
            # Dismiss all notifications
            for entity_id in list(notifications_dict.keys()):
                hass.states.async_remove(entity_id)
                _LOGGER.info("Dwains notification dismissed: %s", entity_id)
            notifications_dict.clear()
            hass.bus.async_fire(EVENT_NOTIFICATIONS_UPDATED, {"action": "dismiss_all"})
            _LOGGER.info("All Dwains notifications dismissed")

        # Update the summary sensor after dismissal
        _update_sensor()

    # ─── Service: mark notification as read ──────────────────────
    @callback
    def handle_mark_read(call):
        notification_id = call.data.get(ATTR_NOTIFICATION_ID)
        entity_id = ENTITY_ID_FORMAT.format(slugify(notification_id))
        notification = notifications_dict.get(entity_id)
        if notification:
            notification[ATTR_STATUS] = STATUS_READ
            hass.bus.async_fire(EVENT_NOTIFICATIONS_UPDATED)
            _update_sensor()
            _LOGGER.info("Dwains notification marked read: %s", notification_id)
        else:
            _LOGGER.warning("Notification %s not found", notification_id)

    # ─── Register services ───────────────────────────────────────
    hass.services.async_register(DOMAIN, "notification_create", handle_create)
    hass.services.async_register(DOMAIN, "notification_dismiss", handle_dismiss)
    hass.services.async_register(DOMAIN, "notification_mark_read", handle_mark_read)

    # ─── WebSocket: get notifications ───────────────────────────
    @websocket_api.websocket_command({
        "type": "dwains_dashboard_notification/get"
    })
    @websocket_api.async_response
    async def ws_get_notifications(hass, connection, msg):
        connection.send_result(
            msg["id"],
            [
                {
                    ATTR_NOTIFICATION_ID: data[ATTR_NOTIFICATION_ID],
                    ATTR_MESSAGE: data[ATTR_MESSAGE],
                    ATTR_STATUS: data[ATTR_STATUS],
                    ATTR_TITLE: data.get(ATTR_TITLE),
                    ATTR_CREATED_AT: data[ATTR_CREATED_AT],
                }
                for data in notifications_dict.values()
            ]
        )

    # ─── Backward-compatible WebSocket ─────────────────────────
    @websocket_api.websocket_command({
        "type": "dwains_dashboard/notifications"
    })
    @websocket_api.async_response
    async def ws_get_notifications_old(hass, connection, msg):
        connection.send_result(
            msg["id"],
            [
                {
                    ATTR_NOTIFICATION_ID: data[ATTR_NOTIFICATION_ID],
                    ATTR_MESSAGE: data[ATTR_MESSAGE],
                    ATTR_STATUS: data[ATTR_STATUS],
                    ATTR_TITLE: data.get(ATTR_TITLE),
                    ATTR_CREATED_AT: data[ATTR_CREATED_AT],
                }
                for data in notifications_dict.values()
            ]
        )

    # Register WebSocket commands
    websocket_api.async_register_command(hass, ws_get_notifications)
    websocket_api.async_register_command(hass, ws_get_notifications_old)

    # ─── Initialize summary sensor ───────────────────────────────
    _update_sensor()
