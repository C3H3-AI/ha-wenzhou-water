"""温州水务传感器"""
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import WenzhouWaterAPI
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "wenzhou_water"

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


def get_scan_interval(entry: ConfigEntry) -> timedelta:
    """从配置获取扫描间隔"""
    # 优先从 options 获取（用户配置），否则使用 data 中的值，最后用默认值
    scan_interval = entry.options.get("scan_interval")
    if scan_interval is None:
        scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    return timedelta(seconds=scan_interval)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """设置传感器"""
    access_token = entry.data[CONF_ACCESS_TOKEN]
    card_id = entry.data[CONF_METER_CARD_ID]

    # 创建 coordinator，设置自动刷新间隔
    coordinator = WenzhouWaterDataUpdateCoordinator(hass, access_token, card_id)
    coordinator.update_interval = get_scan_interval(entry)

    await coordinator.async_config_entry_first_refresh()

    entities = []
    for sensor_id in SENSOR_TYPES:
        entity = WenzhouWaterSensor(coordinator, entry, sensor_id)
        entities.append(entity)

    async_add_entities(entities)


class WenzhouWaterDataUpdateCoordinator(DataUpdateCoordinator):
    """温州水务数据更新协调器"""

    def __init__(self, hass: HomeAssistant, access_token: str, card_id: str):
        self.api = WenzhouWaterAPI(access_token)
        self.card_id = card_id
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # 在 async_setup_entry 中设置
        )

    async def _async_update_data(self) -> dict:
        """更新数据"""
        try:
            data = {}

            # 获取账户静态信息
            static_info = await self.api.get_multi_card_static()
            if static_info and len(static_info) > 0:
                info = static_info[0]
                data["account_balance"] = info.get("amount", 0)
                data["total_arrears"] = info.get("totalLateFee", 0)
                data["total_water"] = info.get("totalWater", 0)

            # 获取水表信息
            meter_info = await self.api.get_meter_card_info(self.card_id)
            if meter_info:
                data["meter_address"] = meter_info.get("cardAddress")
                data["meter_station"] = meter_info.get("stationName")
                data["customer_name"] = meter_info.get("customerName")

            # 获取账单（主要数据源，包含最新抄表和账单信息）
            bills = await self.api.get_bills(self.card_id)
            if bills and len(bills) > 0:
                bill = bills[0]
                data["billing_month"] = bill.get("billingMonth")
                data["price_type"] = bill.get("priceName")
                data["last_reading"] = bill.get("lastReading")
                data["current_reading"] = bill.get("reading")
                data["water_used"] = bill.get("readWater")
                data["bill_amount"] = bill.get("amount")
                data["last_read_date"] = bill.get("lastReadDate")
                data["current_read_date"] = bill.get("readDate")
                data["due_date"] = bill.get("chargeLimitTime")
                data["bills"] = bills

            # 获取最新抄表数据（补充历史数据）
            last_reading = await self.api.get_last_reading(self.card_id)
            if last_reading:
                # 仅补充字段，不覆盖 bills 数据
                if "last_reading" not in data:
                    data["last_reading"] = last_reading.get("lastReading")
                if "water_used" not in data:
                    data["water_used"] = last_reading.get("readWater")

            data["status"] = "ok"
            return data

        except Exception as e:
            _LOGGER.error(f"Failed to update data: {e}")
            return {"status": "error", "error": str(e)}


class WenzhouWaterSensor(CoordinatorEntity):
    """温州水务传感器 - 继承CoordinatorEntity实现自动更新"""

    def __init__(self, coordinator: WenzhouWaterDataUpdateCoordinator, entry: ConfigEntry, sensor_id: str):
        super().__init__(coordinator)  # 关键：必须调用super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.sensor_id = sensor_id
        self._attr_has_entity_name = True

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.entry.data[CONF_METER_CARD_ID]}_{self.sensor_id}"

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
        """返回传感器状态值 - CoordinatorEntity会自动调用此属性"""
        if not self.coordinator.data:
            return None
        # integration_status 返回状态字符串
        if self.sensor_id == "integration_status":
            return self.coordinator.data.get("status", "unknown")
        return self.coordinator.data.get(self.sensor_id)

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
        return {
            "card_id": self.entry.data[CONF_METER_CARD_ID],
            "last_update": self.coordinator.last_update_success,
        }
