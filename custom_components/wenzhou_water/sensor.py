"""温州水务传感器 - v1.1.0
修复:
  - 扫描间隔改为月模式 async_track_point_in_time（精确到每月X号）
  - Sensor 继承 SensorEntity（参考华润燃气）
  - 区分 TokenExpiredError 设置 token_expired 状态
  - 去除 DEBUG 日志
  - integration_status 中文映射
"""
import logging
from datetime import timedelta, datetime
from typing import Any, Dict, Optional
import calendar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

try:
    from homeassistant.components.sensor import SensorEntity
except ImportError:
    from homeassistant.helpers.entity import Entity as SensorEntity

from .api import WenzhouWaterAPI, WenzhouWaterAPIError, WenzhouWaterTokenExpiredError
from .const import (
    DOMAIN,
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_UNIT,
    SCAN_INTERVAL_UNITS,
    INTEGRATION_STATUS,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    # 账户信息
    "account_balance": {
        "name": "账户余额",
        "icon": "mdi:cash",
        "unit": "¥",
    },
    "total_arrears": {
        "name": "总欠费",
        "icon": "mdi:alert-circle",
        "unit": "¥",
    },
    # 最新账单
    "last_reading": {
        "name": "上期读数",
        "icon": "mdi:counter",
        "unit": "m³",
    },
    "current_reading": {
        "name": "本期读数",
        "icon": "mdi:counter",
        "unit": "m³",
    },
    "water_used": {
        "name": "本期用水量",
        "icon": "mdi:water",
        "unit": "m³",
    },
    "bill_amount": {
        "name": "账单金额",
        "icon": "mdi:receipt",
        "unit": "¥",
    },
    "last_read_date": {
        "name": "上期抄表日期",
        "icon": "mdi:calendar",
        "unit": None,
    },
    "current_read_date": {
        "name": "本期抄表日期",
        "icon": "mdi:calendar",
        "unit": None,
    },
    "due_date": {
        "name": "缴费截止日期",
        "icon": "mdi:calendar-clock",
        "unit": None,
    },
    # 水表信息
    "meter_address": {
        "name": "用水地址",
        "icon": "mdi:home-map-marker",
        "unit": None,
    },
    "meter_station": {
        "name": "所属营业厅",
        "icon": "mdi:office-building",
        "unit": None,
    },
    "price_type": {
        "name": "水价类型",
        "icon": "mdi:currency-cny",
        "unit": None,
    },
    # 状态
    "integration_status": {
        "name": "集成状态",
        "icon": "mdi:heart-pulse",
        "unit": None,
    },
}


def _compute_next_monthly_run(day_of_month: int) -> datetime:
    """计算下一次月度更新的时间点

    Args:
        day_of_month: 每月几号更新（1-31）

    Returns:
        下一次触发的本地时间（naive datetime，兼容 async_track_point_in_time）
    """
    # 使用本地 naive datetime，避免与 aware datetime 混用导致的 TypeError
    now = datetime.now()
    # 本月目标日
    max_day = calendar.monthrange(now.year, now.month)[1]
    target_day = min(day_of_month, max_day)

    # 构造本月目标时间点（当天 08:00 执行，避免 0 点边界问题）
    target_this_month = now.replace(day=target_day, hour=8, minute=0, second=0, microsecond=0)

    if now < target_this_month:
        return target_this_month

    # 本月已过，算下个月
    year = now.year
    month = now.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    target_day = min(day_of_month, max_day)
    return datetime(year, month, target_day, 8, 0, 0)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """设置传感器（月模式调度 + CoordinatorEntity）"""
    _unsub_monthly = None  # 月度定时器句柄，避免重复注册
    access_token = entry.data[CONF_ACCESS_TOKEN]
    card_id = entry.data[CONF_METER_CARD_ID]

    # 获取月度更新日期（兼容 v1 无 scan_interval 的情况）
    day_of_month = entry.options.get(CONF_SCAN_INTERVAL)
    if day_of_month is None:
        day_of_month = entry.data.get(CONF_SCAN_INTERVAL, 1)
    if day_of_month is None:
        day_of_month = 1  # 兜底默认
    day_of_month = max(1, min(31, int(day_of_month)))

    # 创建 coordinator（内部轮询间隔设为1小时作为兜底）
    coordinator = WenzhouWaterDataUpdateCoordinator(hass, access_token, card_id)

    # 首次刷新
    await coordinator.async_config_entry_first_refresh()

    # 创建传感器实体
    entities = [
        WenzhouWaterSensor(coordinator, entry, sensor_id)
        for sensor_id in SENSOR_TYPES
    ]
    async_add_entities(entities)

    # ========== 月度定时调度 ==========
    # 使用 async_track_point_in_time 在每月指定日期触发
    async def _scheduled_update(self, now):
        """定时触发数据刷新"""
        _LOGGER.info(f"温州水务月度定时刷新触发（每月{day_of_month}号）")
        await coordinator.async_request_refresh()
        # 取消上一次定时器，避免累积
        nonlocal _unsub_monthly
        if _unsub_monthly is not None:
            _unsub_monthly()
            _unsub_monthly = None
        # 注册下一次
        next_run = _compute_next_monthly_run(day_of_month)
        _LOGGER.info(f"下一次月度刷新时间: {next_run}")
        _unsub_monthly = async_track_point_in_time(hass, _scheduled_update, next_run)

    # 注册首次定时
    next_run = _compute_next_monthly_run(day_of_month)
    _LOGGER.info(f"温州水务月度调度: 每月{day_of_month}号08:00更新, 下次触发: {next_run}")
    _unsub_monthly = async_track_point_in_time(hass, _scheduled_update, next_run)


