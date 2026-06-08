"""温州水务微信扫码登录模块

返回微信服务器二维码图片 URL，由 config_flow 用 <img> + style 控制显示大小。
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import urllib.request
from dataclasses import dataclass
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

WX_APPID = "wx7a3434ca2a0bb80d"
WX_POLL_URL = "https://lp.open.weixin.qq.com/connect/l/qrconnect"
WX_REDIRECT_URI = "https%3A%2F%2Fsw-os.wzgytz.com%2Flogin"
WX_TOKEN_URL = "https://sw-os.wzgytz.com/v3/open-api/system/auth/sign-in"
WX_API_TIMEOUT = 15
WX_BASE = "https://open.weixin.qq.com"


@dataclass(slots=True)
class WechatLoginSession:
    uuid: str
    state: str
    qrcode_image_url: str = ""


@dataclass(slots=True)
class WechatLoginResult:
    success: bool
    token: str = ""
    message: str = ""


def _build_wx_oauth_url(state: str) -> str:
    return (
        f"{WX_BASE}/connect/qrconnect"
        f"?appid={WX_APPID}"
        f"&scope=snsapi_login"
        f"&redirect_uri={WX_REDIRECT_URI}"
        f"&state={state}"
        f"&login_type=jssdk"
        f"&style=white"
        f"&self_redirect=default"
        f"&href="
    )


def _get_wx_uuid(state: str) -> Optional[str]:
    url = _build_wx_oauth_url(state)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/132"})
        resp = urllib.request.urlopen(req, timeout=WX_API_TIMEOUT)
        html = resp.read().decode("utf-8", errors="ignore")
        for m in re.finditer(r'uuid["\'=:\s]+([a-zA-Z0-9_\-]+)', html):
            uuid = m.group(1)
            if len(uuid) > 10:
                return uuid
    except Exception as e:
        _LOGGER.error(f"获取微信UUID失败: {e}")
    return None


async def async_start_weixin_login() -> WechatLoginSession:
    state = str(random.random())
    uuid = await asyncio.get_event_loop().run_in_executor(None, _get_wx_uuid, state)
    if not uuid:
        raise RuntimeError("获取微信UUID失败")

    qrcode_image_url = f"{WX_BASE}/connect/qrcode/{uuid}"

    session = WechatLoginSession(
        uuid=uuid,
        state=state,
        qrcode_image_url=qrcode_image_url,
    )
    _LOGGER.debug(f"微信登录会话已创建: uuid={uuid}")
    return session


async def async_check_qr_status(session: WechatLoginSession) -> WechatLoginResult:
    poll_url = f"{WX_POLL_URL}?uuid={session.uuid}&_=0"
    headers = {"User-Agent": "Mozilla/5.0 Chrome/132"}
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(poll_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()

        m = re.search(r"window\.wx_code='([^']+)'", text)
        if m and m.group(1):
            code = m.group(1)
            token = await _async_wx_to_token(code)
            if token:
                return WechatLoginResult(success=True, token=token, message="登录成功")
            return WechatLoginResult(success=False, message="token_failed")

        err_m = re.search(r"window\.wx_errcode=(\d+)", text)
        if err_m and int(err_m.group(1)) == 400:
            return WechatLoginResult(success=False, message="expired")

    except Exception as e:
        _LOGGER.warning(f"检查微信扫码状态异常: {e}")

    return WechatLoginResult(success=False, message="scan_waiting")


async def _async_wx_to_token(code: str) -> Optional[str]:
    payload = json.dumps({
        "authType": "wxQR",
        "channelAccountId": 2,
        "code": code,
        "mobile": "",
        "mobileCode": "",
        "mobileVerify": "#"
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 Chrome/132",
    }
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(WX_TOKEN_URL, data=payload, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=WX_API_TIMEOUT)) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data["data"]["authToken"]
                _LOGGER.warning(f"微信code换token失败: {data.get('message')}")
    except Exception as e:
        _LOGGER.error(f"微信code换token异常: {e}")
    return None
