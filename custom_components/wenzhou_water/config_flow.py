"""温州水务配置流程 - v2.1.0
v2.1.0:
  - 恢复手动 Token 登录方式（SMS 登录获取的 token 无法访问数据 API）
  - 第一步选择登录方式：短信验证码登录 / 手动输入 Token
v2.0.4:
  - 移除 get_user_info 验证（SMS token 对该接口返回 401，导致误报 invalid_code）
v2.0.3:
  - 修复 async_show_form 的 description 参数在 HA 2026.4.3 中不支持导致的 500 错误
v2.0.0:
  - 取消手动 Token 登录方式，仅支持短信验证码登录（有缺陷，SMS token 无数据权限）
v1.9.0:
  - 新增短信验证码登录方式（手机号+验证码）
  - 配置界面第一步选择登录方式：手机号登录 / 手动Token
"""
import re
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .api import WenzhouWaterAPI, WenzhouWaterSMSLogin, WenzhouWaterAPIError, WenzhouWaterTokenExpiredError
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

# 短信登录常量
CONF_MOBILE = "mobile"
CONF_SMS_CODE = "sms_code"
CONF_VERIFY_ID = "verify_id"
CONF_LOGIN_METHOD = "login_method"

LOGIN_SMS = "sms"
LOGIN_TOKEN = "token"


def _validate_interval(value: int) -> str | None:
    """验证月模式数值（1-31）"""
    if not 1 <= value <= 31:
        return "每月几号更新？请输入 1-31"
    return None


def _validate_mobile(value: str) -> str | None:
    """验证手机号格式"""
    if not value:
        return "请输入手机号"
    cleaned = re.sub(r"[\s\-]", "", value)
    if not re.match(r"^1\d{10}$", cleaned):
        return "请输入正确的手机号（11位数字）"
    return None


def _validate_sms_code(value: str) -> str | None:
    """验证短信验证码格式"""
    if not value:
        return "请输入验证码"
    if not re.match(r"^\d{6}$", value.strip()):
        return "验证码为6位数字"
    return None


