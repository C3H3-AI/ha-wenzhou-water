"""温州水务集成常量 - v5.0.0

v5.0.0: 基于 wz_water_sg 架构重写
  - 新增 ConfigFlow step ID 常量
  - 新增错误码常量
  - 新增登录方式常量
"""

# 平台
DOMAIN = "wenzhou_water"
PLATFORM_NAME = "温州水务"

# API配置
BASE_URL = "https://sw-os.wzgytz.com/v3/open-api"
API_TIMEOUT = 30

# 配置键
CONF_ACCESS_TOKEN = "access_token"
CONF_MOBILE = "mobile"
CONF_SMS_CODE = "sms_code"
CONF_LOGIN_TYPE = "login_type"
CONF_REFRESH_QR_CODE = "refresh_qr_code"
CONF_GENERAL_ERROR = "base"

CONF_METER_CARD_ID = "meter_card_id"
CONF_METER_CARD_NAME = "meter_card_name"
CONF_METER_CARD_ADDRESS = "meter_card_address"
CONF_METER_CARDS = "meter_cards"  # 多水表列表

# 扫描间隔配置（仅支持月模式）
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCAN_INTERVAL_UNIT = "scan_interval_unit"
SCAN_INTERVAL_UNITS = {
    "month": "月（每月X号更新）",
}
DEFAULT_SCAN_INTERVAL_VALUE = 1
DEFAULT_SCAN_INTERVAL_UNIT = "month"

# ConfigFlow Step IDs（wz_water_sg 架构）
STEP_USER = "user"
STEP_SMS_LOGIN = "sms_login"
STEP_SMS_VERIFY = "sms_verify"
STEP_WX_QR_LOGIN = "wx_qr_login"
STEP_QR_LOGIN = "qr_login"
STEP_SELECT_METER = "select_meter"

# 登录方式
LOGIN_SMS = "sms"
LOGIN_WECHAT = "wechat"

# 错误码
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"
ERROR_QR_NOT_SCANNED = "qr_not_scanned"
ERROR_SCAN_EXPIRED = "scan_expired"
ERROR_TOKEN_FAILED = "token_failed"

# 微信常量
WX_APPID = "wx7a3434ca2a0bb80d"
WX_POLL_URL = "https://lp.open.weixin.qq.com/connect/l/qrconnect"
WX_REDIRECT_URI = "https%3A%2F%2Fsw-os.wzgytz.com%2Flogin"
WX_TOKEN_URL = "https://sw-os.wzgytz.com/v3/open-api/system/auth/sign-in"
WX_API_TIMEOUT = 15

# 集成状态定义
INTEGRATION_STATUS = {
    "normal": "正常",
    "token_expired": "密钥过期",
    "network_error": "网络异常",
    "config_error": "配置错误",
    "api_error": "API错误",
}
