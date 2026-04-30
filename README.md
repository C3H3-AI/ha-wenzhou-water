# 温州水务 - Home Assistant 集成

乐清市温州水务集团智能水表数据接入 Home Assistant。

## 功能

- 实时水量查询
- 阶梯水价展示
- 预估账单计算
- 历史账单记录
- 月度用量趋势

## 安装

### 通过 HACS 安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS → 集成 中，点击右上角菜单 → 添加自定义仓库
3. 填入仓库地址：`https://github.com/C3H3-AI/ha-wenzhou-water`
4. 搜索"温州水务"并安装

### 手动安装

将 `custom_components/wenzhou_water/` 目录复制到 Home Assistant 的 `config/custom_components/` 目录下。

## 配置

1. 重启 Home Assistant
2. 进入 设置 → 设备与服务 → 添加集成
3. 搜索"温州水务"并添加
4. **输入注册在水务账户的手机号**，接收验证码
5. 输入短信验证码
6. 选择要监控的水表和每月更新日期

## 仪表盘卡片

### 统一账单卡片（推荐）

推荐使用 [统一账单卡片](https://github.com/C3H3-AI/ha-utility-bill-card)，同时支持温州水务和华润燃气。

1. **通过 HACS 安装卡片**
   - 在 HACS → 仪表盘 中搜索"utility-bill-card"
   - 或手动添加仓库：`https://github.com/C3H3-AI/ha-utility-bill-card`

2. **添加卡片到仪表盘**
   - 打开任意仪表盘，点击右上角"编辑"
   - 点击"添加卡片"
   - 选择"手动配置"
   - 粘贴以下配置：

   ```yaml
   type: custom:ha-utility-bill-card
   entity: sensor.wenzhou_water_账户余额
   title: 温州水务
   ```

## 版本历史

- **v2.0.0**: 取消手动 Token 登录，仅支持短信验证码登录，简化配置流程
- **v1.9.0**: 新增短信验证码登录方式
- **v1.7.0**: 支持多水表和月度轮询

## 支持

- 问题反馈：https://github.com/C3H3-AI/ha-wenzhou-water/issues
- Home Assistant 版本：2024.1.0+
