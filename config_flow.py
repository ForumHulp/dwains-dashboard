import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN

HOMEPAGE_OPTIONS = {
    "sidepanel_title": "Dwains Dashboard",
    "sidepanel_icon": "mdi:alpha-d-box",
    "disable_clock": False,
    "am_pm_clock": True,
    "disable_welcome_message": False,
    "v2_mode": False,
    "disable_sensor_graph": False,
    "invert_cover": False,
    "weather_entity": "weather.thuis",
    "alarm_entity": "alarm_control_panel.home_alarm"
}

class DwainsDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Dwains Dashboard",
                data=user_input,
            )

        schema_dict = {}
        for key, default in HOMEPAGE_OPTIONS.items():
            if key in ("weather_entity", "alarm_entity"):
                continue
            schema_dict[vol.Optional(key, default=default)] = type(default)

        schema = vol.Schema(schema_dict)

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DwainsDashboardOptionsFlow(config_entry)


def _get_entities_by_domain(hass, domain):
    return {state.entity_id: state.entity_id for state in hass.states.async_all() if state.domain == domain}


class DwainsDashboardOptionsFlow(config_entries.OptionsFlow):
    """OptionsFlow for Dwains Dashboard."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            for key in ("weather_entity", "alarm_entity"):
                values = user_input.get(key, [])
                user_input[key] = values[0] if values else ""
            return self.async_create_entry(title="", data=user_input)

        weather_entities = _get_entities_by_domain(self.hass, "weather")
        alarm_entities = _get_entities_by_domain(self.hass, "alarm_control_panel")

        weather_default = self._config_entry.options.get("weather_entity")
        if weather_default and weather_default in weather_entities:
            weather_default = [weather_default]
        else:
            weather_default = []

        alarm_default = self._config_entry.options.get("alarm_entity")
        if alarm_default and alarm_default in alarm_entities:
            alarm_default = [alarm_default]
        else:
            alarm_default = []
    

        schema_dict = {}
        for key, default in HOMEPAGE_OPTIONS.items():
            if key in ("weather_entity", "alarm_entity"):
                continue
            schema_dict[vol.Optional(key, default=self._config_entry.options.get(key, default))] = type(default)

        schema_dict[vol.Optional(
            "weather_entity",
            default=weather_default
        )] = cv.multi_select(weather_entities)

        schema_dict[vol.Optional(
            "alarm_entity",
            default=alarm_default
        )] = cv.multi_select(alarm_entities)

        schema = vol.Schema(schema_dict)

        return self.async_show_form(step_id="init", data_schema=schema)
