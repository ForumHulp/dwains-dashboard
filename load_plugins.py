from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from .const import DOMAIN, VERSION, FRONTEND_LOADED, FRONTEND_URL, FRONTEND_DIR, FRONTEND_FILE
import os

async def load_plugins(hass, name: str):
    """Load Dwains Dashboard frontend JS only once."""
    if hass.data.get(FRONTEND_LOADED):
        return
    hass.data[FRONTEND_LOADED] = True

    # Add JS to frontend
    add_extra_js_url(hass, f"{FRONTEND_URL}/{FRONTEND_FILE}?version={VERSION}")

    # Map URL path to local folder
    js_path = hass.config.path(f"custom_components/{name}/{FRONTEND_DIR}")
    if os.path.isdir(js_path):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, js_path, cache_headers=True)]
        )