class WenzhouWaterDataUpdateCoordinator(DataUpdateCoordinator):
    """温州水务数据更新协调器"""

    def __init__(self, hass: HomeAssistant, access_token: str, card_id: str):
        self.api = WenzhouWaterAPI(access_token)
        self.card_id = card_id
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),  # 兜底轮询间隔
        )

    async def _async_update_data(self) -> dict:
        """更新数据 - 各接口独立容错，任一失败不影响其他"""
        result = {
            "account_balance": 0,
            "total_arrears": 0,
            "total_water": 0,
            "last_reading": 0,
            "current_reading": 0,
            "water_used": 0,
            "bill_amount": 0,
            "last_read_date": "未知",
            "current_read_date": "未知",
            "due_date": "未知",
            "meter_address": "未知",
            "meter_station": "未知",
            "customer_name": "未知",
            "price_type": "未知",
            "billing_month": "未知",
            "status": "unknown",
            "integration_status": "unknown",
        }

        total_api_calls = 4
        error_count = 0
        token_expired = False

        # 1. 获取账户静态信息
        try:
            static_info = await self.api.get_multi_card_static()
            if static_info and len(static_info) > 0:
                info = static_info[0]
                result["account_balance"] = float(info.get("amount", 0) or 0)
                result["total_arrears"] = float(info.get("totalLateFee", 0) or 0)
                result["total_water"] = float(info.get("totalWater", 0) or 0)
        except WenzhouWaterTokenExpiredError as e:
            _LOGGER.error(f"Token已过期: {e}")
            token_expired = True
            error_count += 1
        except Exception as e:
            _LOGGER.error(f"获取账户静态信息失败: {e}")
            error_count += 1

        # 2. 获取水表信息
        try:
            meter_info = await self.api.get_meter_card_info(self.card_id)
            if meter_info:
                result["meter_address"] = meter_info.get("cardAddress", "未知")
                result["meter_station"] = meter_info.get("stationName", "未知")
                result["customer_name"] = meter_info.get("customerName", "未知")
        except WenzhouWaterTokenExpiredError as e:
            _LOGGER.error(f"Token已过期: {e}")
            token_expired = True
            error_count += 1
        except Exception as e:
            _LOGGER.error(f"获取水表信息失败: {e}")
            error_count += 1

        # 3. 获取账单（主要数据源）
        try:
            bills = await self.api.get_bills(self.card_id)
            if bills and len(bills) > 0:
                bill = bills[0]
                result["billing_month"] = bill.get("billingMonth", "未知")
                result["price_type"] = bill.get("priceName", "未知")
                result["last_reading"] = float(bill.get("lastReading", 0) or 0)
                result["current_reading"] = float(bill.get("reading", 0) or 0)
                result["water_used"] = float(bill.get("readWater", 0) or 0)
                result["bill_amount"] = float(bill.get("amount", 0) or 0)
                result["last_read_date"] = bill.get("lastReadDate", "未知")
                result["current_read_date"] = bill.get("readDate", "未知")
                result["due_date"] = bill.get("chargeLimitTime", "未知")
        except WenzhouWaterTokenExpiredError as e:
            _LOGGER.error(f"Token已过期: {e}")
            token_expired = True
            error_count += 1
        except Exception as e:
            _LOGGER.error(f"获取账单失败: {e}")
            error_count += 1

        # 4. 获取最新抄表数据（补充）
        try:
            last_reading = await self.api.get_last_reading(self.card_id)
            if last_reading:
                if result.get("last_reading", 0) == 0:
                    result["last_reading"] = float(last_reading.get("lastReading", 0) or 0)
                if result.get("water_used", 0) == 0:
                    result["water_used"] = float(last_reading.get("readWater", 0) or 0)
        except WenzhouWaterTokenExpiredError as e:
            _LOGGER.error(f"Token已过期: {e}")
            token_expired = True
            error_count += 1
        except Exception as e:
            _LOGGER.error(f"获取最新抄表数据失败: {e}")
            error_count += 1

        # 判断集成状态
        if token_expired:
            result["integration_status"] = "token_expired"
            result["status"] = "error"
            _LOGGER.critical("Token已过期，请重新配置集成！")
        elif error_count >= total_api_calls:
            result["integration_status"] = "api_error"
            result["status"] = "error"
            _LOGGER.critical(f"全部{total_api_calls}个API调用失败！")
        elif error_count > 0:
            result["integration_status"] = "network_error"
            result["status"] = "partial_error"
        else:
            result["integration_status"] = "normal"
            result["status"] = "ok"

        _LOGGER.info(
            f"温州水务数据更新完成: "
            f"余额¥{result['account_balance']}, "
            f"欠费¥{result['total_arrears']}, "
            f"本期用水{result['water_used']}m³, "
            f"状态={result['integration_status']}"
        )
        return result


