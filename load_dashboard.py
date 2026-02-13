from homeassistant.components.lovelace.dashboard import LovelaceYAML
from homeassistant.components.lovelace import _register_panel
from .const import DOMAIN, DEFAULT_TITLE, DEFAULT_ICON, DASHBOARD_URL

def load_dashboard(hass, config_entry):
    """Register Dashboard Lovelace panel (YAML mode)."""
    title = config_entry.options.get("sidepanel_title", DEFAULT_TITLE)
    icon = config_entry.options.get("sidepanel_icon", DEFAULT_ICON)

    filename = hass.config.path("custom_components", DOMAIN, "lovelace", "ui-lovelace.yaml")

    dashboard_config = {
        "mode": "yaml",
        "title": title,
        "icon": icon,
        "filename": filename,
        "show_in_sidebar": True,
        "require_admin": False,
    }

    hass.data["lovelace"].dashboards[DASHBOARD_URL] = LovelaceYAML(
        hass, DASHBOARD_URL, dashboard_config
    )
    _register_panel(hass, DASHBOARD_URL, "yaml", dashboard_config, False)