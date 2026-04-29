# 温州水务 Home Assistant 集成

![Version](https://img.shields.io/badge/version-v1.4.0-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.4%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

通过 Home Assistant 集成查看水务账单、用水量、水价、欠费等信息。支持多水表、历史趋势分析、账户预警。

## 功能亮点

- 多水表支持 - 同时监控多个水表
- 预估月用水量 - 根据当前进度推算月度用水
- 账户预警 - 余额不足/偏低实时提醒
- 历史趋势 - 最多保留12个月用水记录
- 自定义卡片 - Grid 四列布局，状态一目了然

## 安装

### 方法1: HACS 安装（推荐）
1. 打开 HACS
2. 点击 Integrations
3. 点击右上角 `?` → Custom repositories
4. 添加仓库地址: `https://github.com/C3H3-AI/ha-wenzhou-water`
5. 类别选择 `Integration`
6. 搜索并安装 "温州水务"

### 方法2: 手动安装
```bash
# 复制到 custom_components 目录
cp -r wenzhou_water ~/.homeassistant/custom_components/
```

## 配置

### 获取认证参数
登录微信 **温州水务** 小程序，从网络请求头中提取以下参数：

| 参数 | 说明 | 来源 |
|------|------|------|
| `Authorization` | Bearer Token | 请求头（Bearer 后面那一串） |

### 添加集成
1. HA → 设置 → 设备与服务 → 添加集成
2. 搜索 **温州水务**
3. 粘贴 `access_token`
4. 选择对应的水表（如有多个）
5. 完成配置

## 传感器

安装后为每个水表创建以下传感器（共22个）：

### 账户与余额
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_{cardId}_account_balance` | 账户余额 | ¥ |
| `sensor.wenzhou_water_{cardId}_total_arrears` | 总欠费 | ¥ |

### 账单信息
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_{cardId}_bill_amount` | 账单金额 | ¥ |
| `sensor.wenzhou_water_{cardId}_last_reading` | 上期读数 | m³ |
| `sensor.wenzhou_water_{cardId}_current_reading` | 本期读数 | m³ |
| `sensor.wenzhou_water_{cardId}_water_used` | 本期用水量 | m³ |
| `sensor.wenzhou_water_{cardId}_last_read_date` | 上期抄表日期 | - |
| `sensor.wenzhou_water_{cardId}_current_read_date` | 本期抄表日期 | - |
| `sensor.wenzhou_water_{cardId}_due_date` | 缴费截止日期 | - |

### 用水分析（v1.4.0 新增）
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_{cardId}_estimated_monthly_usage` | 预估月用水量 | m³ |
| `sensor.wenzhou_water_{cardId}_history_avg_usage` | 历史月均用水 | m³ |
| `sensor.wenzhou_water_{cardId}_usage_vs_avg` | 与均值对比 | % |

### 账户预警（v1.4.0 新增）
| 传感器实体 | 说明 |
|------------|------|
| `sensor.wenzhou_water_{cardId}_account_warning` | 账户预警状态 |

### 水价阶梯
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_{cardId}_water_price_step1` | 一阶水价 | ¥/m³ |
| `sensor.wenzhou_water_{cardId}_water_price_step2` | 二阶水价 | ¥/m³ |
| `sensor.wenzhou_water_{cardId}_water_price_step3` | 三阶水价 | ¥/m³ |
| `sensor.wenzhou_water_{cardId}_water_price_sewage` | 污水处理费 | ¥/m³ |

### 水表信息
| 传感器实体 | 说明 |
|------------|------|
| `sensor.wenzhou_water_{cardId}_meter_address` | 用水地址 |
| `sensor.wenzhou_water_{cardId}_meter_station` | 所属营业厅 |
| `sensor.wenzhou_water_{cardId}_price_type` | 水价类型 |
| `sensor.wenzhou_water_{cardId}_integration_status` | 集成状态 |

## Lovelace 卡片

集成自带自定义卡片，安装后可直接使用：

```yaml
# 示例：在仪表盘添加温州水务卡片
views:
  - cards:
      - type: custom:wenzhou-water-card
        entity: sensor.wenzhou_water_xxx_account_balance
        title: 温州水务
```

卡片特性：
- 四列 Grid 布局：余额、用水、账单、预估
- 二级信息行：预警状态、均值对比、截止日期
- 状态指示灯：正常（绿）/警告（橙）/错误（红）
- hover 动效与渐变背景

## 配置选项

### 数据更新间隔
每月指定日期更新（默认每月 1 日），可自定义日期。

### 多水表支持
支持同一个账号下的多个水表，每个水表独立一套传感器。可在集成设置中添加或移除水表。

## Automation 示例

```yaml
# 水费欠费提醒
automation:
  - alias: "水费欠费提醒"
    trigger:
      - platform: state
        entity_id: sensor.wenzhou_water_xxx_total_arrears
    condition:
      - condition: numeric_state
        entity_id: sensor.wenzhou_water_xxx_total_arrears
        above: 0
    action:
      - service: notify.notify
        data:
          message: "您有水费欠费 ¥{{ states('sensor.wenzhou_water_xxx_total_arrears') }}"

# 账户余额预警（v1.4.0）
automation:
  - alias: "账户余额偏低提醒"
    trigger:
      - platform: state
        entity_id: sensor.wenzhou_water_xxx_account_warning
    condition:
      - condition: template
        value_template: "{{ '正常' not in states('sensor.wenzhou_water_xxx_account_warning') }}"
    action:
      - service: notify.notify
        data:
          message: "水务账户预警：{{ states('sensor.wenzhou_water_xxx_account_warning') }}"
```

## 更新日志

### v1.4.0 (2026-04-29)
- ✨ 新增 3 个传感器：预估月用水量、账户预警、历史月均用水
- ✨ 新增 `usage_vs_avg` 传感器显示与历史均值对比
- 💾 数据持久化：历史记录保存至 HA Storage，最多保留12个月
- 🎨 新增 Lovelace 自定义卡片 `wenzhou-water-card`
- ⚡ account_warning 动态图标（正常/偏低/不足/为0四级）

### v1.3.5
- 修复账单明细缺少二阶/三阶水价解析

## 故障排除

### Token 相关错误
- 检查 access_token 是否正确
- Token 过期后需重新获取并重新配置集成

### 水表列表为空
- 确认账号下已绑定水表
- 确认 access_token 有效

### 数据不更新
- 检查网络连接
- 查看 HA 日志中的集成错误信息
- 尝试重启 HA Core