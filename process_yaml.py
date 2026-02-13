import logging
import os
import io
import json
from collections import OrderedDict

import jinja2
import yaml
from annotatedyaml import loader
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DASHBOARD_URL

_LOGGER = logging.getLogger(__name__)

# --- Global dictionaries ---
dashboard_more_pages = {}
llgen_config = {}

# --- Jinja2 Environment ---
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader("/"))
jinja_env.filters["fromjson"] = lambda v: json.loads(v)

# --- YAML Loading ---
def render_template(fname: str, args: dict) -> io.StringIO:
    try:
        template = jinja_env.get_template(fname)
        rendered_content = template.render({
            **args,
            "_dd_more_pages": dashboard_more_pages,
            "_global": llgen_config
        })
        stream = io.StringIO(rendered_content)
        stream.name = fname
        return stream
    except jinja2.TemplateError as e:
        _LOGGER.error("Failed to render template %s: %s", fname, e)
        raise HomeAssistantError(e)

def load_yamll(fname: str, secrets=None, args: dict = {}) -> OrderedDict:
    if not os.path.exists(fname):
        _LOGGER.debug("YAML file not found, skipping: %s", fname)
        return OrderedDict()

    try:
        with open(fname, "r", encoding="utf-8") as f:
            first_line = f.readline().lower()
            process_template = first_line.startswith((
                "# dwains_dashboard", "# dwains_theme", "# lovelace_gen", "#dwains_dashboard"
            ))

        if process_template:
            stream = render_template(fname, args)
            return loader.yaml.load(stream, Loader=lambda s: loader.PythonSafeLoader(s, secrets)) or OrderedDict()
        else:
            with open(fname, "r", encoding="utf-8") as f:
                return loader.yaml.load(f, Loader=lambda s: loader.PythonSafeLoader(s, secrets)) or OrderedDict()

    except Exception as e:
        _LOGGER.error("Error loading YAML %s: %s", fname, e)
        return OrderedDict()

# --- !include support ---
def _include_yaml(loader_instance, node):
    args = {}
    if isinstance(node.value, str):
        fn = node.value
    else:
        fn, args, *_ = loader_instance.construct_sequence(node)

    fname = os.path.abspath(os.path.join(os.path.dirname(loader_instance.name), fn))

    if not os.path.exists(fname):
        _LOGGER.warning("Included file not found, skipping: %s", fname)
        return OrderedDict()

    try:
        return loader._add_reference(load_yamll(fname, loader_instance.secrets, args=args), loader_instance, node)
    except Exception as exc:
        _LOGGER.error("Failed to include YAML file %s: %s", fname, exc)
        return OrderedDict()

loader.load_yaml = load_yamll
loader.PythonSafeLoader.add_constructor("!include", _include_yaml)

# --- YAML Composer patch ---
def compose_node(self, parent, index):
    if self.check_event(yaml.events.AliasEvent):
        event = self.get_event()
        anchor = event.anchor
        if anchor not in self.anchors:
            raise yaml.composer.ComposerError(None, None, "found undefined alias %r" % anchor, event.start_mark)
        return self.anchors[anchor]

    event = self.peek_event()
    anchor = event.anchor
    self.descend_resolver(parent, index)

    if self.check_event(yaml.events.ScalarEvent):
        node = self.compose_scalar_node(anchor)
    elif self.check_event(yaml.events.SequenceStartEvent):
        node = self.compose_sequence_node(anchor)
    elif self.check_event(yaml.events.MappingStartEvent):
        node = self.compose_mapping_node(anchor)

    self.ascend_resolver()
    return node

yaml.composer.Composer.compose_node = compose_node

# --- Page scanning helpers ---
async def _ensure_page_config(hass: HomeAssistant, more_pages_path: str, subdir: str):
    page_yaml_path = os.path.join(more_pages_path, subdir, "page.yaml")
    config_yaml_path = os.path.join(more_pages_path, subdir, "config.yaml")

    if not os.path.exists(page_yaml_path):
        return

    def write_default_config(path, subdir_name):
        with open(path, "w", encoding="utf-8") as f:
            config = OrderedDict(name=subdir_name, icon="mdi:puzzle")
            yaml.safe_dump(config, f, default_flow_style=False)
        return config

    def read_config(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    if not os.path.exists(config_yaml_path):
        config = await hass.async_add_executor_job(write_default_config, config_yaml_path, subdir)
    else:
        try:
            config = await hass.async_add_executor_job(read_config, config_yaml_path)
            if "name" not in config or "icon" not in config:
                _LOGGER.warning("Invalid config.yaml in %s, recreating default", subdir)
                config = await hass.async_add_executor_job(write_default_config, config_yaml_path, subdir)
        except Exception as e:
            _LOGGER.error("Failed to read config.yaml in %s: %s", subdir, e)
            config = await hass.async_add_executor_job(write_default_config, config_yaml_path, subdir)

    dashboard_more_pages[subdir] = {
        "name": config["name"],
        "icon": config["icon"],
        "path": os.path.join(DASHBOARD_URL, "configs", "more_pages", subdir, "page.yaml"),
    }

async def _scan_more_pages(hass: HomeAssistant):
    more_pages_path = hass.config.path(f"{DASHBOARD_URL}/configs/more_pages")
    if not os.path.isdir(more_pages_path):
        return

    subdirs = await hass.async_add_executor_job(os.listdir, more_pages_path)
    for subdir in subdirs:
        await _ensure_page_config(hass, more_pages_path, subdir)

# --- Main YAML processor ---
async def process_yaml(hass: HomeAssistant, config_entry):
    hki_path = hass.config.path("hki-user/config")
    if os.path.exists(hki_path):
        for fname in loader._find_files(hki_path, "*.yaml"):
            loaded_yaml = load_yamll(fname)
            if isinstance(loaded_yaml, dict):
                llgen_config.update(loaded_yaml)

    await _scan_more_pages(hass)
    hass.bus.async_fire("{{ DOMAIN }}.reload")

    async def handle_reload(call):
        _LOGGER.warning("Reload dashboard configuration")
        await reload_configuration(hass)

    hass.services.async_register(DOMAIN, "reload", handle_reload)

async def reload_configuration(hass: HomeAssistant):
    await _scan_more_pages(hass)
    hass.bus.async_fire("{{ DOMAIN }}.reload")
