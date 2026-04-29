"""温州水务 按钮平台

提供按钮实体用于手动触发操作：
1. 刷新数据 - 立即刷新所有传感器数据
2. 抓取历史 - 从API批量抓取历史账单
"""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
):
    """设置按钮实体 - 延迟加载模式，不在此时获取coordinator/api"""
    buttons = [
        RefreshWaterDataButton(hass, config_entry),
        FetchWaterHistoryButton(hass, config_entry),
    ]

    async_add_entities(buttons)
    _LOGGER.info(f"温州水务按钮实体已注册: {len(buttons)}个")


class RefreshWaterDataButton(ButtonEntity):
    """刷新数据按钮"""

    _attr_has_entity_name = True
    _attr_name = "刷新数据"
    _attr_icon = "mdi:refresh"

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_refresh_data"

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "温州水务",
            "manufacturer": "温州水务",
            "model": "智能水表",
        }

    async def async_press(self) -> None:
        """按钮按下时触发 - 动态获取coordinator"""
        _LOGGER.info("用户触发: 手动刷新水务数据")

        hass_domain = self.hass.data.get(DOMAIN, {})
        coordinator = hass_domain.get(f"{self.config_entry.entry_id}_coordinator")

        if not coordinator:
            _LOGGER.error("coordinator 未初始化，请稍后重试或重启 Home Assistant")
            return

        await coordinator.async_request_refresh()
        _LOGGER.info("水务数据刷新请求已提交")


class FetchWaterHistoryButton(ButtonEntity):
    """抓取历史账单按钮"""

    _attr_has_entity_name = True
    _attr_name = "抓取历史"
    _attr_icon = "mdi:history"

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.config_entry = config_entry
        self._coordinator = None
        self._attr_unique_id = f"{config_entry.entry_id}_fetch_history"

    async def async_added_to_hass(self) -> None:
        """添加到 Home Assistant 后获取依赖"""
        await super().async_added_to_hass()
        hass_domain = self.hass.data.get(DOMAIN, {})
        self._coordinator = hass_domain.get(f"{self.config_entry.entry_id}_coordinator")

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "温州水务",
            "manufacturer": "温州水务",
            "model": "智能水表",
        }

    async def async_press(self) -> None:
        """按钮按下时触发 - 批量抓取历史账单"""
        _LOGGER.info("用户触发: 抓取历史账单")

        if not self._coordinator:
            hass_domain = self.hass.data.get(DOMAIN, {})
            self._coordinator = hass_domain.get(f"{self.config_entry.entry_id}_coordinator")

        if not self._coordinator:
            _LOGGER.error("coordinator 未初始化，请稍后重试或重启 Home Assistant")
            return

        try:
            total_fetched = 0
            for card_id in self._coordinator.card_ids:
                # 重置初始化标志，强制重新抓取
                self._coordinator._history_init_flags[card_id] = False
                _LOGGER.info(f"  开始抓取 {card_id} 的历史账单...")

                # 触发批量初始化（内部调用 _init_billing_history_from_api）
                history = await self._coordinator._init_billing_history_from_api(card_id)
                total_fetched += len(history) if history else 0
                _LOGGER.info(f"  {card_id} 历史账单抓取完成: {len(history) if history else 0} 条")

            _LOGGER.info(f"历史账单抓取完成: 共 {total_fetched} 条")

            # 触发数据刷新
            await self._coordinator.async_request_refresh()

            # 通知前端
            self.hass.bus.async_fire("wenzhou_water_history_fetched", {
                "config_entry_id": self.config_entry.entry_id,
                "total_fetched": total_fetched,
            })

        except Exception as e:
            _LOGGER.error(f"抓取历史账单失败: {e}")
