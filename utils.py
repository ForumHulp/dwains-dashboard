# utils.py
from collections import OrderedDict
import os
import yaml
import shutil
from datetime import datetime

async def async_load_yaml(hass, filepath, default=None):
    """Async-safe load YAML file."""
    default = default or OrderedDict()
    if os.path.exists(filepath) and os.stat(filepath).st_size != 0:
        return await hass.async_add_executor_job(lambda: yaml.safe_load(open(filepath, "r")) or default)
    return default

async def async_save_yaml(hass, filepath, data):
    """Async-safe save YAML file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    await hass.async_add_executor_job(lambda: yaml.dump(data, open(filepath, "w"), default_flow_style=False, sort_keys=False))

async def async_update_yaml(hass, filepath, updates: dict, key: str | None = None):
    """Load YAML, update keys, save it."""
    data = await async_load_yaml(hass, filepath)
    if key:
        data.setdefault(key, OrderedDict()).update(updates)
    else:
        data.update(updates)
    await async_save_yaml(hass, filepath, data)
    return data

async def async_remove_file_or_folder(hass, path):
    """Async-safe remove file or folder."""
    if await hass.async_add_executor_job(os.path.exists, path):
        if os.path.isdir(path):
            await hass.async_add_executor_job(lambda: shutil.rmtree(path, ignore_errors=True))
        else:
            await hass.async_add_executor_job(lambda: os.remove(path))

async def handle_ws_yaml_update(
    hass,
    connection,
    msg: dict,
    filepath: str,
    updates: dict = None,
    key: str | None = None,
    reload_events: list[str] | None = None,
    success_msg: str = "Saved successfully",
):
    """Generic WS handler for updating YAML files asynchronously."""
    if updates:
        await async_update_yaml(hass, filepath, updates, key)

    if reload_events:
        for ev in reload_events:
            hass.bus.async_fire(ev)

    connection.send_result(msg["id"], {"successful": success_msg})

async def async_load_yaml_file(hass, file_path):
    """Load a YAML file safely in an executor."""
    if not os.path.exists(file_path):
        return OrderedDict()
    def _load():
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or OrderedDict()
    return await hass.async_add_executor_job(_load)

async def async_load_yaml_from_dir(hass, dir_path, strip_ext=False, nested=False):
    """
    Load YAML files from a directory asynchronously.
    - nested=True: loads YAML files inside subdirectories
    - strip_ext=True: removes '.yaml' from keys
    """
    result = OrderedDict()
    full_path = hass.config.path(dir_path)

    if not os.path.isdir(full_path):
        return result

    if nested:
        subdirs = [
            d for d in await hass.async_add_executor_job(os.listdir, full_path)
            if os.path.isdir(os.path.join(full_path, d))
        ]
        for subdir in subdirs:
            subdir_path = os.path.join(full_path, subdir)
            subdir_dict = OrderedDict()
            fnames = sorted(await hass.async_add_executor_job(os.listdir, subdir_path))
            for fname in fnames:
                if fname.endswith(".yaml"):
                    file_path = os.path.join(subdir_path, fname)
                    content = await async_load_yaml_file(hass, file_path)
                    subdir_dict[fname] = content
            result[subdir] = subdir_dict
    else:
        fnames = sorted(await hass.async_add_executor_job(os.listdir, full_path))
        for fname in fnames:
            if fname.endswith(".yaml"):
                file_path = os.path.join(full_path, fname)
                content = await async_load_yaml_file(hass, file_path)
                key = fname[:-5] if strip_ext else fname
                result[key] = content

    return result