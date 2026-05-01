"""温州水务配置流程 - v3.0.0

v3.0.0: 在 v2.1.1 基础上补充南网（wz_water_sg）特性
  - async_show_menu 选择登录方式（替代 selector）
  - 新增微信扫码登录（微信服务器 <img> 方式，移除 segno 依赖）
  - _abort_if_unique_id_configured() 防重复添加
  - reconfigure 流程也支持微信扫码
  - ConfigFlow VERSION 4 → 5
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
    DEFAULT_SCAN_INTERVAL_VALUE,
    DEFAULT_SCAN_INTERVAL_UNIT,
    CONF_MOBILE,
    CONF_SMS_CODE,
    CONF_LOGIN_TYPE,
    CONF_REFRESH_QR_CODE,
    CONF_GENERAL_ERROR,
    STEP_USER,
    STEP_SMS_LOGIN,
    STEP_SMS_VERIFY,
    STEP_WX_QR_LOGIN,
    STEP_QR_LOGIN,
    STEP_SELECT_METER,
    STEP_RECONFIGURE,
    STEP_RECONFIGURE_SMS,
    STEP_RECONFIGURE_SMS_VERIFY,
    STEP_RECONFIGURE_QR,
    STEP_RECONFIGURE_SELECT_METER,
    LOGIN_SMS,
    LOGIN_WECHAT,
    LOGIN_TOKEN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_QR_NOT_SCANNED,
    ERROR_SCAN_EXPIRED,
    ERROR_TOKEN_FAILED,
    ERROR_UNKNOWN,
)
from .wechat_auth import async_start_weixin_login, WechatLoginResult

_LOGGER = logging.getLogger(__name__)

WX_POLL_URL = "https://lp.open.weixin.qq.com/connect/l/qrconnect"


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


def _mask_mobile(mobile: str) -> str:
    return mobile[:3] + "****" + mobile[7:]


async def _check_scan_once(session) -> WechatLoginResult:
    """单次检查微信扫码状态"""
    import aiohttp
    import re as _re

    poll_url = f"{WX_POLL_URL}?uuid={session.uuid}&_=0"
    headers = {"User-Agent": "Mozilla/5.0 Chrome/132"}
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                poll_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                text = await resp.text()

        # 扫码成功
        m = _re.search(r"window\.wx_code='([^']+)'", text)
        if m and m.group(1):
            code = m.group(1)
            from .wechat_auth import _async_wx_to_token
            token = await _async_wx_to_token(code)
            if token:
                return WechatLoginResult(success=True, token=token, message="登录成功")
            return WechatLoginResult(success=False, message="token_failed")

        # 二维码过期
        err_m = _re.search(r"window\.wx_errcode=(\d+)", text)
        if err_m and int(err_m.group(1)) == 400:
            return WechatLoginResult(success=False, message="expired")

    except Exception as e:
        _LOGGER.warning(f"检查微信扫码状态异常: {e}")

    return WechatLoginResult(success=False, message="scan_waiting")


class WenzhouWaterConfigFlow(ConfigFlow, domain="wenzhou_water"):
    """温州水务配置流程 - v3.0.0"""

    VERSION = 5

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """获取选项流程"""
        return WenzhouWaterOptionsFlow(entry)

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """选择登录方式（async_show_menu 方式）"""
        return self.async_show_menu(
            step_id=STEP_USER,
            menu_options=[
                STEP_SMS_LOGIN,
                STEP_WX_QR_LOGIN,
            ],
        )

    # ========== 短信登录 ==========

    async def async_step_sms_login(self, user_input: dict[str, Any] = None) -> FlowResult:
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
                    self._login_type = LOGIN_SMS
                    return await self.async_step_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors[CONF_GENERAL_ERROR] = ERROR_CANNOT_CONNECT

        return self.async_show_form(
            step_id=STEP_SMS_LOGIN,
            data_schema=vol.Schema({
                vol.Required(CONF_MOBILE): str,
            }),
            errors=errors,
        )

    async def async_step_sms_verify(self, user_input: dict[str, Any] = None) -> FlowResult:
        """短信验证码登录 - 输入验证码"""
        errors = {}
        schema = vol.Schema({vol.Required(CONF_SMS_CODE): str})

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
                        errors[CONF_GENERAL_ERROR] = ERROR_INVALID_AUTH
                    else:
                        # SMS 登录获取的 token 可能无法访问数据 API，先验证
                        api = WenzhouWaterAPI(access_token)
                        try:
                            meter_cards = await api.get_meter_cards()
                            if meter_cards:
                                await self.async_set_unique_id(access_token[:16])
                                self._abort_if_unique_id_configured()
                                self._access_token = access_token
                                return await self.async_step_select_meter()
                            else:
                                errors[CONF_GENERAL_ERROR] = "no_meters"
                        except Exception:
                            _LOGGER.warning("SMS token 无法获取水表数据，请使用微信扫码方式")
                            errors[CONF_GENERAL_ERROR] = "sms_token_invalid"
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"SMS login failed: {e}")
                    errors[CONF_GENERAL_ERROR] = ERROR_INVALID_AUTH

        return self.async_show_form(
            step_id=STEP_SMS_VERIFY,
            data_schema=schema,
            errors=errors,
            description_placeholders={"phone": _mask_mobile(self._mobile)},
        )

    # ========== 微信扫码登录 ==========

    async def async_step_wx_qr_login(self, user_input: dict[str, Any] = None) -> FlowResult:
        """微信扫码登录入口"""
        self._login_type = LOGIN_WECHAT
        return await self.async_step_qr_login()

    async def async_step_qr_login(self, user_input: dict[str, Any] = None) -> FlowResult:
        """微信扫码登录 - 显示二维码 + 验证"""
        if user_input is None:
            return await self._show_qr_form()

        if user_input.get(CONF_REFRESH_QR_CODE):
            return await self._show_qr_form()

        return await self._validate_qr_login()

    async def _show_qr_form(self) -> FlowResult:
        """显示二维码表单"""
        try:
            self._wechat_session = await async_start_weixin_login()
            qr_image_url = self._wechat_session.qrcode_image_url
        except Exception as e:
            _LOGGER.error(f"二维码获取失败: {e}")
            return self.async_show_form(
                step_id=STEP_QR_LOGIN,
                data_schema=vol.Schema(
                    {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
                ),
                errors={CONF_GENERAL_ERROR: ERROR_CANNOT_CONNECT},
                description_placeholders={
                    "description": "<p>二维码获取失败，请重试。</p>",
                },
            )

        return self.async_show_form(
            step_id=STEP_QR_LOGIN,
            data_schema=vol.Schema(
                {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
            ),
            description_placeholders={
                "description": (
                    f"<p>请使用微信扫描下方二维码进行授权：</p>"
                    f'<p><img src="{qr_image_url}" alt="微信二维码" style="width: 200px;"/></p>'
                    f"<p>授权完成后，点击「提交」继续。</p>"
                ),
            },
        )

    async def _validate_qr_login(self) -> FlowResult:
        """验证扫码结果"""
        if not hasattr(self, "_wechat_session") or self._wechat_session is None:
            return await self._show_qr_form()

        errors = {}
        try:
            result = await _check_scan_once(self._wechat_session)
            if result.success and result.token:
                self._access_token = result.token
                await self.async_set_unique_id(result.token[:16])
                self._abort_if_unique_id_configured()
                return await self.async_step_select_meter()
            elif result.message == "expired":
                errors[CONF_GENERAL_ERROR] = ERROR_SCAN_EXPIRED
            elif result.message == "token_failed":
                errors[CONF_GENERAL_ERROR] = ERROR_TOKEN_FAILED
            else:
                errors[CONF_GENERAL_ERROR] = ERROR_QR_NOT_SCANNED
        except Exception as e:
            _LOGGER.exception(f"扫码验证异常: {e}")
            errors[CONF_GENERAL_ERROR] = ERROR_UNKNOWN

        qr_image_url = self._wechat_session.qrcode_image_url if hasattr(self, "_wechat_session") and self._wechat_session else ""
        return self.async_show_form(
            step_id=STEP_QR_LOGIN,
            data_schema=vol.Schema(
                {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
            ),
            errors=errors,
            description_placeholders={
                "description": (
                    f"<p>请使用微信扫描下方二维码进行授权：</p>"
                    f'<p><img src="{qr_image_url}" alt="微信二维码" style="width: 200px;"/></p>'
                    f"<p>授权完成后，点击「提交」继续。</p>"
                ),
            },
        )

    # ========== 选择水表 ==========

    async def async_step_select_meter(self, user_input: dict[str, Any] = None) -> FlowResult:
        """选择水表并配置更新日期（支持多水表）"""
        errors = {}

        if not hasattr(self, "_access_token"):
            return self.async_show_form(step_id=STEP_USER, errors={CONF_GENERAL_ERROR: "missing_token"})

        api = WenzhouWaterAPI(self._access_token)

        try:
            meter_cards = await api.get_meter_cards()
            if not meter_cards:
                errors[CONF_GENERAL_ERROR] = "no_meters"
                return self.async_show_form(step_id=STEP_USER, errors=errors)
        except Exception as e:
            _LOGGER.error(f"Failed to get meter cards: {e}")
            errors[CONF_GENERAL_ERROR] = ERROR_CANNOT_CONNECT
            return self.async_show_form(step_id=STEP_USER, errors=errors)

        self._meter_cards = meter_cards
        meter_options = {"__all__": f"全部水表（共{len(meter_cards)}个）"}
        for card in meter_cards:
            meter_options[card["cardId"]] = f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"

        if user_input is not None:
            selected = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            if not 1 <= int(day_of_month) <= 31:
                errors[CONF_SCAN_INTERVAL] = "请输入1-31"
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
                        CONF_LOGIN_TYPE: getattr(self, "_login_type", LOGIN_TOKEN),
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
            step_id=STEP_SELECT_METER,
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"day": str(DEFAULT_SCAN_INTERVAL_VALUE)},
        )

    # ========== 重新配置流程 ==========

    async def async_step_reconfigure(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 选择登录方式（async_show_menu）"""
        return self.async_show_menu(
            step_id=STEP_RECONFIGURE,
            menu_options=[
                STEP_RECONFIGURE_SMS,
                STEP_RECONFIGURE_QR,
            ],
        )

    # --- 重新配置：短信登录 ---

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
                    self._login_type = LOGIN_SMS
                    return await self.async_step_reconfigure_sms_verify()
                except WenzhouWaterAPIError as e:
                    _LOGGER.error(f"发送验证码失败: {e}")
                    errors[CONF_GENERAL_ERROR] = ERROR_CANNOT_CONNECT

        return self.async_show_form(
            step_id=STEP_RECONFIGURE_SMS,
            data_schema=vol.Schema({
                vol.Required(CONF_MOBILE): str,
            }),
            errors=errors,
        )

    async def async_step_reconfigure_sms_verify(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - SMS 验证码验证"""
        errors = {}
        schema = vol.Schema({vol.Required(CONF_SMS_CODE): str})

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
                    errors[CONF_GENERAL_ERROR] = ERROR_INVALID_AUTH

        return self.async_show_form(
            step_id=STEP_RECONFIGURE_SMS_VERIFY,
            data_schema=schema,
            errors=errors,
            description_placeholders={"phone": _mask_mobile(self._mobile)},
        )

    # --- 重新配置：微信扫码 ---

    async def async_step_reconfigure_qr(self, user_input: dict[str, Any] = None) -> FlowResult:
        """重新配置 - 微信扫码登录"""
        self._login_type = LOGIN_WECHAT

        if user_input is None:
            return await self._show_reconfigure_qr_form()

        if user_input.get(CONF_REFRESH_QR_CODE):
            return await self._show_reconfigure_qr_form()

        return await self._validate_reconfigure_qr_login()

    async def _show_reconfigure_qr_form(self) -> FlowResult:
        """重新配置 - 显示二维码表单"""
        try:
            self._wechat_session = await async_start_weixin_login()
            qr_image_url = self._wechat_session.qrcode_image_url
        except Exception as e:
            _LOGGER.error(f"二维码获取失败: {e}")
            return self.async_show_form(
                step_id=STEP_RECONFIGURE_QR,
                data_schema=vol.Schema(
                    {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
                ),
                errors={CONF_GENERAL_ERROR: ERROR_CANNOT_CONNECT},
                description_placeholders={
                    "description": "<p>二维码获取失败，请重试。</p>",
                },
            )

        return self.async_show_form(
            step_id=STEP_RECONFIGURE_QR,
            data_schema=vol.Schema(
                {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
            ),
            description_placeholders={
                "description": (
                    f"<p>请使用微信扫描下方二维码进行授权：</p>"
                    f'<p><img src="{qr_image_url}" alt="微信二维码" style="width: 200px;"/></p>'
                    f"<p>授权完成后，点击「提交」继续。</p>"
                ),
            },
        )

    async def _validate_reconfigure_qr_login(self) -> FlowResult:
        """重新配置 - 验证扫码结果"""
        if not hasattr(self, "_wechat_session") or self._wechat_session is None:
            return await self._show_reconfigure_qr_form()

        errors = {}
        try:
            result = await _check_scan_once(self._wechat_session)
            if result.success and result.token:
                self._access_token = result.token
                return await self.async_step_reconfigure_select_meter()
            elif result.message == "expired":
                errors[CONF_GENERAL_ERROR] = ERROR_SCAN_EXPIRED
            elif result.message == "token_failed":
                errors[CONF_GENERAL_ERROR] = ERROR_TOKEN_FAILED
            else:
                errors[CONF_GENERAL_ERROR] = ERROR_QR_NOT_SCANNED
        except Exception as e:
            _LOGGER.exception(f"扫码验证异常: {e}")
            errors[CONF_GENERAL_ERROR] = ERROR_UNKNOWN

        qr_image_url = self._wechat_session.qrcode_image_url if hasattr(self, "_wechat_session") and self._wechat_session else ""
        return self.async_show_form(
            step_id=STEP_RECONFIGURE_QR,
            data_schema=vol.Schema(
                {vol.Required(CONF_REFRESH_QR_CODE, default=False): bool}
            ),
            errors=errors,
            description_placeholders={
                "description": (
                    f"<p>请使用微信扫描下方二维码进行授权：</p>"
                    f'<p><img src="{qr_image_url}" alt="微信二维码" style="width: 200px;"/></p>'
                    f"<p>授权完成后，点击「提交」继续。</p>"
                ),
            },
        )

    # --- 重新配置：选择水表 ---

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
                errors[CONF_GENERAL_ERROR] = "no_meters"
                return self.async_show_form(step_id=STEP_RECONFIGURE_SELECT_METER, errors=errors)
        except Exception as e:
            _LOGGER.error(f"Failed to get meter cards: {e}")
            errors[CONF_GENERAL_ERROR] = ERROR_CANNOT_CONNECT
            return self.async_show_form(step_id=STEP_RECONFIGURE_SELECT_METER, errors=errors)

        self._meter_cards = meter_cards
        meter_options = {"__all__": f"全部水表（共{len(meter_cards)}个）"}
        for card in meter_cards:
            meter_options[card["cardId"]] = f"{card.get('cardName', '未知')} - {card.get('cardAddress', '未知地址')}"

        if user_input is not None:
            selected = user_input.get(CONF_METER_CARD_ID)
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)

            if not 1 <= int(day_of_month) <= 31:
                errors[CONF_SCAN_INTERVAL] = "请输入1-31"
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
                    CONF_LOGIN_TYPE: getattr(self, "_login_type", LOGIN_TOKEN),
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
            step_id=STEP_RECONFIGURE_SELECT_METER,
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"day": str(DEFAULT_SCAN_INTERVAL_VALUE)},
        )


class WenzhouWaterOptionsFlow(OptionsFlow):
    """温州水务选项流程 - 修改更新日期"""

    def __init__(self, entry: ConfigEntry):
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] = None) -> FlowResult:
        """配置每月更新日期"""
        errors = {}

        if user_input is not None:
            day_of_month = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE)
            if not 1 <= int(day_of_month) <= 31:
                errors[CONF_SCAN_INTERVAL] = "请输入1-31"
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
            description_placeholders={"day": str(DEFAULT_SCAN_INTERVAL_VALUE)},
        )
