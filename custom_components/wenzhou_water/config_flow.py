"""温州水务配置流程"""
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class WenzhouWaterConfigFlow(ConfigFlow, domain="wenzhou_water"):
    """温州水务配置流程"""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """用户输入配置"""
        errors = {}

        if user_input is not None:
            # 验证token
            access_token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            if not access_token:
                errors["base"] = "invalid_token"
            else:
                # 保存token并进入下一步选择水表
                await self.async_set_unique_id(access_token[:16])
                self._access_token = access_token
                return await self.async_step_select_meter()

        data_schema = vol.Schema({
            vol.Required(CONF_ACCESS_TOKEN): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"url": "https://github.com/C3H3-AI/ha-wenzhou-water"},
        )

    async def async_step_select_meter(self, user_input: dict[str, Any] = None) -> FlowResult:
        """选择水表"""
        from .api import WenzhouWaterAPI

        errors = {}
        api = WenzhouWaterAPI(self._access_token)

        try:
            # 获取用户的水表列表
            meter_cards = await api.get_meter_cards()
            if not meter_cards:
                errors["base"] = "no_meters"
                return self.async_show_form(step_id="user", errors=errors)
        except Exception as e:
            _LOGGER.error(f"Failed to get meter cards: {e}")
            errors["base"] = "invalid_token"
            return self.async_show_form(step_id="user", errors=errors)

        # 保存水表列表供选择
        self._meter_cards = meter_cards
        meter_options = {
            card["cardId"]: f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"
            for card in meter_cards
        }

        if user_input is not None:
            selected_id = user_input.get(CONF_METER_CARD_ID)
            if selected_id:
                selected_card = next((c for c in meter_cards if c["cardId"] == selected_id), None)
                if selected_card:
                    return self.async_create_entry(
                        title=f"温州水务 - {selected_card.get('cardName', selected_id)}",
                        data={
                            CONF_ACCESS_TOKEN: self._access_token,
                            CONF_METER_CARD_ID: selected_id,
                            CONF_METER_CARD_NAME: selected_card.get("cardName"),
                            CONF_METER_CARD_ADDRESS: selected_card.get("cardAddress"),
                        },
                    )

        data_schema = vol.Schema({
            vol.Required(CONF_METER_CARD_ID): vol.In(meter_options),
        })

        return self.async_show_form(
            step_id="select_meter",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry, add_suggested_values=True):
        """获取选项流程"""
        return WenzhouWaterOptionsFlow(entry)


class WenzhouWaterOptionsFlow(OptionsFlow):
    """温州水务选项流程"""

    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] = None) -> FlowResult:
        """配置选项"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # 默认更新间隔为1小时
        current_interval = self.entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        current_hours = current_interval // 3600

        data_schema = vol.Schema({
            vol.Required("scan_interval_hours", default=current_hours): vol.All(
                vol.Coerce(int),
                vol.In([1, 2, 3, 6, 12, 24])
            ),
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)
