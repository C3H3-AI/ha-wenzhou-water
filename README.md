# 温州水务 - Home Assistant 集成

![Version](https://img.shields.io/badge/version-v4.0.3-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.4%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

温州水务集团智能水表数据接入 Home Assistant，支持短信验证码和微信扫码登录。

## 安装

### HACS 安装（推荐）
1. 确保已安装 [HACS](https://hacs.xyz/)
2. HACS → 集成 →右上角菜单 → 添加自定义仓
3. 填入仓库：`https://github.com/C3H3-AI/ha-wenzhou-water`
4. 搜索"温州水务"并安装

### 手动安装
将 `custom_components/wenzhou_water/` 复制到 HA 的 `config/custom_components/` 目录。

## 配置

1. 重启 Home Assistant
2. 设置 → 设备与服务 → 添加集成 → 搜索"温州水务"
3. 登录方式：
   - **微信扫码**：扫描二维码 → 授权 → 提交（默认）
   - **短信验证**：输入手机号 → 收验证码 → 提交
4. 选择水表和更新日期（默认每月7日）

### 有效期
- 登录有效期约 6 个月
- 过期后集成会发送通知，重新登录即可

## 传感器

### 主要传感器
| 传感器 | 说明 | 单位 |
|--------|------|------|
| 账户余额 | 账户余额 | ¥ |
| 总欠费 | 总欠费 | ¥ |
| 本期用水量 | 本期用水量 | m³ |
| 本期账单 | 账单金额 | ¥ |
| 距截止天数 | 缴费截止倒计时 | 天 |
| 集成状态 | 连接状态 | - |

### 完整列表
详见代码 `sensor.py`，包含：
- 账户与账单（余额、欠费、预警）
- 用水量（本期、历史、阶梯用量）
- 阶梯水价（一二三阶价格、阈值）
- 日期与状态（抄表日期、更新状态）
- 水表信息（地址、营业厅、水价类型）
- 按钮（刷新数据、获取历史）

## 仪表盘卡片

推荐使用 [统一账单卡片](https://github.com/C3H3-AI/ha-utility-bill-card)：

```yaml
type: custom:ha-utility-bill-card
entity: sensor.wenzhou_water_账户余额
title: 温州水务
```

## 故障排除

- **数据不更新**：检查网络、重启 HA Core
- **登录过期**：集成会通知，重新配置即可
- **问题反馈**：https://github.com/C3H3-AI/ha-wenzhou-water/issues

## 更新日志

### v4.0.2 (2026-06-23)
- 🐛 **账单月份偏移修正** — 月初出账的水务账单，统计记录映射到实际用水月份（billingMonth - 1）
- 🔧 **重启稳定性修复** — 重启后立即恢复传感器状态值，防止生成 sum=0 统计记录

### v4.0.1 (2026-06-23)
- 🐛 **修复能源面板负数问题** — 账单未出时累计值保持上次值，不跌为0
- ✨ **历史数据扩展** — 从12个月扩展到24个月

### v3.1.0
- ✨ 微信扫码登录 UI 优化
- ✨ 登录方式选择优化（输入手机号切换短信验证）
- 🐛 修复翻译缺失问题

### v3.0.0
- ✨ 新增微信扫码登录
- ✨ 支持重新配置切换登录方式

### 更早版本
详见 [GitHub Releases](https://github.com/C3H3-AI/ha-wenzhou-water/releases)