class WenzhouWaterSensor(CoordinatorEntity, SensorEntity):
    """温州水务传感器 - 继承 SensorEntity + CoordinatorEntity"""

    def __init__(self, coordinator: WenzhouWaterDataUpdateCoordinator, entry: ConfigEntry, sensor_id: str):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.sensor_id = sensor_id
        self._attr_has_entity_name = True

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.entry.data[CONF_METER_CARD_ID]}_{self.sensor_id}"

    @property
    def name(self) -> str:
        return SENSOR_TYPES[self.sensor_id]["name"]

    @property
    def device_info(self) -> dict:
        card_id = self.entry.data[CONF_METER_CARD_ID]
        card_name = self.entry.data.get(CONF_METER_CARD_NAME, "未知")
        return {
            "identifiers": {(DOMAIN, card_id)},
            "name": f"温州水务 - {card_name}",
            "manufacturer": "温州水务",
            "model": "智能水表",
        }

    @property
    def native_value(self):
        """返回传感器状态值"""
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self.sensor_id)
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """返回单位"""
        return SENSOR_TYPES[self.sensor_id].get("unit")

    @property
    def icon(self) -> str | None:
        """返回图标"""
        return SENSOR_TYPES[self.sensor_id].get("icon")

    @property
    def extra_state_attributes(self) -> dict:
        """额外状态属性"""
        data = self.coordinator.data or {}
        raw_status = data.get("integration_status", "unknown")
        return {
            "card_id": self.entry.data[CONF_METER_CARD_ID],
            "last_update": self.coordinator.last_update_success,
            "integration_status": raw_status,
            "integration_status_cn": INTEGRATION_STATUS.get(raw_status, raw_status),
        }

    @property
    def available(self) -> bool:
        """传感器可用性 - token过期时仍显示（状态为 token_expired）"""
        if not self.coordinator.data:
            return self.coordinator.last_update_success
        return True

    async def async_added_to_hass(self):
        """添加到 Home Assistant - 避免初始 unknown"""
        await super().async_added_to_hass()
        # CoordinatorEntity 已自动注册 listener，这里只需处理已有数据的情况
        if self.coordinator.data is not None:
            self.async_write_ha_state()
