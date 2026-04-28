"""温州水务传感器 - v1.3.0
修复:
  - 支持多用户/多水表：遍历所有配置的水表，为每个创建独立传感器组
  - unique_id 包含 card_id 以区分不同水表的同一类传感器
  - sensor entity 从 coordinator.data[card_id][sensor_type] 取值
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
    CONF_METER_CARDS,
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
    # 单价（元/立方米）
    "water_price_step1": {
        "name": "一阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
    },
    "water_price_step2": {
        "name": "二阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
    },
    "water_price_step3": {
        "name": "三阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
    },
    "water_price_sewage": {
        "name": "污水处理费",
        "icon": "mdi:recycle",
        "unit": "¥/m³",
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
    """设置传感器（支持多水表 + 月模式调度）"""
    _unsub_monthly = None  # 月度定时器句柄，避免重复注册
    access_token = entry.data[CONF_ACCESS_TOKEN]

    # 兼容旧格式：优先读取 meter_cards（列表），否则读取单个 meter_card_id
    meter_cards_config = entry.data.get(CONF_METER_CARDS, [])
    if meter_cards_config:
        # 新格式：meter_cards 是列表
        card_ids = [c["cardId"] for c in meter_cards_config]
    else:
        # 旧格式：只有单个 meter_card_id，转换为列表
        card_id = entry.data.get(CONF_METER_CARD_ID)
        card_name = entry.data.get(CONF_METER_CARD_NAME, "未知")
        card_address = entry.data.get(CONF_METER_CARD_ADDRESS, "未知地址")
        if card_id:
            meter_cards_config = [{"cardId": card_id, "cardName": card_name, "cardAddress": card_address}]
            card_ids = [card_id]
        else:
            meter_cards_config = []
            card_ids = []

    if not card_ids:
        _LOGGER.error("温州水务：未找到任何水表配置，请重新配置集成")
        return

    _LOGGER.info(f"温州水务：检测到 {len(card_ids)} 个水表: {card_ids}")

    # 获取月度更新日期
    day_of_month = entry.options.get(CONF_SCAN_INTERVAL)
    if day_of_month is None:
        day_of_month = entry.data.get(CONF_SCAN_INTERVAL, 1)
    if day_of_month is None:
        day_of_month = 1
    day_of_month = max(1, min(31, int(day_of_month)))

    # 创建 coordinator（支持多水表）
    coordinator = WenzhouWaterDataUpdateCoordinator(hass, access_token, card_ids)

    # 首次刷新
    await coordinator.async_config_entry_first_refresh()

    # 为每个水表创建传感器实体
    entities = []
    for card_info in meter_cards_config:
        card_id = card_info.get("cardId")
        card_name = card_info.get("cardName", "未知")
        for sensor_id in SENSOR_TYPES:
            entities.append(
                WenzhouWaterSensor(coordinator, entry, sensor_id, card_id, card_name)
            )

    async_add_entities(entities)

    # ========== 月度定时调度 ==========
    async def _scheduled_update(now):
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
    """温州水务数据更新协调器（支持多水表）"""

    def __init__(self, hass: HomeAssistant, access_token: str, card_ids: list):
        self.api = WenzhouWaterAPI(access_token)
        self.card_ids = card_ids  # 支持多水表
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),  # 兜底轮询间隔
        )

    def _make_card_result(self, card_id: str) -> dict:
        """生成单个水表的默认数据结构"""
        return {
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
            "water_price_step1": 0,
            "water_price_step2": 0,
            "water_price_step3": 0,
            "water_price_sewage": 0,
        }

    async def _async_update_data(self) -> dict:
        """更新数据 - 每个水表独立获取，全局共享账户信息"""
        # 结果结构: {card_id: {sensor_type: value}}
        result = {}
        for card_id in self.card_ids:
            result[card_id] = self._make_card_result(card_id)

        # 全局账户信息（从第一个水表获取）
        total_api_calls = 4
        error_count = 0
        token_expired = False

        # 1. 获取账户静态信息（全局，共享）
        try:
            static_info = await self.api.get_multi_card_static()
            if static_info and len(static_info) > 0:
                for info in static_info:
                    cid = info.get("cardId")
                    if cid in result:
                        result[cid]["account_balance"] = float(info.get("amount", 0) or 0)
                        result[cid]["total_arrears"] = float(info.get("totalLateFee", 0) or 0)
                        result[cid]["total_water"] = float(info.get("totalWater", 0) or 0)
        except WenzhouWaterTokenExpiredError as e:
            _LOGGER.error(f"Token已过期: {e}")
            token_expired = True
            error_count += 1
        except Exception as e:
            _LOGGER.error(f"获取账户静态信息失败: {e}")
            error_count += 1

        # 2-4. 为每个水表获取独立数据
        for card_id in self.card_ids:
            card_result = result[card_id]
            card_error_count = 0

            # 2. 获取水表信息
            try:
                meter_info = await self.api.get_meter_card_info(card_id)
                if meter_info:
                    card_result["meter_address"] = meter_info.get("cardAddress", "未知")
                    card_result["meter_station"] = meter_info.get("stationName", "未知")
                    card_result["customer_name"] = meter_info.get("customerName", "未知")
            except WenzhouWaterTokenExpiredError as e:
                _LOGGER.error(f"Token已过期（{card_id}）: {e}")
                token_expired = True
                card_error_count += 1
            except Exception as e:
                _LOGGER.error(f"获取水表信息失败（{card_id}）: {e}")
                card_error_count += 1

            # 3. 获取账单
            try:
                bills = await self.api.get_bills(card_id)
                if bills and len(bills) > 0:
                    bill = bills[0]
                    card_result["billing_month"] = bill.get("billingMonth", "未知")
                    card_result["price_type"] = bill.get("priceName", "未知")
                    card_result["last_reading"] = float(bill.get("lastReading", 0) or 0)
                    card_result["current_reading"] = float(bill.get("reading", 0) or 0)
                    card_result["water_used"] = float(bill.get("readWater", 0) or 0)
                    card_result["bill_amount"] = float(bill.get("amount", 0) or 0)
                    card_result["last_read_date"] = bill.get("lastReadDate", "未知")
                    card_result["current_read_date"] = bill.get("readDate", "未知")
                    card_result["due_date"] = bill.get("chargeLimitTime", "未知")

                    # 解析账单明细，提取单价
                    details = bill.get("details", [])
                    water_price_step1 = 0.0
                    water_price_step2 = 0.0
                    water_price_step3 = 0.0
                    water_price_sewage = 0.0
                    for detail in details:
                        pi_name = detail.get("piName", "")
                        level = detail.get("level", -1)
                        price = float(detail.get("price", 0) or 0)
                        # 基本水价，取 level=1/2/3（一阶/二阶/三阶）
                        if pi_name == "基本水价" and level == 1:
                            water_price_step1 = price
                        elif pi_name == "基本水价" and level == 2:
                            water_price_step2 = price
                        elif pi_name == "基本水价" and level == 3:
                            water_price_step3 = price
                        # 污水处理费，level=0
                        elif pi_name == "代收污水处理费" and level == 0:
                            water_price_sewage = price
                    card_result["water_price_step1"] = water_price_step1
                    card_result["water_price_step2"] = water_price_step2
                    card_result["water_price_step3"] = water_price_step3
                    card_result["water_price_sewage"] = water_price_sewage
            except WenzhouWaterTokenExpiredError as e:
                _LOGGER.error(f"Token已过期（{card_id}）: {e}")
                token_expired = True
                card_error_count += 1
            except Exception as e:
                _LOGGER.error(f"获取账单失败（{card_id}）: {e}")
                card_error_count += 1

            # 4. 获取最新抄表数据（补充）
            try:
                last_reading = await self.api.get_last_reading(card_id)
                if last_reading:
                    if card_result.get("last_reading", 0) == 0:
                        card_result["last_reading"] = float(last_reading.get("lastReading", 0) or 0)
                    if card_result.get("water_used", 0) == 0:
                        card_result["water_used"] = float(last_reading.get("readWater", 0) or 0)
            except WenzhouWaterTokenExpiredError as e:
                _LOGGER.error(f"Token已过期（{card_id}）: {e}")
                token_expired = True
                card_error_count += 1
            except Exception as e:
                _LOGGER.error(f"获取最新抄表数据失败（{card_id}）: {e}")
                card_error_count += 1

            # 判断单个水表状态
            if token_expired:
                card_result["integration_status"] = "token_expired"
                card_result["status"] = "error"
            elif card_error_count >= total_api_calls:
                card_result["integration_status"] = "api_error"
                card_result["status"] = "error"
            elif card_error_count > 0:
                card_result["integration_status"] = "network_error"
                card_result["status"] = "partial_error"
            else:
                card_result["integration_status"] = "normal"
                card_result["status"] = "ok"

        # 全局状态（任一水表有问题则全局有问题）
        if token_expired:
            for card_id in self.card_ids:
                result[card_id]["integration_status"] = "token_expired"
                result[card_id]["status"] = "error"

        _LOGGER.info(
            f"温州水务数据更新完成（{len(self.card_ids)}个水表）: "
            f"状态={result[self.card_ids[0]]['integration_status'] if self.card_ids else 'unknown'}"
        )
        return result


class WenzhouWaterSensor(CoordinatorEntity, SensorEntity):
    """温州水务传感器 - 继承 SensorEntity + CoordinatorEntity，支持多水表"""

    def __init__(self, coordinator: WenzhouWaterDataUpdateCoordinator, entry: ConfigEntry,
                 sensor_id: str, card_id: str, card_name: str):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.sensor_id = sensor_id
        self.card_id = card_id
        self.card_name = card_name
        self._attr_has_entity_name = True

    @property
    def unique_id(self) -> str:
        # unique_id 包含 card_id，确保多水表时实体不冲突
        return f"{DOMAIN}_{self.card_id}_{self.sensor_id}"

    @property
    def name(self) -> str:
        # 传感器名称包含水表名，便于区分
        return f"{self.card_name} {SENSOR_TYPES[self.sensor_id]['name']}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self.card_id)},
            "name": f"温州水务 - {self.card_name}",
            "manufacturer": "温州水务",
            "model": "智能水表",
        }

    @property
    def native_value(self):
        """返回传感器状态值（从对应 card_id 的数据中取）"""
        if not self.coordinator.data:
            return None
        card_data = self.coordinator.data.get(self.card_id, {})
        return card_data.get(self.sensor_id)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return SENSOR_TYPES[self.sensor_id].get("unit")

    @property
    def icon(self) -> str | None:
        return SENSOR_TYPES[self.sensor_id].get("icon")

    @property
    def extra_state_attributes(self) -> dict:
        """额外状态属性"""
        card_data = self.coordinator.data.get(self.card_id, {}) if self.coordinator.data else {}
        raw_status = card_data.get("integration_status", "unknown")
        return {
            "card_id": self.card_id,
            "card_name": self.card_name,
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
        if self.coordinator.data is not None:
            self.async_write_ha_state()
