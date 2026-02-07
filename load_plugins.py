import logging

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

_LOADED = "dwains_dashboard_frontend_loaded"


async def load_plugins(hass, name):
    if hass.data.get(_LOADED):
        return

    hass.data[_LOADED] = True

    add_extra_js_url(
        hass,
        f"/dwains_dashboard/js/dwains-dashboard.js?version={VERSION}",
    )

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/dwains_dashboard/js",
                hass.config.path(f"custom_components/{name}/js"),
                True,
            )
        ]
    )
