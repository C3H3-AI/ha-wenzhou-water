# Changelog

## [4.2.1] - 2026-09-13

### Fixed

- billing_month 排序 str/int 类型兼容（HA 在线修复同步）

## [4.2.0] - 2026-09-13

### Added

- water-statistics-card：用水对比统计卡片（friendly_name 动态匹配）

## [4.1.0] - 2026-07

### Fixed

- 保持偏移但逐月补缺，防能源面板负值
- EARLIEST_BILLING_MONTH 改为动态计算（当前月-2年滑动窗口）

## [4.0.1] - 2026-07

### Fixed

- 能源面板负数修复 + 历史扩展 24 月
- 账单月份偏移：账单月映射到实际用水月 (billingMonth-1)

## [3.2.0] - 2025

- 使用 segno 生成二维码实现尺寸可控
