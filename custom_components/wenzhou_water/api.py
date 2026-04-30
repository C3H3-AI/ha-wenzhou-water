"""温州水务API客户端 - v1.3.0
新增 v1.3.0:
  - 新增短信验证码登录: send_sms_code(), login_with_sms()
  - 无需预先获取 Token，直接用手机号+验证码登录
修复: get_bills 支持自定义起始月份，支持24个月历史数据抓取（2024年3月起）
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from .const import BASE_URL, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# API 返回的错误码，表示 Token 无效/过期
TOKEN_EXPIRED_CODES = {401, 10001, 10002, 10003, 10401}


class WenzhouWaterAPI:
    """温州水务API客户端（需Token初始化）"""

    # API 支持的最早账单月份
    EARLIEST_BILLING_MONTH = "202403"  # 2024年3月

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

    @staticmethod
    def _calc_month(yyyymm: str, offset: int) -> str:
        """计算月份偏移（支持跨年）

        Args:
            yyyymm: 格式如 "202403"
            offset: 月份偏移量，正数往后，负数往前

        Returns:
            偏移后的年月，格式如 "202402"
        """
        year = int(yyyymm[:4])
        month = int(yyyymm[4:6])
        month += offset
        while month <= 0:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        return f"{year}{month:02d}"

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """发送API请求"""
        url = f"{BASE_URL}{path}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=self._headers, **kwargs) as response:
                    # 检查 HTTP 401
                    if response.status == 401:
                        raise WenzhouWaterTokenExpiredError("HTTP 401 - Token已失效")

                    data = await response.json()
                    code = data.get("code", 0)

                    if code != 0:
                        msg = data.get("message", "API error")
                        _LOGGER.error(f"API error: {msg} (code={code})")
                        # 检查是否 Token 过期相关错误码
                        if code in TOKEN_EXPIRED_CODES:
                            raise WenzhouWaterTokenExpiredError(msg, code)
                        raise WenzhouWaterAPIError(msg, code)

                    return data.get("data", {})

        except WenzhouWaterTokenExpiredError:
            raise  # 直接上抛 Token 过期异常
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Network error: {e}")
            raise WenzhouWaterAPIError(f"Network error: {e}", -1) from e
        except asyncio.TimeoutError as e:
            _LOGGER.error(f"Request timeout: {e}")
            raise WenzhouWaterAPIError("Request timeout", -2) from e

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
        """获取账单列表

        Args:
            card_id: 水表卡号
            start_month: 起始月份（YYYYMM），默认从最早可抓取的时间开始（202403）
            end_month: 结束月份（YYYYMM），默认当前月份

        Returns:
            账单列表，按月份降序排列
        """
        now = datetime.now()
        if not end_month:
            end_month = now.strftime("%Y%m")

        if start_month:
            # 确保不早于最早可抓取月份
            if start_month < self.EARLIEST_BILLING_MONTH:
                start_month = self.EARLIEST_BILLING_MONTH
        else:
            # 默认从最早可抓取月份开始（2024年3月）
            start_month = self.EARLIEST_BILLING_MONTH

        return await self._request("GET", f"/meter-card/{card_id}/bills?startBM={start_month}&endBM={end_month}")

    async def get_multi_card_static(self) -> list:
        """获取多卡静态信息"""
        data = await self._request("GET", "/meter-card/multi-card/static")
        return data if isinstance(data, list) else []


class WenzhouWaterAPIError(Exception):
    """温州水务API异常"""

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(self.message)


class WenzhouWaterTokenExpiredError(WenzhouWaterAPIError):
    """Token过期异常 - 集成可据此设置 token_expired 状态"""

    def __init__(self, message: str = "Token已过期", code: int = 401):
        super().__init__(message, code)


# ============ 短信验证码登录（无需Token）============

# 发送短信验证码的请求头（与有Token的请求头不同）
_SMS_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://sw-os.wzgytz.com",
    "Referer": "https://sw-os.wzgytz.com/login",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
}


class WenzhouWaterSMSLogin:
    """温州水务短信验证码登录（无需Token）"""

    @staticmethod
    async def send_sms_code(mobile: str) -> str:
        """发送短信验证码

        Args:
            mobile: 手机号

        Returns:
            验证码ID（后续登录时需要）

        Raises:
            WenzhouWaterAPIError: 发送失败时抛出
        """
        url = f"{BASE_URL}/system/sms/code"
        payload = {
            "channelAccountId": 2,
            "mobile": mobile,
            "template": "",
            "subCompanyCode": "00"
        }

        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=_SMS_HEADERS) as response:
                    data = await response.json()
                    code = data.get("code", 0)
                    if code != 0:
                        msg = data.get("message", "发送验证码失败")
                        _LOGGER.error(f"发送短信验证码失败: {msg} (code={code})")
                        raise WenzhouWaterAPIError(msg, code)
                    # 返回验证码ID
                    return data.get("data", "")
        except aiohttp.ClientError as e:
            _LOGGER.error(f"发送短信验证码网络错误: {e}")
            raise WenzhouWaterAPIError(f"网络错误: {e}", -1) from e
        except asyncio.TimeoutError as e:
            _LOGGER.error(f"发送短信验证码超时: {e}")
            raise WenzhouWaterAPIError("请求超时", -2) from e

    @staticmethod
    async def login_with_sms(mobile: str, code: str, verify_id: str) -> dict:
        """短信验证码登录

        Args:
            mobile: 手机号
            code: 收到的6位短信验证码
            verify_id: 发送验证码时返回的验证码ID

        Returns:
            登录结果，包含:
            - authToken: 访问令牌
            - expired: 过期时间
            - registerCode: 注册码（可能为null）

        Raises:
            WenzhouWaterAPIError: 登录失败时抛出
            WenzhouWaterTokenExpiredError: Token无效（理论上不会在这里抛出）
        """
        url = f"{BASE_URL}/system/auth/sign-in"
        # mobileVerify 格式: "验证码ID#验证码"
        payload = {
            "authType": "mobile",
            "channelAccountId": 2,
            "code": "",  # 空字符串
            "mobile": mobile,
            "mobileCode": code,  # 6位验证码
            "mobileVerify": f"{verify_id}#{code}"
        }

        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=_SMS_HEADERS) as response:
                    data = await response.json()
                    code = data.get("code", 0)
                    if code != 0:
                        msg = data.get("message", "登录失败")
                        _LOGGER.error(f"短信验证码登录失败: {msg} (code={code})")
                        raise WenzhouWaterAPIError(msg, code)
                    return data.get("data", {})
        except aiohttp.ClientError as e:
            _LOGGER.error(f"短信验证码登录网络错误: {e}")
            raise WenzhouWaterAPIError(f"网络错误: {e}", -1) from e
        except asyncio.TimeoutError as e:
            _LOGGER.error(f"短信验证码登录超时: {e}")
            raise WenzhouWaterAPIError("请求超时", -2) from e
