# 温州水务 Home Assistant 集成

![Version](https://img.shields.io/badge/version-v0.0.2-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.4%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

通过 Home Assistant 集成查看水务账单、用水量、欠费等信息。

## 安装

### 方法1: HACS 安装
1. 打开 HACS
2. 点击 Integrations
3. 点击右上角 ⋮ → Custom repositories
4. 添加: `https://github.com/C3H3-AI/ha-wenzhou-water`
5. 搜索并安装 "温州水务"

### 方法2: 手动安装
```bash
# 复制到 custom_components 目录
cp -r wenzhou_water ~/.homeassistant/custom_components/
```

## 配置

### 获取 Access Token（通过 HAR 抓包）
1. 打开浏览器开发者工具 → Network → 勾选 Preserve log
2. 打开微信**温州水务**小程序并登录
3. 登录后，在 Network 中找到任意一个 `sw-os.wzgytz.com` 的请求
4. 复制请求头中的 `Authorization` 值（Bearer 后面那一串）
5. 或导出 HAR 文件，从请求头中提取 access_token

### 2. 添加集成
1. HA → 设置 → 设备与服务 → 添加集成
2. 搜索 **温州水务**
3. 粘贴 `access_token`
4. 选择对应的水表
5. 完成配置

## 传感器

安装后会创建以下传感器:

| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_account_balance` | 账户余额 | ¥ |
| `sensor.wenzhou_water_total_arrears` | 总欠费 | ¥ |
| `sensor.wenzhou_water_last_reading` | 上期读数 | m³ |
| `sensor.wenzhou_water_current_reading` | 本期读数 | m³ |
| `sensor.wenzhou_water_water_used` | 本期用水量 | m³ |
| `sensor.wenzhou_water_bill_amount` | 账单金额 | ¥ |
| `sensor.wenzhou_water_last_read_date` | 上期抄表日期 | - |
| `sensor.wenzhou_water_current_read_date` | 本期抄表日期 | - |
| `sensor.wenzhou_water_due_date` | 缴费截止日期 | - |
| `sensor.wenzhou_water_meter_address` | 用水地址 | - |
| `sensor.wenzhou_water_meter_station` | 所属营业厅 | - |
| `sensor.wenzhou_water_price_type` | 水价类型 | - |
| `sensor.wenzhou_water_integration_status` | 集成状态 | - |

## 配置选项

### 数据更新间隔

支持多种更新频率：

| 单位 | 说明 | 示例 |
|------|------|------|
| **小时** | 每N小时更新一次 | 1, 2, 3, 6, 12, 24 |
| **天** | 每天指定时间更新 | 每天 08:00 |
| **周** | 每周指定星期几更新 | 每周一、周三、周五 |
| **月** | 每月指定日期更新 | 每月 1, 15 号 |

## 技术信息

- API: `sw-os.wzgytz.com`
- 认证: Bearer Token（从 HAR 抓包提取）
- 平台: cloud_polling
- 更新: 可配置间隔（1-24小时）

## 故障排除

### 无法获取数据
- 检查 access_token 是否有效
- 重新抓包获取新的 access_token
- 检查网络连接

### 水表列表为空
- 确认账号下有绑定水表
- 检查 access_token 是否正确