class WenzhouWaterConfigFlow(ConfigFlow, domain="wenzhou_water"):
    """温州水务配置流程"""

    VERSION = 4

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """第一步：选择登录方式"""
        if user_input is not None:
            method = user_input.get(CONF_LOGIN_METHOD)
            if method == LOGIN_SMS:
                return await self.async_step_sms()
            elif method == LOGIN_TOKEN:
                return await self.async_step_manual_token()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LOGIN_METHOD, default=LOGIN_TOKEN): selector({
                    "select": {
                        "options": [
                            {"value": LOGIN_TOKEN, "label": "手动输入 Token（抓包获取）"},
                            {"value": LOGIN_SMS, "label": "短信验证码登录"},
                        ],
                        "mode": "list",
                    }
                }),
            }),
        )

    async def async_step_manual_token(self, user_input: dict[str, Any] = None) -> FlowResult:
        """手动输入 Access Token"""
        errors = {}

        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            if not token:
                errors[CONF_ACCESS_TOKEN] = "请输入 Access Token"
            elif len(token) < 20:
                errors[CONF_ACCESS_TOKEN] = "Token 格式不正确，长度过短"
            else:
                # 验证 Token 是否有效：尝试获取水表信息
                api = WenzhouWaterAPI(token)
                try:
                    meter_cards = await api.get_meter_cards()
                    if not meter_cards:
                        errors["base"] = "no_meters"
                    else:
                        await self.async_set_unique_id(token[:16])
                        self._access_token = token
                        return await self.async_step_select_meter()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"Token 验证失败: {e}")
                    errors["base"] = "invalid_token"
                except Exception as e:
                    _LOGGER.error(f"Token 验证异常: {e}")
                    errors["base"] = "invalid_token"

        return self.async_show_form(
            step_id="manual_token",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCESS_TOKEN): str,
            }),
            errors=errors,
        )

    async def async_step_sms(self, user_input: dict[str, Any] = None) -> FlowResult:
        """短信验证码登录 - 输入手机号"""
        errors = {}

        if user_input is not None:
            mobile = re.sub(r"[\s\-]", "", user_input.get(CONF_MOBILE, ""))
            validation_error = _validate_mobile(mobile)
            if validation_error:
                errors[CONF_MOBILE] = validation_error
            else:
                try:
                    verify_id = await WenzhouWaterSMSLogin.send_sms_code(mobile)
                    self._mobile = mobile
                    self._verify_id = verify_id
                    return await self.async_step_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors["base"] = "sms_send_failed"

        return self.async_show_form(
            step_id="sms",
            data_schema=vol.Schema({
                vol.Required(CONF_MOBILE): str,
            }),
            errors=errors,
        )

    async def async_step_sms_verify(self, user_input: dict[str, Any] = None) -> FlowResult:
        """短信验证码登录 - 输入验证码"""
        errors = {}

        if user_input is not None:
            code = user_input.get(CONF_SMS_CODE, "").strip()
            validation_error = _validate_sms_code(code)
            if validation_error:
                errors[CONF_SMS_CODE] = validation_error
            else:
                try:
                    result = await WenzhouWaterSMSLogin.login_with_sms(
                        self._mobile, code, self._verify_id
                    )
                    access_token = result.get("authToken")
                    if not access_token:
                        errors["base"] = "login_failed"
                    else:
                        # SMS 登录获取的 token 可能无法访问数据 API
                        # 先尝试获取水表信息验证
                        api = WenzhouWaterAPI(access_token)
                        try:
                            meter_cards = await api.get_meter_cards()
                            if meter_cards:
                                await self.async_set_unique_id(access_token[:16])
                                self._access_token = access_token
                                return await self.async_step_select_meter()
                            else:
                                errors["base"] = "no_meters"
                        except Exception:
                            _LOGGER.warning("SMS token 无法获取水表数据，请使用手动 Token 方式")
                            errors["base"] = "sms_token_invalid"
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"SMS login failed: {e}")
                    errors["base"] = "invalid_code"

        return self.async_show_form(
            step_id="sms_verify",
            data_schema=vol.Schema({
                vol.Required(CONF_SMS_CODE): str,
            }),
            errors=errors,
            description_placeholders={"mobile": self._mobile[:3] + "****" + self._mobile[7:]},
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

    # === 重新配置流程 ===

    async def async_step_reconfigure(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 同样支持两种登录方式"""
        reconfigure_entry = self._get_reconfigure_entry()
        if reconfigure_entry is None:
            return self.async_abort(reason="cannot_reconfigure")

        if user_input is not None:
            method = user_input.get(CONF_LOGIN_METHOD)
            if method == LOGIN_TOKEN:
                return await self.async_step_reconfigure_manual_token()
            elif method == LOGIN_SMS:
                return await self.async_step_reconfigure_sms()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_LOGIN_METHOD, default=LOGIN_TOKEN): selector({
                    "select": {
                        "options": [
                            {"value": LOGIN_TOKEN, "label": "手动输入 Token（抓包获取）"},
                            {"value": LOGIN_SMS, "label": "短信验证码登录"},
                        ],
                        "mode": "list",
                    }
                }),
            }),
        )

    async def async_step_reconfigure_manual_token(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 手动输入 Token"""
        errors = {}

        if user_input is not None:
            token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            if not token:
                errors[CONF_ACCESS_TOKEN] = "请输入 Access Token"
            elif len(token) < 20:
                errors[CONF_ACCESS_TOKEN] = "Token 格式不正确"
            else:
                api = WenzhouWaterAPI(token)
                try:
                    meter_cards = await api.get_meter_cards()
                    if not meter_cards:
                        errors["base"] = "no_meters"
                    else:
                        self._access_token = token
                        return await self.async_step_reconfigure_select_meter()
                except Exception as e:
                    _LOGGER.error(f"Token 验证失败: {e}")
                    errors["base"] = "invalid_token"

        return self.async_show_form(
            step_id="reconfigure_manual_token",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCESS_TOKEN): str,
            }),
            errors=errors,
        )

    async def async_step_reconfigure_sms(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 短信验证码"""
        errors = {}

        if user_input is not None:
            mobile = re.sub(r"[\s\-]", "", user_input.get(CONF_MOBILE, ""))
            validation_error = _validate_mobile(mobile)
            if validation_error:
                errors[CONF_MOBILE] = validation_error
            else:
                try:
                    verify_id = await WenzhouWaterSMSLogin.send_sms_code(mobile)
                    self._mobile = mobile
                    self._verify_id = verify_id
                    return await self.async_step_reconfigure_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors["base"] = "sms_send_failed"

        return self.async_show_form(
            step_id="reconfigure_sms",
            data_schema=vol.Schema({
                vol.Required(CONF_MOBILE): str,
            }),
            errors=errors,
        )

    async def async_step_reconfigure_sms_verify(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - SMS 验证码验证"""
        errors = {}

        if user_input is not None:
            code = user_input.get(CONF_SMS_CODE, "").strip()
            validation_error = _validate_sms_code(code)
            if validation_error:
                errors[CONF_SMS_CODE] = validation_error
            else:
                try:
                    result = await WenzhouWaterSMSLogin.login_with_sms(
                        self._mobile, code, self._verify_id
                    )
                    access_token = result.get("authToken")
                    if access_token:
                        self._access_token = access_token
                        return await self.async_step_reconfigure_select_meter()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"SMS login failed: {e}")
                    errors["base"] = "invalid_code"

        return self.async_show_form(
            step_id="reconfigure_sms_verify",
            data_schema=vol.Schema({
                vol.Required(CONF_SMS_CODE): str,
            }),
            errors=errors,
            description_placeholders={"mobile": self._mobile[:3] + "****" + self._mobile[7:]},
        )

    async def async_step_reconfigure_select_meter(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 选择水表"""
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

        current_cards = reconfigure_entry.data.get(CONF_METER_CARDS, [])
        current_day = reconfigure_entry.data.get(
            CONF_SCAN_INTERVAL,
            reconfigure_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
        )
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
    async def async_migrate_entry(hass, config_entry):
        """迁移配置到新版本"""
        _LOGGER.debug("Migration from VERSION 3 to 4 - no changes needed")
        return config_entry

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """获取选项流程"""
        return WenzhouWaterOptionsFlow(entry)


class WenzhouWaterOptionsFlow(OptionsFlow):
    """温州水务选项流程 - 修改更新日期"""

    def __init__(self, entry: ConfigEntry):
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
