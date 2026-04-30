"""温州水务传感器 - v1.9.0
新增 v1.9.0:
  - Token过期后自动发送通知提醒用户重新登录
修复 v1.7.9:
  - 新增传感器：下次轮询时间（显示下次月度调度刷新时间）
修复 v1.7.8:
  - 命名统一：step2/3_usage 添加"本期"前缀（与 step1_usage 保持一致）
修复 v1.7.7:
  - 命名更精确："累计一阶用水量"改为"本年累计一阶用水量"（避免误解为从用水开始的全部累计）
修复 v1.7.6:
  - 传感器命名更清晰：step1_usage 改为"本期一阶用水量"，level_usage 改为"累计一阶用水量"
修复 v1.7.5:
  - 修复 items 未定义的 NameError bug
  - 修复 threshold1 过早引用问题（应在 items 解析后赋值）
  - 添加 state_class/device_class 属性（支持能源仪表盘）
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
  - 并发优化：批量抓取历史数据时并行请求，信号量控制+防限流延迟
  - 一次性初始化：添加标志位避免每次刷新重复触发批量初始化
  - 历史数据扩展：新增 read_date（抄表日期）、balance（余额）字段
"""
import asyncio
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
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "total_arrears": {
        "name": "总欠费",
        "icon": "mdi:alert-circle",
        "unit": "¥",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    # 最新账单
    "last_reading": {
        "name": "上期读数",
        "icon": "mdi:counter",
        "unit": "m³",
        "state_class": "measurement",
    },
    "current_reading": {
        "name": "本期读数",
        "icon": "mdi:counter",
        "unit": "m³",
        "state_class": "measurement",
    },
    "water_used": {
        "name": "本期用水量",
        "icon": "mdi:water",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "bill_amount": {
        "name": "账单金额",
        "icon": "mdi:receipt",
        "unit": "¥",
        "device_class": "monetary",
        "state_class": "measurement",
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
    # 阶梯信息
    "water_price_step1": {
        "name": "一阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "water_price_step2": {
        "name": "二阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "water_price_step3": {
        "name": "三阶水价",
        "icon": "mdi:currency-cny",
        "unit": "¥/m³",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "water_price_sewage": {
        "name": "污水处理费",
        "icon": "mdi:recycle",
        "unit": "¥/m³",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "price_threshold1": {
        "name": "一阶阈值",
        "icon": "mdi:stairs-up",
        "unit": "m³",
        "state_class": "measurement",
    },
    "price_threshold2": {
        "name": "二阶阈值",
        "icon": "mdi:stairs-up",
        "unit": "m³",
        "state_class": "measurement",
    },
    "step1_usage": {
        "name": "本期一阶用水量",
        "icon": "mdi:numeric-1-box",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "step2_usage": {
        "name": "本期二阶用水量",
        "icon": "mdi:numeric-2-box",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "step3_usage": {
        "name": "本期三阶用水量",
        "icon": "mdi:numeric-3-box",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "current_step": {
        "name": "当前阶梯",
        "icon": "mdi:stairs",
        "unit": None,
    },
    # 阶梯详情（从 price-info 接口获取）
    "level_usage": {
        "name": "本年累计一阶用水量",
        "icon": "mdi:numeric-1-box-outline",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "level_max": {
        "name": "一阶上限",
        "icon": "mdi:stairs-up",
        "unit": "m³",
        "state_class": "measurement",
    },
    "level_remaining": {
        "name": "阶梯剩余量",
        "icon": "mdi:water-outline",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "person_count": {
        "name": "家庭人口",
        "icon": "mdi:account-group",
        "unit": "人",
        "state_class": "measurement",
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
    # 预估与预警
    "estimated_monthly_usage": {
        "name": "预估月用水量",
        "icon": "mdi:chart-line",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "estimated_bill_amount": {
        "name": "预估本月账单",
        "icon": "mdi:calculator",
        "unit": "¥",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "account_warning": {
        "name": "账户预警",
        "icon": "mdi:alert",
        "unit": None,
    },
    "days_until_due": {
        "name": "距截止天数",
        "icon": "mdi:calendar-alert",
        "unit": "天",
    },
    "history_avg_usage": {
        "name": "历史月均用水",
        "icon": "mdi:history",
        "unit": "m³",
        "device_class": "water",
        "state_class": "measurement",
    },
    "usage_vs_avg": {
        "name": "与均值对比",
        "icon": "mdi:percent",
        "unit": "%",
        "state_class": "measurement",
    },
    # 状态
    "integration_status": {
        "name": "集成状态",
        "icon": "mdi:heart-pulse",
        "unit": None,
    },
    "last_update_time": {
        "name": "最后更新时间",
        "icon": "mdi:clock-outline",
        "unit": None,
    },
    "next_poll_time": {
        "name": "下次轮询时间",
        "icon": "mdi:clock-next",
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
    coordinator = WenzhouWaterDataUpdateCoordinator(hass, entry.entry_id, access_token, card_ids, day_of_month)

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

    def __init__(self, hass: HomeAssistant, entry_id: str, access_token: str, card_ids: list, day_of_month: int = 1):
        self.api = WenzhouWaterAPI(access_token)
        self._entry_id = entry_id  # 保存 entry_id 用于通知
        self.card_ids = card_ids  # 支持多水表
        self.day_of_month = day_of_month  # 保存月度调度日期
        # 历史初始化标志：避免每次刷新都重复触发批量初始化
        self._history_init_flags = {card_id: False for card_id in card_ids}
        # 初始化锁：防止并发重复初始化
        self._history_init_locks = {card_id: asyncio.Lock() for card_id in card_ids}
        # Token过期通知标志：避免重复发送通知
        self._token_expired_notified = False
        # Store 实例缓存（避免 HA 2026.4 中 hass.helpers.store 访问方式变化的问题）
        # 在 __init__ 中创建，保存到 hass.data 复用
        self._history_stores: Dict[str, Any] = {}
        for card_id in card_ids:
            key = f"{DOMAIN}_history_{card_id}"
            # 延迟到 hass 准备就绪时通过 property 访问器获取
            self._history_stores[card_id] = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),  # 兜底轮询间隔
        )

    def _get_history_store(self, card_id: str):
        """获取指定水表的历史 Store 实例（延迟初始化，复用）"""
        if self._history_stores.get(card_id) is None:
            try:
                from homeassistant.helpers.store import Store
                self._history_stores[card_id] = Store(
                    hass=self.hass,
                    key=f"{DOMAIN}_history_{card_id}",
                )
            except Exception as e:
                _LOGGER.error(f"创建历史 Store 失败（{card_id}）: {e}")
                return None
        return self._history_stores[card_id]

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
            # 阶梯单价
            "water_price_step1": 0,
            "water_price_step2": 0,
            "water_price_step3": 0,
            "water_price_sewage": 0,
            "price_threshold1": 0,
            "price_threshold2": 0,
            "price_threshold3": 0,
            # 阶梯详情
            "level_usage": 0,
            "level_max": 0,
            "level_remaining": 0,
            "person_count": 0,
            # 阶梯用水量
            "step1_usage": 0,
            "step2_usage": 0,
            "step3_usage": 0,
            "current_step": 1,
            # 预估
            "estimated_monthly_usage": 0,
            "estimated_bill_amount": 0,
            "account_warning": "正常",
            "days_until_due": 0,
            # 历史
            "history_avg_usage": 0,
            "usage_vs_avg": 0,
            # 诊断
            "last_update_time": "未知",
            "next_poll_time": "未知",
        }

    async def _load_billing_history(self, card_id: str) -> list:
        """从 HA Storage 加载历史账单数据"""
        try:
            store = self._get_history_store(card_id)
            if store is None:
                return []
            data = await store.async_load()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def _save_billing_history(self, card_id: str, card_result: dict, existing_history: list) -> None:
        """保存账单到历史记录（最多保留12个月）"""
        try:
            billing_month = card_result.get("billing_month", "")
            if not billing_month or billing_month == "未知":
                return

            # 检查本月是否已记录
            already_exists = any(h.get("billing_month") == billing_month for h in existing_history)
            if not already_exists:
                record = {
                    "billing_month": billing_month,
                    "water_used": card_result.get("water_used", 0),
                    "bill_amount": card_result.get("bill_amount", 0),
                }
                existing_history.append(record)

            # 只保留最近12个月
            existing_history.sort(key=lambda x: x.get("billing_month", ""), reverse=True)
            trimmed = existing_history[:12]

            store = self._get_history_store(card_id)
            if store is None:
                return
            await store.async_save(trimmed)
        except Exception as e:
            _LOGGER.error(f"保存历史记录失败（{card_id}）: {e}")

    async def _init_billing_history_from_api(self, card_id: str) -> list:
        """首次初始化：从 API 批量抓取历史账单（最多24个月）

        并发优化：每批6个月，最多4批并行请求，间隔500ms防限流
        """
        import asyncio as _asyncio
        from .api import WenzhouWaterAPI

        now = datetime.now()
        end_month = now.strftime("%Y%m")
        earliest = WenzhouWaterAPI.EARLIEST_BILLING_MONTH  # "202403"

        _LOGGER.info(f"温州水务：开始初始化历史账单（{card_id}），范围 {earliest} - {end_month}")

        # 分批规划：每批 6 个月
        batch_size = 6
        batches = []
        current_start = earliest
        while current_start <= end_month:
            current_end = WenzhouWaterAPI._calc_month(current_start, batch_size - 1)
            if current_end > end_month:
                current_end = end_month
            batches.append((current_start, current_end))
            current_start = WenzhouWaterAPI._calc_month(current_start, batch_size)

        _LOGGER.info(f"  规划 {len(batches)} 批次: {batches}")

        # 并发控制：最多同时 2 个请求，间隔 500ms 防限流
        semaphore = _asyncio.Semaphore(2)
        history = []
        fetch_errors = 0

        async def _fetch_batch(start: str, end: str) -> list:
            """抓取单个批次（受信号量控制）"""
            nonlocal fetch_errors
            async with semaphore:
                try:
                    _LOGGER.info(f"  抓取 {start} - {end}...")
                    bills = await self.api.get_bills(card_id, start, end)
                    await _asyncio.sleep(0.5)  # 防限流延迟
                    return bills
                except Exception as e:
                    _LOGGER.warning(f"  抓取 {start}-{end} 失败: {e}")
                    fetch_errors += 1
                    return []

        # 并行执行所有批次
        results = await _asyncio.gather(*[_fetch_batch(s, e) for s, e in batches])
        for bills in results:
            for bill in bills:
                bm = bill.get("billingMonth", "")
                if not bm:
                    continue
                history.append({
                    "billing_month": bm,
                    "water_used": float(bill.get("readWater", 0) or 0),
                    "bill_amount": float(bill.get("amount", 0) or 0),
                    "read_date": bill.get("readDate", ""),  # 扩展：保存抄表日期
                    "balance": float(bill.get("balance", 0) or 0),  # 扩展：保存余额
                })

        # 去重（按 billing_month）+ 排序
        seen = set()
        unique = []
        for h in history:
            bm = h.get("billing_month", "")
            if bm and bm not in seen:
                seen.add(bm)
                unique.append(h)
        unique.sort(key=lambda x: x.get("billing_month", ""), reverse=True)

        # 只保留最近12个月
        result = unique[:12]
        _LOGGER.info(f"  历史账单初始化完成，共 {len(result)} 条（失败 {fetch_errors} 批次）")

        # 保存到 Storage
        if result:
            try:
                store = self._get_history_store(card_id)
                if store:
                    await store.async_save(result)
            except Exception as e:
                _LOGGER.error(f"  保存历史账单失败: {e}")

        return result

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

            # 3.5 获取阶梯信息（从专用接口获取，优先级最高）
            try:
                price_info = await self.api.get_price_info(card_id)
                if price_info:
                    # 直接使用 API 返回的阶梯数据，不再用账单推断
                    api_current_step = price_info.get("priceLevel", 1)
                    level_usage = price_info.get("levelUsage", 0)
                    level_max = price_info.get("levelMax", 240)
                    person_count = price_info.get("personCount", 1)
                    price_type = price_info.get("priceName", "未知")

                    card_result["current_step"] = api_current_step
                    card_result["level_usage"] = level_usage
                    card_result["level_max"] = level_max
                    card_result["level_remaining"] = max(0, level_max - level_usage)
                    card_result["person_count"] = person_count
                    card_result["price_type"] = price_type

                    # 从 price-info 顶层字段读取阶梯价格（顶层的 priceStep1/2/3 通常为 0 或不存在）
                    water_price_step1 = float(price_info.get("priceStep1", 0) or 0)
                    water_price_step2 = float(price_info.get("priceStep2", 0) or 0)
                    water_price_step3 = float(price_info.get("priceStep3", 0) or 0)

                    # 从 items 中解析阶梯阈值和污水处理费
                    # items[] 中 price=0 是 API 格式问题，真实价格从 bills details 兜底
                    items = price_info.get("items", []) or []
                    threshold1 = float(price_info.get("levelMax", 0) or 0)  # 兜底
                    threshold2 = 0.0
                    threshold3 = 0.0
                    water_price_sewage = 0.0
                    for item in items:
                        pi_name = item.get("piName", "")
                        level = int(item.get("level", -1) or -1)
                        end_water = float(item.get("endWater", -1) or -1)
                        if level == 1:
                            threshold1 = float(item.get("endWater", 0) or 0)
                        elif level == 2:
                            threshold2 = float(item.get("endWater", 0) or 0)
                        elif level == 3:
                            threshold3 = float(item.get("endWater", 0) or 0) if end_water > 0 else 0
                        elif pi_name == "代收污水处理费" and level == 0:
                            water_price_sewage = float(item.get("price", 0) or 0)

                    # 一阶阈值必须在 items 解析完成后才能赋值
                    card_result["price_threshold1"] = threshold1
                    card_result["water_price_step1"] = water_price_step1
                    card_result["water_price_step2"] = water_price_step2
                    card_result["water_price_step3"] = water_price_step3
                    card_result["water_price_sewage"] = water_price_sewage
                    card_result["price_threshold2"] = threshold2  # 二阶上限
                    card_result["price_threshold3"] = threshold3  # 三阶上限（0表示无上限）

                    _LOGGER.debug(f"  阶梯信息: {card_id} - {price_type}, 当前{api_current_step}阶, 已用{level_usage}m³, 剩余{level_max - level_usage}m³, 价格: ¥{water_price_step1}/{water_price_step2}/{water_price_step3}, 污水费: ¥{water_price_sewage}")
            except WenzhouWaterTokenExpiredError as e:
                _LOGGER.error(f"Token已过期（{card_id}）: {e}")
                token_expired = True
                card_error_count += 1
            except Exception as e:
                _LOGGER.error(f"获取阶梯信息失败（{card_id}）: {e}")
                card_error_count += 1

            # 3. 获取账单（补充其他数据）
            try:
                bills = await self.api.get_bills(card_id)
                if bills and len(bills) > 0:
                    bill = bills[0]
                    card_result["billing_month"] = bill.get("billingMonth", "未知")
                    card_result["last_reading"] = float(bill.get("lastReading", 0) or 0)
                    card_result["current_reading"] = float(bill.get("reading", 0) or 0)
                    card_result["water_used"] = float(bill.get("readWater", 0) or 0)
                    card_result["bill_amount"] = float(bill.get("amount", 0) or 0)
                    card_result["last_read_date"] = bill.get("lastReadDate", "未知")
                    card_result["current_read_date"] = bill.get("readDate", "未知")
                    card_result["due_date"] = bill.get("chargeLimitTime", "未知")

                    # 从账单 details[] 提取各阶梯用水量（pi=580 基本水价的 level 分组）
                    # 同时提取阶梯单价（兜底：某些水表 price-info 不返回 priceStep1/2/3）
                    step1_usage = 0.0
                    step2_usage = 0.0
                    step3_usage = 0.0
                    bill_step1_price = 0.0
                    bill_step2_price = 0.0
                    bill_step3_price = 0.0
                    bill_sewage_price = 0.0
                    details = bill.get("details", [])
                    for d in details:
                        level = int(d.get("level", 0) or 0)
                        water = float(d.get("water", 0) or 0)
                        price = float(d.get("price", 0) or 0)
                        pi = int(d.get("pi", 0) or 0)
                        pi_name = d.get("piName", "")
                        # 基本水价 (pi=580) 的阶梯信息
                        if pi == 580:
                            if level == 1:
                                step1_usage += water
                                bill_step1_price = price
                            elif level == 2:
                                step2_usage += water
                                bill_step2_price = price
                            elif level == 3:
                                step3_usage += water
                                bill_step3_price = price
                        # 污水处理费 (pi=581)
                        elif pi == 581 and level == 0:
                            bill_sewage_price = price
                    card_result["step1_usage"] = round(step1_usage, 2)
                    card_result["step2_usage"] = round(step2_usage, 2)
                    card_result["step3_usage"] = round(step3_usage, 2)

                    # 兜底：如果 price-info 未返回阶梯价格，从账单 details 提取
                    if card_result.get("water_price_step1", 0) == 0 and bill_step1_price > 0:
                        card_result["water_price_step1"] = bill_step1_price
                    if card_result.get("water_price_step2", 0) == 0 and bill_step2_price > 0:
                        card_result["water_price_step2"] = bill_step2_price
                    if card_result.get("water_price_step3", 0) == 0 and bill_step3_price > 0:
                        card_result["water_price_step3"] = bill_step3_price
                    if card_result.get("water_price_sewage", 0) == 0 and bill_sewage_price > 0:
                        card_result["water_price_sewage"] = bill_sewage_price

                    # 账单中的阶梯信息仅作备用（如果 price-info 未获取到）
                    if card_result.get("current_step") is None:
                        import re
                        price_name = bill.get("priceName", "")
                        step_match = re.search(r'(\d)阶', price_name)
                        card_result["current_step"] = int(step_match.group(1)) if step_match else 1
                        card_result["price_type"] = price_name
                        # 账单中没有阈值信息，设置默认值
                        if card_result.get("price_threshold1") is None:
                            card_result["price_threshold1"] = 240.0  # 默认一阶上限
                            card_result["price_threshold2"] = 420.0  # 默认二阶上限
                            card_result["price_threshold3"] = 0      # 无上限
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
            # 发送 Token 过期通知（只发送一次）
            if not self._token_expired_notified:
                self._token_expired_notified = True
                try:
                    from . import async_token_expired_notification
                    await async_token_expired_notification(self.hass, self._entry_id)
                except Exception as e:
                    _LOGGER.error(f"发送Token过期通知失败: {e}")

        # 计算新增传感器：预估月用水量、账户预警、历史均值
        from datetime import datetime as dt
        today = dt.now()
        day_of_month = today.day
        days_in_month = calendar.monthrange(today.year, today.month)[1]

        for card_id in self.card_ids:
            card_result = result[card_id]
            current_usage = card_result.get("water_used", 0)

            # 预估月用水量 = 当前用量 / 当天 × 月总天数
            if day_of_month > 0 and current_usage > 0:
                estimated = round(current_usage / day_of_month * days_in_month, 2)
                card_result["estimated_monthly_usage"] = estimated
            else:
                card_result["estimated_monthly_usage"] = current_usage

            # 计算预估本月账单（根据预估用水量估算）
            estimated_usage = card_result.get("estimated_monthly_usage", 0)
            price_step1 = card_result.get("water_price_step1", 0)
            price_step2 = card_result.get("water_price_step2", 0)
            price_step3 = card_result.get("water_price_step3", 0)
            price_sewage = card_result.get("water_price_sewage", 0)
            threshold1 = card_result.get("price_threshold1", 17)
            threshold2 = card_result.get("price_threshold2", 30)

            # 优先使用账单中真实阶梯用量计算预估账单（更准确）
            real_step1 = card_result.get("step1_usage", 0)
            real_step2 = card_result.get("step2_usage", 0)
            real_step3 = card_result.get("step3_usage", 0)
            # 如果阶梯用量都>0，说明是真实数据，直接用；否则按预估用量估算
            if real_step1 + real_step2 + real_step3 > 0:
                s1 = real_step1
                s2 = real_step2
                s3 = real_step3
                _LOGGER.debug(f"  预估账单使用账单阶梯用量: {card_id} - {s1}/{s2}/{s3}m³")
            elif estimated_usage > 0:
                # 按预估用量估算阶梯分段
                if estimated_usage <= threshold1:
                    s1 = estimated_usage
                    s2 = 0
                    s3 = 0
                elif estimated_usage <= threshold2:
                    s1 = threshold1
                    s2 = round(estimated_usage - threshold1, 2)
                    s3 = 0
                else:
                    s1 = threshold1
                    s2 = round(threshold2 - threshold1, 2)
                    s3 = round(estimated_usage - threshold2, 2)
            else:
                s1, s2, s3 = 0, 0, 0

            if s1 + s2 + s3 > 0:
                # 预估账单 = 水费 + 污水处理费（不含 pi=583 免税自来水）
                estimated_water = s1 * price_step1 + s2 * price_step2 + s3 * price_step3
                estimated_sewage = (s1 + s2 + s3) * price_sewage
                card_result["estimated_bill_amount"] = round(estimated_water + estimated_sewage, 2)
            else:
                card_result["estimated_bill_amount"] = 0

            # 计算距截止日期天数
            due_date_str = card_result.get("due_date", "")
            if due_date_str and due_date_str != "未知":
                try:
                    # 尝试解析日期格式
                    due_date = None
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
                        try:
                            due_date = dt.strptime(due_date_str[:10], fmt)
                            break
                        except ValueError:
                            continue
                    if due_date:
                        days_left = (due_date.date() - today.date()).days
                        card_result["days_until_due"] = days_left
                except Exception:
                    card_result["days_until_due"] = 0
            else:
                card_result["days_until_due"] = 0

            # 账户预警
            balance = card_result.get("account_balance", 0)
            bill_amount = card_result.get("bill_amount", 0)
            if balance <= 0:
                card_result["account_warning"] = "余额为0，请及时充值"
            elif balance < bill_amount:
                card_result["account_warning"] = f"余额不足（余额¥{balance:.2f}）"
            elif balance < 50:
                card_result["account_warning"] = f"余额偏低（¥{balance:.2f}）"
            else:
                card_result["account_warning"] = "正常"

            # 历史均值（通过 billing_history 计算）
            history = await self._load_billing_history(card_id)

            # 首次初始化：历史数据少于2条时，使用锁机制批量从API抓取
            # 使用标志位确保只触发一次，避免每次刷新都检查
            if not self._history_init_flags.get(card_id, False) and len(history) < 2:
                self._history_init_flags[card_id] = True  # 先标记，避免并发
                _LOGGER.info(f"历史数据不足（{len(history)}条），开始批量初始化...")
                init_history = await self._init_billing_history_from_api(card_id)
                if init_history:
                    history = init_history
                else:
                    # 初始化失败，重置标志以便下次重试
                    self._history_init_flags[card_id] = False

            if history:
                total = sum(h.get("water_used", 0) for h in history)
                avg = round(total / len(history), 2) if history else 0
                card_result["history_avg_usage"] = avg
                # 与均值对比
                if avg > 0:
                    vs_pct = round((current_usage - avg) / avg * 100, 1)
                    card_result["usage_vs_avg"] = vs_pct
                else:
                    card_result["usage_vs_avg"] = 0
                # 更新历史记录（追加当前月份）
                await self._save_billing_history(card_id, card_result, history)
            else:
                # 无历史，初始化
                await self._save_billing_history(card_id, card_result, [])
                card_result["history_avg_usage"] = current_usage
                card_result["usage_vs_avg"] = 0

        # 设置最后更新时间和下次轮询时间（所有水表统一）
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        next_poll = _compute_next_monthly_run(self.day_of_month)
        next_poll_str = next_poll.strftime("%Y-%m-%d %H:%M:%S")
        for card_id in self.card_ids:
            result[card_id]["last_update_time"] = now_str
            result[card_id]["next_poll_time"] = next_poll_str

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

        # 从 SENSOR_TYPES 读取 state_class / device_class（支持能源仪表盘）
        sensor_cfg = SENSOR_TYPES.get(sensor_id, {})
        self._attr_device_class = sensor_cfg.get("device_class")
        self._attr_state_class = sensor_cfg.get("state_class")

    @property
    def unique_id(self) -> str:
        # unique_id 包含 card_id，确保多水表时实体不冲突
        return f"{DOMAIN}_{self.card_id}_{self.sensor_id}"

    @property
    def name(self) -> str:
        # 实体名仅保留传感器类型名（设备名已含 card_name）
        return SENSOR_TYPES[self.sensor_id]["name"]

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
        value = card_data.get(self.sensor_id)

        # current_step 显示为"第X阶梯"
        if self.sensor_id == "current_step" and isinstance(value, int):
            return f"第{value}阶梯"

        # usage_vs_avg 返回数值（unit="%"，HA 要求数值型传感器必须返回 float）
        if self.sensor_id == "usage_vs_avg" and isinstance(value, (int, float)):
            return round(float(value), 1)

        # account_warning 返回字符串状态
        if self.sensor_id == "account_warning":
            return str(value) if value else "正常"

        # days_until_due 负数显示为逾期
        if self.sensor_id == "days_until_due" and isinstance(value, int):
            if value < 0:
                return f"已逾期{-value}天"
            elif value == 0:
                return "今天截止"
            else:
                return value

        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        return SENSOR_TYPES[self.sensor_id].get("unit")

    @property
    def icon(self) -> str | None:
        base_icon = SENSOR_TYPES[self.sensor_id].get("icon")
        # account_warning 根据预警级别动态改图标
        if self.sensor_id == "account_warning":
            card_data = self.coordinator.data.get(self.card_id, {}) if self.coordinator.data else {}
            warning = card_data.get("account_warning", "正常")
            if "0" in warning or "余额为0" in warning:
                return "mdi:alert-octagon"
            elif "不足" in warning:
                return "mdi:alert-circle"
            elif "偏低" in warning:
                return "mdi:alert"
            else:
                return "mdi:check-circle"
        # current_step 根据阶梯级别显示不同图标
        if self.sensor_id == "current_step":
            card_data = self.coordinator.data.get(self.card_id, {}) if self.coordinator.data else {}
            step = card_data.get("current_step", 1)
            if step == 1:
                return "mdi:numeric-1-box-outline"
            elif step == 2:
                return "mdi:numeric-2-box-outline"
            else:
                return "mdi:numeric-3-box-outline"
        # days_until_due 根据天数显示不同图标
        if self.sensor_id == "days_until_due":
            card_data = self.coordinator.data.get(self.card_id, {}) if self.coordinator.data else {}
            days = card_data.get("days_until_due", 0)
            if days < 0:
                return "mdi:alert-circle"
            elif days <= 3:
                return "mdi:alert"
            else:
                return "mdi:calendar-check"
        return base_icon

    @property
    def extra_state_attributes(self) -> dict:
        """额外状态属性"""
        card_data = self.coordinator.data.get(self.card_id, {}) if self.coordinator.data else {}
        raw_status = card_data.get("integration_status", "unknown")
        attrs = {
            "card_id": self.card_id,
            "card_name": self.card_name,
            "last_update": self.coordinator.last_update_success,
            "integration_status": raw_status,
            "integration_status_cn": INTEGRATION_STATUS.get(raw_status, raw_status),
        }
        # Token 过期时添加操作指引
        if raw_status == "token_expired":
            attrs["操作指引"] = "请在集成配置中重新输入 Token 或刷新授权"
            attrs["help_url"] = "https://github.com/C3H3-AI/ha-wenzhou-water"
        return attrs

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
