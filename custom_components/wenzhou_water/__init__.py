"""温州水务Home Assistant集成 - v4.0.0

v4.0.0: 能源面板支持
  - 新增水表历史累计传感器
  - 新增累计水费传感器
  - 历史数据自动注入统计表（sqlite3直写）
  - 启动时自动注入 + 按钮触发
"""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS = ["sensor", "button"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_auto_inject():
        await asyncio.sleep(10)
        try:
            from .sensor import _import_water_history_to_statistics
            await _import_water_history_to_statistics(hass, entry)
        except Exception as e:
            _LOGGER.warning("自动注入水表历史统计失败（可按钮补救）: %s", e)

    hass.async_create_task(async_auto_inject())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.info(f"温州水务: 迁移 config entry 从 version {config_entry.version}")

    new_data = {**config_entry.data}

    if config_entry.version == 1:
        from .const import DEFAULT_SCAN_INTERVAL_VALUE, DEFAULT_SCAN_INTERVAL_UNIT
        if "scan_interval" not in new_data:
            new_data["scan_interval"] = DEFAULT_SCAN_INTERVAL_VALUE
        if "scan_interval_unit" not in new_data:
            new_data["scan_interval_unit"] = DEFAULT_SCAN_INTERVAL_UNIT
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("温州水务: v1→v2 迁移完成")

    if config_entry.version == 2:
        if "meter_cards" not in new_data:
            card_id = new_data.get("meter_card_id")
            if card_id:
                new_data["meter_cards"] = [{
                    "cardId": card_id,
                    "cardName": new_data.get("meter_card_name", "未知"),
                    "cardAddress": new_data.get("meter_card_address", "未知地址"),
                }]
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=3)
        _LOGGER.info("温州水务: v2→v3 迁移完成")

    if config_entry.version in (3, 4):
        if "login_type" not in new_data:
            new_data["login_type"] = "sms"
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=5)
        _LOGGER.info("温州水务: v3/v4→v5 迁移完成")

    return True


async def async_token_expired_notification(hass: HomeAssistant, entry_id: str) -> None:
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "⚠️ 温州水务登录已过期",
                "message": "温州水务集成的登录令牌已过期（有效期约6个月），数据将停止更新。\n\n请点击下方按钮重新登录：\n\n[重新配置 →](config/config_entries/config_flow?config_flow=wenzhou_water)\n\n进入「设置 → 设备与服务 → 温州水务 → 重新配置」，选择微信扫码或短信验证码登录即可。",
                "notification_id": f"wenzhou_water_token_expired_{entry_id}",
            },
            blocking=True,
        )
        _LOGGER.warning("温州水务: Token过期通知已发送")
    except Exception as e:
        _LOGGER.warning(f"温州水务: 发送Token过期通知失败: {e}")

    _LOGGER.error(
        f"温州水务登录已过期（配置项ID: {entry_id}），请重新配置"
    )