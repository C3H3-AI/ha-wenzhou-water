"""温州水务集成常量"""

# 平台
DOMAIN = "wenzhou_water"
PLATFORM_NAME = "温州水务"

# API配置
BASE_URL = "https://sw-os.wzgytz.com/v3/open-api"
API_TIMEOUT = 30

# 配置键
CONF_ACCESS_TOKEN = "access_token"
CONF_METER_CARD_ID = "meter_card_id"
CONF_METER_CARD_NAME = "meter_card_name"
CONF_METER_CARD_ADDRESS = "meter_card_address"
CONF_METER_CARDS = "meter_cards"  # 多水表列表，每个元素为 {cardId, cardName, cardAddress}

# 扫描间隔配置（仅支持月模式）
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCAN_INTERVAL_UNIT = "scan_interval_unit"
SCAN_INTERVAL_UNITS = {
    "month": "月（每月X号更新）",
}

# 默认扫描间隔
DEFAULT_SCAN_INTERVAL_VALUE = 1    # 每月1号
DEFAULT_SCAN_INTERVAL_UNIT = "month"

# 集成状态定义
INTEGRATION_STATUS = {
    "normal": "正常",
    "token_expired": "密钥过期",
    "network_error": "网络异常",
    "config_error": "配置错误",
    "api_error": "API错误",
}
