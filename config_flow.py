import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

SIDEPANEL_TITLE = "sidepanel_title"
SIDEPANEL_ICON = "sidepanel_icon"


@config_entries.HANDLERS.register("dwains_dashboard")
class DwainsDashboardConfigFlow(config_entries.ConfigFlow):
    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Dwains Dashboard", data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DwainsDashboardEditFlow()


class DwainsDashboardEditFlow(config_entries.OptionsFlow):
    """OptionsFlow for Dwains Dashboard."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            _LOGGER.info("Dwains Dashboard options updated: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(
                SIDEPANEL_TITLE,
                default=self.config_entry.options.get(SIDEPANEL_TITLE, "Dwains Dashboard")
            ): str,
            vol.Optional(
                SIDEPANEL_ICON,
                default=self.config_entry.options.get(SIDEPANEL_ICON, "mdi:alpha-d-box")
            ): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
