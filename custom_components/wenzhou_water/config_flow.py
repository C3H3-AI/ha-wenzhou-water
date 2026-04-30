"""温州水务配置流程 - v2.0.0
v2.0.0:
  - 取消手动 Token 登录方式，仅支持短信验证码登录
  - 简化配置流程，直接进入手机号输入步骤
v1.9.0:
  - 新增短信验证码登录方式（手机号+验证码）
  - 配置界面第一步选择登录方式：手机号登录 / 手动Token
  - Token过期后自动提示用户重新登录
v1.8.0:
  - 配置界面添加描述文案，提升用户引导体验
  - Token 步骤：说明 Token 获取方式
  - 水表选择步骤：说明轮询时间（每月 N 日 08:00）
  - 选项配置步骤：说明修改后的生效时机
v1.6.0:
  - 修复 OptionsFlow.__init__ 缺失导致 500 错误
  - 修复 OptionsFlow self.config_entry -> self.entry 拼写错误
  - 支持多用户/多水表：可选择监控所有水表或指定水表
  - 周期抓取改为数字输入框（1-31日）而非滑动条
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


def _validate_interval(value: int) -> str | None:
    """验证月模式数值（1-31）"""
    if not 1 <= value <= 31:
        return "每月几号更新？请输入 1-31"
    return None


def _validate_mobile(value: str) -> str | None:
    """验证手机号格式"""
    if not value:
        return "请输入手机号"
    # 移除空格和短横线
    cleaned = re.sub(r"[\s\-]", "", value)
    # 验证中国手机号格式（1开头的11位数字）
    if not re.match(r"^1\d{10}$", cleaned):
        return "请输入正确的手机号（11位数字）"
    return None


def _validate_sms_code(value: str) -> str | None:
    """验证短信验证码格式"""
    if not value:
        return "请输入验证码"
    # 6位数字
    if not re.match(r"^\d{6}$", value.strip()):
        return "验证码为6位数字"
    return None


class WenzhouWaterConfigFlow(ConfigFlow, domain="wenzhou_water"):
    """温州水务配置流程"""

    VERSION = 4

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """第一步：输入手机号（短信验证码登录）"""
        errors = {}

        if user_input is not None:
            mobile = re.sub(r"[\s\-]", "", user_input.get(CONF_MOBILE, ""))
            validation_error = _validate_mobile(mobile)
            if validation_error:
                errors[CONF_MOBILE] = validation_error
            else:
                try:
                    # 发送验证码
                    verify_id = await WenzhouWaterSMSLogin.send_sms_code(mobile)
                    # 保存手机号和验证码ID，进入验证步骤
                    self._mobile = mobile
                    self._verify_id = verify_id
                    return await self.async_step_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors["base"] = "sms_send_failed"

        data_schema = vol.Schema({
            vol.Required(CONF_MOBILE): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description="请输入注册在水务账户的手机号\n\n点击下一步后将向该手机号发送验证码短信",
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
                    # 验证验证码并登录
                    result = await WenzhouWaterSMSLogin.login_with_sms(
                        self._mobile, code, self._verify_id
                    )
                    access_token = result.get("authToken")
                    if not access_token:
                        errors["base"] = "login_failed"
                    else:
                        # 验证Token是否有效
                        api = WenzhouWaterAPI(access_token)
                        user_info = await api.get_user_info()
                        if not user_info:
                            errors["base"] = "login_failed"
                        else:
                            await self.async_set_unique_id(access_token[:16])
                            self._access_token = access_token
                            return await self.async_step_select_meter()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"SMS login failed: {e}")
                    errors["base"] = "invalid_code"

        data_schema = vol.Schema({
            vol.Required(CONF_SMS_CODE): str,
        })

        return self.async_show_form(
            step_id="sms_verify",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"mobile": self._mobile[:3] + "****" + self._mobile[7:]},
            description="验证码已发送至 **{{mobile}}**\n\n请输入收到的6位短信验证码",
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
            description="{{hint}}\n\n轮询说明：数据将在每月该日期的 08:00 自动刷新，无需手动操作。",
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 使用短信验证码重新登录"""
        reconfigure_entry = self._get_reconfigure_entry()
        if reconfigure_entry is None:
            return self.async_abort(reason="cannot_reconfigure")

        errors = {}

        if user_input is not None:
            mobile = re.sub(r"[\s\-]", "", user_input.get(CONF_MOBILE, ""))
            validation_error = _validate_mobile(mobile)
            if validation_error:
                errors[CONF_MOBILE] = validation_error
            else:
                try:
                    # 发送验证码
                    verify_id = await WenzhouWaterSMSLogin.send_sms_code(mobile)
                    self._mobile = mobile
                    self._verify_id = verify_id
                    return await self.async_step_reconfigure_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors["base"] = "sms_send_failed"

        data_schema = vol.Schema({
            vol.Required(CONF_MOBILE): str,
        })

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
            description="请输入注册在水务账户的手机号以重新验证\n\n点击下一步后将向该手机号发送验证码短信",
        )

    async def async_step_reconfigure_sms_verify(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 验证短信验证码"""
        reconfigure_entry = self._get_reconfigure_entry()
        errors = {}

        if user_input is not None:
            code = user_input.get(CONF_SMS_CODE, "").strip()
            validation_error = _validate_sms_code(code)
            if validation_error:
                errors[CONF_SMS_CODE] = validation_error
            else:
                try:
                    # 验证验证码并登录
                    result = await WenzhouWaterSMSLogin.login_with_sms(
                        self._mobile, code, self._verify_id
                    )
                    access_token = result.get("authToken")
                    if not access_token:
                        errors["base"] = "login_failed"
                    else:
                        # 验证Token是否有效
                        api = WenzhouWaterAPI(access_token)
                        user_info = await api.get_user_info()
                        if not user_info:
                            errors["base"] = "login_failed"
                        else:
                            self._access_token = access_token
                            return await self.async_step_reconfigure_select_meter()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"SMS login failed: {e}")
                    errors["base"] = "invalid_code"

        data_schema = vol.Schema({
            vol.Required(CONF_SMS_CODE): str,
        })

        return self.async_show_form(
            step_id="reconfigure_sms_verify",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"mobile": self._mobile[:3] + "****" + self._mobile[7:]},
            description="验证码已发送至 **{{mobile}}**\n\n请输入收到的6位短信验证码",
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
            description="{{hint}}\n\n轮询说明：数据将在每月该日期的 08:00 自动刷新，无需手动操作。",
        )

    @staticmethod
    async def async_migrate_entry(hass, config_entry):
        """迁移配置到新版本"""
        # v2.0.0 只是简化了登录流程，数据结构没有变化
        # VERSION 3 -> 4 无需数据迁移
        return True

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
            description="{{hint}}\n\n修改后，下次轮询将按照新的日期执行。",
        )
