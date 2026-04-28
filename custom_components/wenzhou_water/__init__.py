"""温州水务Home Assistant集成"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)

__version__ = "0.1.0"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置集成入口"""
    hass.data.setdefault("wenzhou_water", {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop("wenzhou_water", None)
    return unload_ok
