from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, VERSION


async def async_setup_entry(hass, config_entry, async_add_entities):
    async_add_entities([DwainsDashboardVersionSensor()])


class DwainsDashboardVersionSensor(SensorEntity):
    _attr_unique_id = "dwains-dashboard-latest-version"
    _attr_name = "Dwains Dashboard Version"
    _attr_icon = "mdi:alpha-d-box"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True

    def __init__(self) -> None:
        self._attr_native_value = VERSION
