# 温州水务 - Home Assistant 集成

![Version](https://img.shields.io/badge/version-v3.0.1-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.4%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

乐清市温州水务集团智能水表数据接入 Home Assistant，支持短信验证码和微信扫码两种登录方式。

## 安装

### 方法1: HACS 安装（推荐）
1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS → 集成 中，点击右上角菜单 → 添加自定义仓
3. 填入仓库地址：`https://github.com/C3H3-AI/ha-wenzhou-water`
4. 类别选择 `Integration`
5. 搜索"温州水务"并安装

### 方法2: 手动安装
将 `custom_components/wenzhou_water/` 目录复制到 Home Assistant 的 `config/custom_components/` 目录下。

## 配置

1. 重启 Home Assistant
2. 进入 设置 → 设备与服务 → 添加集成
3. 搜索"温州水务"并添加
4. **选择登录方式**：
   - **短信验证码登录**：输入注册在水务账户的手机号 → 收到验证码 → 输入
   - **微信扫码登录**：使用微信扫描二维码 → 授权 → 点击提交
5. 选择要监控的水表和每月更新日期

### Token 说明
- 登录后获取的 Token 有效期约 6 个月
- Token 过期后集成会发送通知提醒重新登录
- ⚠️ 短信登录 Token 对数据 API 可能返回 401（与小程序身份不同），建议优先使用微信扫码

## 传感器

安装后创建以下传感器：

### 账户与账单
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_账户余额` | 账户余额 | ¥ |
| `sensor.wenzhou_water_总欠费` | 总欠费 | ¥ |
| `sensor.wenzhou_water_账单金额` | 账单金额 | ¥ |
| `sensor.wenzhou_water_预估本月账单` | 预估本月账单 | ¥ |
| `sensor.wenzhou_water_账户预警` | 账户预警 | - |

### 用水量
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_上期读数` | 上期读数 | m³ |
| `sensor.wenzhou_water_本期读数` | 本期读数 | m³ |
| `sensor.wenzhou_water_本期用水量` | 本期用水量 | m³ |
| `sensor.wenzhou_water_本期一阶用水量` | 本期一阶用水量 | m³ |
| `sensor.wenzhou_water_本期二阶用水量` | 本期二阶用水量 | m³ |
| `sensor.wenzhou_water_本期三阶用水量` | 本期三阶用水量 | m³ |
| `sensor.wenzhou_water_预估月用水量` | 预估月用水量 | m³ |
| `sensor.wenzhou_water_历史月均用水` | 历史月均用水 | m³ |

### 阶梯水价
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_一阶水价` | 一阶水价 | ¥/m³ |
| `sensor.wenzhou_water_二阶水价` | 二阶水价 | ¥/m³ |
| `sensor.wenzhou_water_三阶水价` | 三阶水价 | ¥/m³ |
| `sensor.wenzhou_water_污水处理费` | 污水处理费 | ¥/m³ |
| `sensor.wenzhou_water_一阶阈值` | 一阶阈值 | m³ |
| `sensor.wenzhou_water_二阶阈值` | 二阶阈值 | m³ |
| `sensor.wenzhou_water_当前阶梯` | 当前阶梯 | - |
| `sensor.wenzhou_water_本年累计一阶用水量` | 本年累计一阶用水量 | m³ |
| `sensor.wenzhou_water_一阶上限` | 一阶上限 | m³ |
| `sensor.wenzhou_water_阶梯剩余量` | 阶梯剩余量 | m³ |
| `sensor.wenzhou_water_家庭人口` | 家庭人口 | 人 |

### 日期与状态
| 传感器实体 | 说明 | 单位 |
|------------|------|------|
| `sensor.wenzhou_water_上期抄表日期` | 上期抄表日期 | - |
| `sensor.wenzhou_water_本期抄表日期` | 本期抄表日期 | - |
| `sensor.wenzhou_water_缴费截止日期` | 缴费截止日期 | - |
| `sensor.wenzhou_water_距截止天数` | 距截止天数 | 天 |
| `sensor.wenzhou_water_集成状态` | 集成状态 | - |
| `sensor.wenzhou_water_最后更新时间` | 最后更新时间 | - |
| `sensor.wenzhou_water_下次轮询时间` | 下次轮询时间 | - |
| `sensor.wenzhou_water_与均值对比` | 与均值对比 | % |

### 水表信息
| 传感器实体 | 说明 |
|------------|------|
| `sensor.wenzhou_water_用水地址` | 用水地址 |
| `sensor.wenzhou_water_所属营业厅` | 所属营业厅 |
| `sensor.wenzhou_water_水价类型` | 水价类型 |

### 按钮
| 按钮实体 | 说明 |
|----------|------|
| `button.wenzhou_water_fetch_history` | 抓取所有历史记录 |
| `button.wenzhou_water_refresh_data` | 刷新数据 |

## 配置选项

### 数据更新间隔
| 单位 | 说明 | 示例 |
|------|------|------|
| 月 | 每月指定日期更新 | 每月 1 号 |

### 重新配置
- 进入 设置 → 设备与服务 → 温州水务 → 三个点 → 重新配置
- 支持切换登录方式（短信/微信扫码）

## 仪表盘卡片

推荐使用 [统一账单卡片](https://github.com/C3H3-AI/ha-utility-bill-card)，同时支持温州水务和华润燃气。

1. **通过 HACS 安装卡片**
   - 在 HACS → 仪表盘中搜索"utility-bill-card"
   - 或手动添加仓库：`https://github.com/C3H3-AI/ha-utility-bill-card`

2. **添加卡片到仪表盘**

   ```yaml
   type: custom:ha-utility-bill-card
   entity: sensor.wenzhou_water_账户余额
   title: 温州水务
   ```

## Automation 示例

```yaml
# 水费欠费提醒
automation:
  - alias: "水费欠费提醒"
    trigger:
      - platform: state
        entity_id: sensor.wenzhou_water_总欠费
    condition:
      - condition: numeric_state
        entity_id: sensor.wenzhou_water_总欠费
        above: 0
    action:
      - service: notify.notify
        data:
          message: "您有水费欠费 ¥{{ states('sensor.wenzhou_water_总欠费') }}"
```

## 故障排除

### Token 相关错误
- 短信登录 Token 可能无数据权限，建议使用微信扫码登录
- Token 过期后集成会发送通知，重新配置即可

### 数据不更新
- 检查网络连接
- 查看 HA 日志中的集成错误信息
- 尝试重启 HA Core

## 更新日志

### v3.0.1
- 📝 README 与代码完全同步（传感器列表、登录方式、配置说明）
- 📝 版本号同步更新

### v3.0.0
- ✨ 新增微信扫码登录（微信服务器二维码，移除 segno 依赖）
- ✨ async_show_menu 选择登录方式（短信/微信扫码）
- ✨ reconfigure 流程支持微信扫码重新登录
- 🐛 修复 state_class 兼容性（device_class=water/monetary + state_class）
- 🐛 修复 Store 导入路径（helpers.storage）
- 🔧 防重复添加（_abort_if_unique_id_configured）

### v2.1.1
- 🐛 修复 API 请求头（X-MCS-CHANNEL=2）

### v2.1.0
- 🔧 恢复手动 Token 登录（短信登录的 Token 无数据权限）

### v2.0.0
- ✨ 取消手动 Token 登录，仅支持短信验证码登录

### v1.9.0
- ✨ 新增短信验证码登录方式

### v1.7.0
- ✨ 支持多水表和月度轮询

## 支持

- 问题反馈：https://github.com/C3H3-AI/ha-wenzhou-water/issues
- Home Assistant 版本：2026.4+
