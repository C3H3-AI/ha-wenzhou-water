"""温州水务配置流程 - v1.1.0
修复:
  - 简化扫描间隔只留月模式
  - reconfigure 支持换水表
  - token 字段脱敏
"""
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import WenzhouWaterAPI, WenzhouWaterTokenExpiredError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_UNIT,
    SCAN_INTERVAL_UNITS,
    DEFAULT_SCAN_INTERVAL_VALUE,
    DEFAULT_SCAN_INTERVAL_UNIT,
)

_LOGGER = logging.getLogger(__name__)


def _validate_interval(value: int) -> str | None:
    """验证月模式数值（1-31）"""
    if not 1 <= value <= 31:
        return "每月几号更新？请输入 1-31"
    return None


class WenzhouWaterConfigFlow(ConfigFlow, domain="wenzhou_water"):
    """温州水务配置流程"""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """用户输入配置"""
        errors = {}

        if user_input is not None:
            access_token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            if not access_token:
                errors["base"] = "invalid_token"
            else:
                try:
                    api = WenzhouWaterAPI(access_token)
                    user_info = await api.get_user_info()
                    if not user_info:
                        errors["base"] = "invalid_token"
                    else:
                        await self.async_set_unique_id(access_token[:16])
                        self._access_token = access_token
                        return await self.async_step_select_meter()
                except WenzhouWaterTokenExpiredError:
                    errors["base"] = "token_expired"
                except Exception as e:
                    _LOGGER.error(f"Token validation failed: {e}")
                    errors["base"] = "invalid_token"

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
        """选择水表并配置更新日期"""
        errors = {}

        if not hasattr(self, "_access_token"):
            return self.async_show_form(step_id="user", errors={"base": "missing_token"})

        api = WenzhouWaterAPI(self._access_token)

        try:
            meter_cards = await api.get_meter_cards()
            if not meter_cards:
                errors["base"] = "no_meters"
                return self.async_show_form(step_id="user", errors=errors)
        except Exception as e:
            _LOGGER.error(f"Failed to get meter cards: {e}")
            errors["base"] = "invalid_token"
            return self.async_show_form(step_id="user", errors=errors)

        self._meter_cards = meter_cards
        meter_options = {
            card["cardId"]: f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"
            for card in meter_cards
        }

        if user_input is not None:
            selected_id = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            validation_error = _validate_interval(int(day_of_month))
            if validation_error:
                errors[CONF_SCAN_INTERVAL] = validation_error
            elif selected_id:
                selected_card = next((c for c in meter_cards if c["cardId"] == selected_id), None)
                if selected_card:
                    return self.async_create_entry(
                        title=f"温州水务 - {selected_card.get('cardName', selected_id)}",
                        data={
                            CONF_ACCESS_TOKEN: self._access_token,
                            CONF_METER_CARD_ID: selected_id,
                            CONF_METER_CARD_NAME: selected_card.get("cardName"),
                            CONF_METER_CARD_ADDRESS: selected_card.get("cardAddress"),
                            CONF_SCAN_INTERVAL: int(day_of_month),
                            CONF_SCAN_INTERVAL_UNIT: "month",
                        },
                    )

        data_schema = vol.Schema({
            vol.Required(CONF_METER_CARD_ID): vol.In(meter_options),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=DEFAULT_SCAN_INTERVAL_VALUE,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
        })

        return self.async_show_form(
            step_id="select_meter",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hint": "选择水表并设置每月几号更新数据（1-31）"},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 支持更换 Token 和水表"""
        reconfigure_entry = self._get_reconfigure_entry()
        if reconfigure_entry is None:
            return self.async_abort(reason="cannot_reconfigure")

        errors = {}

        if user_input is not None:
            access_token = user_input.get(CONF_ACCESS_TOKEN, "").strip()

            if access_token:
                try:
                    api = WenzhouWaterAPI(access_token)
                    user_info = await api.get_user_info()
                    if not user_info:
                        errors["base"] = "invalid_token"
                    else:
                        # 进入水表选择步骤
                        self._access_token = access_token
                        return await self.async_step_reconfigure_select_meter()
                except WenzhouWaterTokenExpiredError:
                    errors["base"] = "token_expired"
                except Exception as e:
                    _LOGGER.error(f"Token validation failed: {e}")
                    errors["base"] = "invalid_token"

        current_token = reconfigure_entry.data.get(CONF_ACCESS_TOKEN, "")

        reconfigure_schema = vol.Schema({
            vol.Required(
                CONF_ACCESS_TOKEN,
                default=current_token,
            ): str,
        })

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=reconfigure_schema,
            errors=errors,
        )

    async def async_step_reconfigure_select_meter(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 选择水表和更新日期"""
        reconfigure_entry = self._get_reconfigure_entry()
        errors = {}

        if not hasattr(self, "_access_token"):
            return self.async_abort(reason="missing_token")

        api = WenzhouWaterAPI(self._access_token)

        try:
            meter_cards = await api.get_meter_cards()
            if not meter_cards:
                errors["base"] = "no_meters"
                return self.async_show_form(step_id="reconfigure_select_meter", errors=errors)
        except Exception as e:
            _LOGGER.error(f"Failed to get meter cards: {e}")
            errors["base"] = "invalid_token"
            return self.async_show_form(step_id="reconfigure_select_meter", errors=errors)

        meter_options = {
            card["cardId"]: f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"
            for card in meter_cards
        }

        if user_input is not None:
            selected_id = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            validation_error = _validate_interval(int(day_of_month))
            if validation_error:
                errors[CONF_SCAN_INTERVAL] = validation_error
            elif selected_id:
                selected_card = next((c for c in meter_cards if c["cardId"] == selected_id), None)
                if selected_card:
                    final_data = {
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_METER_CARD_ID: selected_id,
                        CONF_METER_CARD_NAME: selected_card.get("cardName") if selected_card else None,
                        CONF_METER_CARD_ADDRESS: selected_card.get("cardAddress") if selected_card else None,
                        CONF_SCAN_INTERVAL: int(day_of_month),
                        CONF_SCAN_INTERVAL_UNIT: "month",
                    }
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data_updates=final_data,
                    )

        # 读取当前值
        current_card_id = reconfigure_entry.data.get(CONF_METER_CARD_ID)
        current_day = reconfigure_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

        data_schema = vol.Schema({
            vol.Required(
                CONF_METER_CARD_ID,
                default=current_card_id,
            ): vol.In(meter_options),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_day,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
        })

        return self.async_show_form(
            step_id="reconfigure_select_meter",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """获取选项流程"""
        return WenzhouWaterOptionsFlow(entry)


class WenzhouWaterOptionsFlow(OptionsFlow):
    """温州水务选项流程 - 修改更新日期"""

    async def async_step_init(self, user_input: dict[str, Any] = None) -> FlowResult:
        """配置每月更新日期"""
        errors = {}

        if user_input is not None:
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
            validation_error = _validate_interval(int(day_of_month))
            if validation_error:
                errors[CONF_SCAN_INTERVAL] = validation_error
            else:
                user_input[CONF_SCAN_INTERVAL_UNIT] = "month"
                return self.async_create_entry(title="", data=user_input)

        current_day = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
        )

        data_schema = vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_day,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hint": "设置每月几号更新数据（1-31）"},
        )
