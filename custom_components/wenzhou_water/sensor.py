"""温州水务传感器"""
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import WenzhouWaterAPI
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_METER_CARD_ID,
    CONF_METER_CARD_NAME,
    CONF_METER_CARD_ADDRESS,
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """设置传感器"""
    access_token = entry.data[CONF_ACCESS_TOKEN]
    card_id = entry.data[CONF_METER_CARD_ID]

    coordinator = WenzhouWaterDataUpdateCoordinator(hass, access_token, card_id)
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
            name="wenzhou_water",
            update_interval=None,  # 手动控制更新
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

            # 获取最新抄表数据
            last_reading = await self.api.get_last_reading(self.card_id)
            if last_reading:
                data["last_reading"] = last_reading.get("lastReading")
                data["current_reading"] = last_reading.get("reading")
                data["water_used"] = last_reading.get("readWater")
                data["bill_amount"] = last_reading.get("amount")
                data["last_read_date"] = last_reading.get("lastReadDate")
                data["current_read_date"] = last_reading.get("readDate")
                data["due_date"] = last_reading.get("chargeLimitTime")
                data["price_type"] = last_reading.get("priceName")

            # 获取账单
            bills = await self.api.get_bills(self.card_id)
            data["bills"] = bills

            data["status"] = "ok"
            return data

        except Exception as e:
            _LOGGER.error(f"Failed to update data: {e}")
            return {"status": "error", "error": str(e)}


class WenzhouWaterSensor(Entity):
    """温州水务传感器基类"""

    def __init__(self, coordinator: WenzhouWaterDataUpdateCoordinator, entry: ConfigEntry, sensor_id: str):
        self.coordinator = coordinator
        self.entry = entry
        self.sensor_id = sensor_id
        self._attr_has_entity_name = True

    @property
    def unique_id(self) -> str:
        return f"wenzhou_water_{self.entry.data[CONF_METER_CARD_ID]}_{self.sensor_id}"

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

    async def async_update(self):
        """更新传感器数据"""
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict:
        """额外状态属性"""
        data = self.coordinator.data or {}
        return {
            "card_id": self.entry.data[CONF_METER_CARD_ID],
            "last_update": data.get("last_update"),
        }


DOMAIN = "wenzhou_water"
