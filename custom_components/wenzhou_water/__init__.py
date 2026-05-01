"""温州水务Home Assistant集成 - v5.0.0

v5.0.0: 基于 wz_water_sg 架构重写
  - ConfigFlow 使用 async_show_menu 选择登录方式
  - 微信扫码使用微信服务器图片 URL（移除 segno 依赖）
  - 独立 qr_login / validate_qr_login 步骤
  - 简化 __init__，移除旧版迁移代码
"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS = ["sensor", "button"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """通过 configuration.yaml 配置的方式（可选兼容）"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置集成入口"""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """处理 config entry 版本迁移

    v1 → v2: 添加 scan_interval / scan_interval_unit
    v2 → v3: 添加 meter_cards（多水表单条记录）
    v3 → v4: 纯短信登录，三步流程
    v4 → v5: 基于 wz_water_sg 架构重写（async_show_menu + 微信服务器二维码）
    """
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
        # v4 → v5: 添加 login_type 字段（如果不存在）
        if "login_type" not in new_data:
            new_data["login_type"] = "sms"
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=5)
        _LOGGER.info("温州水务: v3/v4→v5 迁移完成")

    return True


async def async_token_expired_notification(hass: HomeAssistant, entry_id: str) -> None:
    """Token过期通知 - 提醒用户重新登录"""
    try:
        from homeassistant.exceptions import HomeAssistantError
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "⚠️ 温州水务登录已过期",
                "message": "温州水务集成的登录令牌已过期（有效期约6个月），数据将停止更新。\n\n请点击下方按钮重新登录：\n\n[重新配置 →](config/config_entries/config_flow?config_flow=wenzhou_water)\n\n进入「设置 → 设备与服务 → 温州水务 → 重新配置」，输入手机号接收验证码即可。",
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
