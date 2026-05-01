"""温州水务配置流程 - v5.0.0

v5.0.0: 基于 wz_water_sg 架构重写
  - async_show_menu 选择登录方式（替代 selector）
  - 微信扫码使用微信服务器图片 URL（替代 segno 生成）
  - 独立 async_step_qr_login + _validate_qr_login
  - 移除 segno 依赖
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GENERAL_ERROR,
    CONF_LOGIN_TYPE,
    CONF_METER_CARD_ID,
    CONF_METER_CARDS,
    CONF_MOBILE,
    CONF_REFRESH_QR_CODE,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_UNIT,
    CONF_SMS_CODE,
    DEFAULT_SCAN_INTERVAL_VALUE,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_QR_NOT_SCANNED,
    ERROR_SCAN_EXPIRED,
    ERROR_TOKEN_FAILED,
    ERROR_UNKNOWN,
    LOGIN_SMS,
    LOGIN_WECHAT,
    STEP_QR_LOGIN,
    STEP_SELECT_METER,
    STEP_SMS_LOGIN,
    STEP_SMS_VERIFY,
    STEP_USER,
    STEP_WX_QR_LOGIN,
)
from .api import WenzhouWaterAPI, WenzhouWaterSMSLogin, WenzhouWaterAPIError
from .wechat_auth import async_start_weixin_login, WechatLoginResult

_LOGGER = logging.getLogger(__name__)

WX_POLL_URL = "https://lp.open.weixin.qq.com/connect/l/qrconnect"


class WenzhouWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """温州水务配置流程 - 基于 wz_water_sg 架构"""

    VERSION = 5

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WenzhouWaterOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """选择登录方式"""
        return self.async_show_menu(
            step_id=STEP_USER,
            menu_options=[
                STEP_SMS_LOGIN,
                STEP_WX_QR_LOGIN,
            ],
        )

    # ========== 短信登录 ==========

    async def async_step_sms_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """短信登录 - 输入手机号"""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_SMS_LOGIN,
                data_schema=vol.Schema({
                    vol.Required(CONF_MOBILE): vol.All(str, vol.Length(min=11, max=11))
                }),
            )
        mobile = re.sub(r"[\s\-]", "", user_input[CONF_MOBILE])
        if not re.match(r"^1\d{10}$", mobile):
            return self.async_show_form(
                step_id=STEP_SMS_LOGIN,
                data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
                errors={CONF_MOBILE: "请输入正确的11位手机号"},
            )
        self._mobile = mobile
        self._login_type = LOGIN_SMS
        try:
            self._verify_id = await WenzhouWaterSMSLogin.send_sms_code(mobile)
        except WenzhouWaterAPIError:
            return self.async_show_form(
                step_id=STEP_SMS_LOGIN,
                data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
                errors={CONF_GENERAL_ERROR: ERROR_CANNOT_CONNECT},
            )
        return await self.async_step_sms_verify()

    async def async_step_sms_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """短信登录 - 输入验证码"""
        schema = vol.Schema({
            vol.Required(CONF_SMS_CODE): vol.All(str, vol.Length(min=6, max=6))
        })
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_SMS_VERIFY,
                data_schema=schema,
                description_placeholders={"phone": _mask_mobile(self._mobile)},
            )

        code = user_input[CONF_SMS_CODE].strip()
        if not re.match(r"^\d{6}$", code):
            return self.async_show_form(
                step_id=STEP_SMS_VERIFY,
                data_schema=schema,
                errors={CONF_SMS_CODE: "请输入6位数字"},
                description_placeholders={"phone": _mask_mobile(self._mobile)},
            )
        try:
            result = await WenzhouWaterSMSLogin.login_with_sms(
                self._mobile, code, self._verify_id
            )
            token = result.get("authToken")
            if token:
                self._access_token = token
                await self.async_set_unique_id(token[:16])
                return await self.async_step_select_meter()
        except WenzhouWaterAPIError:
            pass
        return self.async_show_form(
            step_id=STEP_SMS_VERIFY,
            data_schema=schema,
            errors={CONF_GENERAL_ERROR: ERROR_INVALID_AUTH},
            description_placeholders={"phone": _mask_mobile(self._mobile)},
        )

    # ========== 微信扫码登录 ==========

    async def async_step_wx_qr_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """微信扫码登录入口"""
        self._login_type = LOGIN_WECHAT
        return await self.async_step_qr_login()

    async def async_step_qr_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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

    async def async_step_select_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """选择水表"""
        if not hasattr(self, "_access_token") or not self._access_token:
            return self.async_show_form(
                step_id=STEP_SELECT_METER,
                data_schema=vol.Schema({}),
                errors={CONF_GENERAL_ERROR: "Token缺失"},
            )

        api = WenzhouWaterAPI(self._access_token)
        try:
            cards = await api.get_meter_cards()
        except Exception:
            return self.async_show_form(
                step_id=STEP_SELECT_METER,
                data_schema=vol.Schema({}),
                errors={CONF_GENERAL_ERROR: ERROR_CANNOT_CONNECT},
            )

        if not cards:
            return self.async_abort(reason="no_meters")

        opts = {"__all__": f"全部水表（共{len(cards)}个）"}
        for c in cards:
            opts[c["cardId"]] = f"{c.get('cardName', '')} - {c.get('cardAddress', '')}"

        errors = {}
        if user_input is not None:
            selected = user_input.get(CONF_METER_CARD_ID)
            day = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE))
            if not 1 <= day <= 31:
                errors[CONF_SCAN_INTERVAL] = "请输入 1-31"
            elif selected:
                if selected == "__all__":
                    sc = [{"cardId": c["cardId"], "cardName": c.get("cardName"), "cardAddress": c.get("cardAddress")} for c in cards]
                    title = f"温州水务（{len(sc)}个水表）"
                else:
                    card = next((c for c in cards if c["cardId"] == selected), None)
                    sc = [{"cardId": card["cardId"], "cardName": card.get("cardName"), "cardAddress": card.get("cardAddress")}] if card else []
                    title = f"温州水务 - {card.get('cardName', selected)}" if card else ""

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_METER_CARDS: sc,
                        CONF_LOGIN_TYPE: self._login_type,
                        CONF_SCAN_INTERVAL: day,
                        CONF_SCAN_INTERVAL_UNIT: "month",
                    },
                )

        return self.async_show_form(
            step_id=STEP_SELECT_METER,
            data_schema=vol.Schema({
                vol.Required(CONF_METER_CARD_ID, default="__all__"): vol.In(opts),
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_VALUE):
                    selector({"number": {"min": 1, "max": 31, "mode": "box"}}),
            }),
            errors=errors,
            description_placeholders={"day": str(DEFAULT_SCAN_INTERVAL_VALUE)},
        )


# ========== OptionsFlow ==========


class WenzhouWaterOptionsFlowHandler(config_entries.OptionsFlow):
    """温州水务选项流程"""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """管理选项"""
        errors = {}
        if user_input is not None:
            d = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE))
            if 1 <= d <= 31:
                user_input[CONF_SCAN_INTERVAL_UNIT] = "month"
                return self.async_create_entry(title="", data=user_input)
            errors[CONF_SCAN_INTERVAL] = "请输入 1-31"

        cur = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_VALUE),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=cur):
                    selector({"number": {"min": 1, "max": 31, "mode": "box"}}),
            }),
            errors=errors,
        )


# ========== 辅助函数 ==========


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


def _mask_mobile(mobile: str) -> str:
    return mobile[:3] + "****" + mobile[7:]
