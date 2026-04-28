"""温州水务Home Assistant集成 - v1.2.0

修复:
  - 添加 async_migrate_entry 处理 v1→v2 版本迁移
  - scan_interval 缺失时自动补充默认值
"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_SCAN_INTERVAL, CONF_SCAN_INTERVAL_UNIT, DEFAULT_SCAN_INTERVAL_VALUE, DEFAULT_SCAN_INTERVAL_UNIT

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)

__version__ = "1.3.0"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """通过 configuration.yaml 配置的方式（可选兼容）"""
    return True


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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """处理 config entry 版本迁移

    v1 → v2: 添加 scan_interval 和 scan_interval_unit 字段
    旧版 config entry 没有 scan_interval，导致 sensor.py 读取时为 None
    """
    _LOGGER.info(f"温州水务: 迁移 config entry 从 version {config_entry.version}")

    if config_entry.version == 1:
        new_data = {**config_entry.data}
        # 补充缺失的 scan_interval 字段
        if CONF_SCAN_INTERVAL not in new_data:
            new_data[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL_VALUE
            _LOGGER.info(f"补充 scan_interval={DEFAULT_SCAN_INTERVAL_VALUE}")
        if CONF_SCAN_INTERVAL_UNIT not in new_data:
            new_data[CONF_SCAN_INTERVAL_UNIT] = DEFAULT_SCAN_INTERVAL_UNIT
            _LOGGER.info(f"补充 scan_interval_unit={DEFAULT_SCAN_INTERVAL_UNIT}")

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2
        )
        _LOGGER.info("温州水务: 迁移到 version 2 完成")

    return True
