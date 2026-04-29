"""温州水务Home Assistant集成 - v1.7.0

新增 v1.7.0:
  - 阶梯水价解析（threshold1/2 一二阶阈值）
  - 阶梯用水量计算（step1_usage/step2_usage/step3_usage）
  - 当前所处阶梯传感器（current_step）
  - 预估本月账单金额（estimated_bill_amount）
  - 距截止日期天数（days_until_due）
  - 新增诊断传感器：最后更新时间（last_update_time）
新增 v1.6.0:
  - 并发优化：批量抓取历史数据时并行请求
  - 一次性初始化：避免重复触发批量初始化
  - 历史数据扩展：新增 read_date、balance 字段
新增 v1.5.0:
  - 历史数据首次初始化：从 API 批量抓取（2024年3月起）
新增 v1.4.0:
  - 新增传感器：预估月用水量、账户预警、历史月均用水、与均值对比
  - 新增历史数据持久化（HA Storage）
  - account_warning 动态图标（正常/偏低/不足/为0四级）
"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_SCAN_INTERVAL, CONF_SCAN_INTERVAL_UNIT, CONF_METER_CARDS, DEFAULT_SCAN_INTERVAL_VALUE, DEFAULT_SCAN_INTERVAL_UNIT

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)

__version__ = "1.7.0"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """通过 configuration.yaml 配置的方式（可选兼容）"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置集成入口"""
    hass.data.setdefault("wenzhou_water", {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop("wenzhou_water", None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """处理 config entry 版本迁移

    v1 → v2: 添加 scan_interval / scan_interval_unit
    v2 → v3: 添加 meter_cards（多水表单条记录）
    """
    _LOGGER.info(f"温州水务: 迁移 config entry 从 version {config_entry.version}")

    new_data = {**config_entry.data}

    if config_entry.version == 1:
        # 补充缺失的 scan_interval 字段
        if CONF_SCAN_INTERVAL not in new_data:
            new_data[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL_VALUE
            _LOGGER.info(f"补充 scan_interval={DEFAULT_SCAN_INTERVAL_VALUE}")
        if CONF_SCAN_INTERVAL_UNIT not in new_data:
            new_data[CONF_SCAN_INTERVAL_UNIT] = DEFAULT_SCAN_INTERVAL_UNIT
            _LOGGER.info(f"补充 scan_interval_unit={DEFAULT_SCAN_INTERVAL_UNIT}")
        # 升级到 v2
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("温州水务: v1→v2 迁移完成")
        # 继续执行 v2→v3 迁移

    if config_entry.version == 2:
        # v2 → v3: 将单个 meter_card_id 转换为 meter_cards 列表
        if CONF_METER_CARDS not in new_data:
            card_id = new_data.get(CONF_METER_CARD_ID)
            if card_id:
                new_data[CONF_METER_CARDS] = [{
                    "cardId": card_id,
                    "cardName": new_data.get(CONF_METER_CARD_NAME, "未知"),
                    "cardAddress": new_data.get(CONF_METER_CARD_ADDRESS, "未知地址"),
                }]
                _LOGGER.info(f"v2→v3: 将单水表 {card_id} 迁移到 meter_cards 列表")
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=3)
        _LOGGER.info("温州水务: v2→v3 迁移完成")

    return True
