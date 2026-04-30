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
4. 输入水表号和户号

## 仪表盘卡片

### 统一账单卡片（推荐）

推荐使用 [统一账单卡片](https://github.com/C3H3-AI/ha-utility-bill-card)，同时支持温州水务和华润燃气。

1. **添加资源引用**
   - 进入 设置 → 仪表盘 → 资源
   - 点击"添加资源"
   - URL: `/local/community/utility-bill-card/utility-bill-card.js`
   - 类型: 选择 **JavaScript 模块**

2. **添加卡片到仪表盘**
   - 打开任意仪表盘，点击右上角"编辑"
   - 点击"添加卡片"
   - 选择"手动配置"（或在搜索中搜索）
   - 粘贴以下配置：

   ```yaml
   type: custom:utility-bill-card
   entity: sensor.wenzhou_water_账户余额
   title: 温州水务
   ```

## 支持

- 问题反馈：https://github.com/C3H3-AI/ha-wenzhou-water/issues
- Home Assistant 版本：2024.1.0+
