"""温州水务API客户端"""
import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import BASE_URL, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class WenzhouWaterAPI:
    """温州水务API客户端"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "X-MCS-AUTH-TOKEN": access_token,
            "Content-Type": "application/json",
            "X-MCS-CHANNEL": "1",
            "x-web-xhr": "1",
            "x-3h-account-type": "mcs",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254186b) XWEB/19481",
            "Referer": "https://servicewechat.com/wxe8c4cb0f78106a50/43/page-frame.html",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """发送API请求"""
        url = f"{BASE_URL}{path}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, headers=self._headers, **kwargs) as response:
                data = await response.json()
                if data.get("code") != 0:
                    _LOGGER.error(f"API error: {data.get('message')} (code={data.get('code')})")
                    raise Exception(data.get("message", "API error"))
                return data.get("data", {})

    async def get_user_info(self) -> dict:
        """获取用户信息"""
        return await self._request("GET", "/system/users/my")

    async def get_meter_cards(self) -> list:
        """获取用户的水表卡列表"""
        data = await self._request("GET", "/system/users/meter-cards/my")
        return data if isinstance(data, list) else []

    async def get_meter_card_info(self, card_id: str) -> dict:
        """获取水表卡详细信息"""
        return await self._request("GET", f"/meter-card/{card_id}/des")

    async def get_last_reading(self, card_id: str) -> dict:
        """获取最新抄表数据"""
        return await self._request("GET", f"/meter-card/{card_id}/last-reading")

    async def get_price_info(self, card_id: str) -> dict:
        """获取水价信息"""
        return await self._request("GET", f"/meter-card/{card_id}/price-info")

    async def get_bills(self, card_id: str, start_month: str = None, end_month: str = None) -> list:
        """获取账单列表"""
        import datetime
        if not end_month:
            end_month = datetime.datetime.now().strftime("%Y%m")
        if not start_month:
            start_month = datetime.datetime.now().replace(month=1).strftime("%Y%m")

        return await self._request("GET", f"/meter-card/{card_id}/bills?startBM={start_month}&endBM={end_month}")

    async def get_multi_card_static(self) -> list:
        """获取多卡静态信息"""
        data = await self._request("GET", "/meter-card/multi-card/static")
        return data if isinstance(data, list) else []
