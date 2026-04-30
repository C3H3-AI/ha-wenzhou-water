"""温州水务Home Assistant集成 - v1.9.0

新增 v1.9.0:
  - 新增短信验证码登录（手机号+验证码）
  - Token过期后自动发送通知提醒用户重新登录
v1.8.0:
  - 配置界面添加描述文案，提升用户引导体验
修复 v1.7.9:
  - 新增传感器：下次轮询时间（显示下次月度调度刷新时间）
修复 v1.7.8:
  - 传感器命名统一：step2/3_usage 添加"本期"前缀
修复 v1.7.7:
  - 传感器命名更精确："累计一阶用水量"改为"本年累计一阶用水量"
修复 v1.7.6:
  - 传感器命名更清晰：step1_usage 改为"本期一阶用水量"，level_usage 改为"累计一阶用水量"
  - 修复 items 未定义的 NameError bug
  - 修复 threshold1 过早引用问题（应在 items 解析后赋值）
  - 添加 state_class/device_class 属性（支持能源仪表盘）
  - 添加按钮平台：刷新数据、爪取历史
  - 初始化时自动爪取历史数据（历史<2条时自动触发）
修复 v1.7.4:
  - 从 price-info items[] 解析二阶/三阶阈值（priceThreshold2/3 通常为 None）
修复 v1.7.3:
  - 从账单 details[] 兜底提取阶梯价格（某些水表 price-info 不返回 priceStep1/2/3）
修复 v1.7.1:
  - 使用 price-info 接口获取真实阶梯数据，不再硬编码阈值
  - 新增传感器: level_usage(一阶已用量), level_max(一阶上限), level_remaining(阶梯剩余量), person_count(家庭人口)
  - 各阶梯价格从 price-info.items 获取，不再从账单推断
  - 阶梯阈值直接使用 API 返回的 levelMax，不再计算
新增 v1.7.0:
  - 新增阶梯水价解析（threshold1/2 一二阶阈值）
  - 新增阶梯用水量计算（step1_usage/step2_usage/step3_usage）
  - 新增当前所处阶梯传感器（current_step）
  - 新增预估本月账单金额（estimated_bill_amount）
  - 新增距截止日期天数（days_until_due）
  - 新增诊断传感器：最后更新时间（last_update_time）
新增 v1.6.0:
  - 并发优化：批量爪取历史数据时并行请求
  - 一次性初始化：避免重复触发批量初始化
  - 历史数据扩展：新增 read_date、balance 字段
新增 v1.5.0:
  - 历史数据首次初始化：从 API 批量爪取（2024年3月起）
新增 v1.4.0:
  - 新增传感器：预估月用水量、账户预警、历史月均用水、与均值对比
  - 新增历史数据持久化（HA Storage）
  - account_warning 动态图标（正常/偏低/不足/为0四级）
"""
import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_SCAN_INTERVAL, CONF_SCAN_INTERVAL_UNIT, CONF_METER_CARDS, DEFAULT_SCAN_INTERVAL_VALUE, DEFAULT_SCAN_INTERVAL_UNIT

PLATFORMS = ["sensor", "button"]

_LOGGER = logging.getLogger(__name__)

__version__ = "1.9.0"


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


async def async_token_expired_notification(hass: HomeAssistant, entry_id: str) -> None:
    """Token过期通知 - 提醒用户重新登录

    Args:
        hass: Home Assistant 实例
        entry_id: 配置项ID
    """
    try:
        await hass.services.async_call(
            "notify",
            "notify",
            {
                "title": "⚠️ 温州水务 Token 已过期",
                "message": "温州水务集成的访问令牌已过期，请重新配置集成。\n\n请进入 Home Assistant → 设置 → 设备与服务 → 温州水务 → 重新配置，使用短信验证码登录。",
                "target": "notify",
            },
            blocking=True,
        )
        _LOGGER.warning("温州水务: Token过期通知已发送")
    except HomeAssistantError as e:
        _LOGGER.warning(f"温州水务: 发送Token过期通知失败: {e}")

    # 同时在日志中记录，方便调试
    _LOGGER.error(
        f"温州水务 Token 已过期，请重新配置集成。配置项ID: {entry_id}"
    )
