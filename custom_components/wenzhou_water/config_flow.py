"""温州水务配置流程 - v1.3.3
修复:
  - 修复 OptionsFlow.__init__ 缺失导致 500 错误
  - 修复 OptionsFlow self.config_entry -> self.entry 拼写错误
  - 支持多用户/多水表：可选择监控所有水表或指定水表
  - 周期抓取改为数字输入框（1-31日）而非滑动条
"""
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .api import WenzhouWaterAPI, WenzhouWaterTokenExpiredError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
    CONF_METER_CARDS,
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

    VERSION = 3

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
        """选择水表并配置更新日期（支持多水表）"""
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
        # 构建选项：第一个为"全部水表"，后续为各水表
        meter_options = {"__all__": f"全部水表（共{len(meter_cards)}个）"}
        for card in meter_cards:
            meter_options[card["cardId"]] = f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"

        if user_input is not None:
            selected = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            validation_error = _validate_interval(int(day_of_month))
            if validation_error:
                errors[CONF_SCAN_INTERVAL] = validation_error
            elif selected:
                # 收集选中的水表列表
                if selected == "__all__":
                    selected_cards = [
                        {"cardId": c["cardId"], "cardName": c.get("cardName"), "cardAddress": c.get("cardAddress")}
                        for c in meter_cards
                    ]
                    title = f"温州水务（{len(selected_cards)}个水表）"
                else:
                    card = next((c for c in meter_cards if c["cardId"] == selected), None)
                    if card:
                        selected_cards = [{"cardId": card["cardId"], "cardName": card.get("cardName"), "cardAddress": card.get("cardAddress")}]
                        title = f"温州水务 - {card.get('cardName', selected)}"
                    else:
                        selected_cards = []

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_METER_CARDS: selected_cards,
                        CONF_SCAN_INTERVAL: int(day_of_month),
                        CONF_SCAN_INTERVAL_UNIT: "month",
                    },
                )

        data_schema = vol.Schema({
            vol.Required(CONF_METER_CARD_ID, default="__all__"): vol.In(meter_options),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=DEFAULT_SCAN_INTERVAL_VALUE,
            ): selector({"number": {"min": 1, "max": 31, "mode": "box"}}),
        })

        return self.async_show_form(
            step_id="select_meter",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hint": "设置每月{{day}}日自动更新数据（1-31日）"},
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
        """重新配置 - 选择水表和更新日期（支持多水表）"""
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

        self._meter_cards = meter_cards
        meter_options = {"__all__": f"全部水表（共{len(meter_cards)}个）"}
        for card in meter_cards:
            meter_options[card["cardId"]] = f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"

        if user_input is not None:
            selected = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            validation_error = _validate_interval(int(day_of_month))
            if validation_error:
                errors[CONF_SCAN_INTERVAL] = validation_error
            elif selected:
                if selected == "__all__":
                    selected_cards = [
                        {"cardId": c["cardId"], "cardName": c.get("cardName"), "cardAddress": c.get("cardAddress")}
                        for c in meter_cards
                    ]
                    title = f"温州水务（{len(selected_cards)}个水表）"
                else:
                    card = next((c for c in meter_cards if c["cardId"] == selected), None)
                    if card:
                        selected_cards = [{"cardId": card["cardId"], "cardName": card.get("cardName"), "cardAddress": card.get("cardAddress")}]
                        title = f"温州水务 - {card.get('cardName', selected)}"
                    else:
                        selected_cards = []

                final_data = {
                    CONF_ACCESS_TOKEN: self._access_token,
                    CONF_METER_CARDS: selected_cards,
                    CONF_SCAN_INTERVAL: int(day_of_month),
                    CONF_SCAN_INTERVAL_UNIT: "month",
                }
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=final_data,
                    title=title,
                )

        # 读取当前值
        current_cards = reconfigure_entry.data.get(CONF_METER_CARDS, [])
        current_day = reconfigure_entry.data.get(
            CONF_SCAN_INTERVAL,
            reconfigure_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
        )
        # 兼容旧格式
        if isinstance(current_cards, list) and len(current_cards) > 0:
            if len(current_cards) == len(meter_cards):
                current_selection = "__all__"
            else:
                current_selection = current_cards[0].get("cardId", "__all__") if current_cards else "__all__"
        else:
            current_selection = "__all__"

        data_schema = vol.Schema({
            vol.Required(CONF_METER_CARD_ID, default=current_selection): vol.In(meter_options),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_day,
            ): selector({"number": {"min": 1, "max": 31, "mode": "box"}}),
        })

        return self.async_show_form(
            step_id="reconfigure_select_meter",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hint": "设置每月{{day}}日自动更新数据（1-31日）"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """获取选项流程"""
        return WenzhouWaterOptionsFlow(entry)


class WenzhouWaterOptionsFlow(OptionsFlow):
    """温州水务选项流程 - 修改更新日期"""

    def __init__(self, entry: ConfigEntry):
        """初始化选项流程"""
        self.entry = entry

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

        current_day = self.entry.options.get(
            CONF_SCAN_INTERVAL,
            self.entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
        )

        data_schema = vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_day,
            ): selector({"number": {"min": 1, "max": 31, "mode": "box"}}),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hint": "设置每月{{day}}日自动更新数据（1-31日）"},
        )
