"""温州水务微信扫码登录模块

移除 segno 依赖，微信页面自带二维码图片。
WechatLoginSession 使用 qrcode_image_url（微信服务器直供）。
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

# 温州水务微信 OAuth 配置
WX_APPID = "wx7a3434ca2a0bb80d"
WX_POLL_URL = "https://lp.open.weixin.qq.com/connect/l/qrconnect"
WX_REDIRECT_URI = "https%3A%2F%2Fsw-os.wzgytz.com%2Flogin"
WX_TOKEN_URL = "https://sw-os.wzgytz.com/v3/open-api/system/auth/sign-in"
WX_API_TIMEOUT = 15
WX_BASE = "https://open.weixin.qq.com"


@dataclass(slots=True)
class WechatLoginSession:
    """微信登录会话"""
    uuid: str
    state: str
    qrcode_image_url: str = ""  # 微信服务器直接提供的二维码图片 URL
    qrcode_url: str = ""  # OAuth URL（备用）


@dataclass(slots=True)
class WechatLoginResult:
    """微信登录结果"""
    success: bool
    token: str = ""
    message: str = ""


def _build_wx_oauth_url(state: str) -> str:
    """构建微信 OAuth URL"""
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
    """同步获取微信 UUID"""
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
    """启动微信登录，获取 UUID 和二维码图片 URL"""
    state = str(random.random())
    uuid = await asyncio.get_event_loop().run_in_executor(None, _get_wx_uuid, state)
    if not uuid:
        raise RuntimeError("获取微信UUID失败")

    # 微信页面直接提供了二维码图片 URL
    qrcode_image_url = f"{WX_BASE}/connect/qrcode/{uuid}"

    session = WechatLoginSession(
        uuid=uuid,
        state=state,
        qrcode_image_url=qrcode_image_url,
        qrcode_url=_build_wx_oauth_url(state),
    )
    _LOGGER.debug(f"微信登录会话已创建: uuid={uuid}")
    return session


async def _async_wx_to_token(code: str) -> Optional[str]:
    """异步用微信 code 换 token"""
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
