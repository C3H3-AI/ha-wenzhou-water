"""温州水务Home Assistant集成"""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .sensor import DOMAIN, async_setup_entry

__version__ = "0.0.2"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置集成入口"""
    hass.data.setdefault(DOMAIN, {})
    return await async_setup_entry(hass, entry, async_add_entities)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成"""
    unload_ok = True
    if DOMAIN in hass.data:
        del hass.data[DOMAIN]
    return unload_ok
