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

## 支持

- 问题反馈：https://github.com/C3H3-AI/ha-wenzhou-water/issues
- Home Assistant 版本：2024.1.0+
