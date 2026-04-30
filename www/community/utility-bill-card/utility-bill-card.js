/**
 * 公用事业账单卡片 (Utility Bill Card) - v1.0.0
 * 统一支持温州水务和华润燃气的 Lovelace 自定义卡片
 *
 * 支持的集成:
 *   - 温州水务 (ha-wenzhou-water): entity 以 wenzhou_water 开头
 *   - 华润燃气 (ha-crcgas): entity 以 crcgas 开头
 *
 * 用法示例:
 *   # 华润燃气
 *   type: custom:utility-bill-card
 *   entity: sensor.crcgas_account_balance
 *   title: 华润燃气
 *
 *   # 温州水务
 *   type: custom:utility-bill-card
 *   entity: sensor.wenzhou_water_账户余额
 *   title: 温州水务
 */
(function () {
  'use strict';

  const CARD_VERSION = '1.0.0';

  class UtilityBillCard extends HTMLElement {
    setConfig(config) {
      if (!config.entity) {
        throw new Error('请指定 entity 参数');
      }
      this._config = {
        title: config.title || '公用事业',
        entity: config.entity,
        ...config,
      };
      this._hass = null;
      this._cardId = 'ubc-' + Math.random().toString(36).substr(2, 9);

      // 根据 entity 前缀识别类型
      const entityLower = config.entity.toLowerCase();
      if (entityLower.includes('wenzhou_water')) {
        this._type = 'water';
        this._icon = '💧';
        this._usageLabel = '本期用水';
        this._usageUnit = 'm³';
        this._progressLabel = '阶梯用水进度';
        this._avgLabel = '月均用水';
      } else {
        this._type = 'gas';
        this._icon = '🔥';
        this._usageLabel = '本期用气';
        this._usageUnit = 'm³';
        this._progressLabel = '阶梯用气进度';
        this._avgLabel = '月均用气';
      }

      if (this._cardEl) return;
      const card = document.createElement('div');
      card.id = this._cardId;
      card.className = 'ubc-container';
      card.innerHTML = `
        <div class="ubc-header">
          <div class="ubc-title">
            <span class="ubc-icon">${this._icon}</span>
            <span class="ubc-title-text">${this._config.title}</span>
          </div>
          <div class="ubc-status-dot" id="${this._cardId}-dot"></div>
        </div>
        <div class="ubc-grid">
          <div class="ubc-card ubc-card-balance" id="${this._cardId}-balance">
            <div class="ubc-card-label">账户余额</div>
            <div class="ubc-card-value ubc-value-balance">--</div>
            <div class="ubc-card-unit">¥</div>
          </div>
          <div class="ubc-card ubc-card-usage" id="${this._cardId}-usage">
            <div class="ubc-card-label">${this._usageLabel}</div>
            <div class="ubc-card-value ubc-value-usage">--</div>
            <div class="ubc-card-unit">${this._usageUnit}</div>
          </div>
          <div class="ubc-card ubc-card-step" id="${this._cardId}-step">
            <div class="ubc-card-label">当前阶梯</div>
            <div class="ubc-card-value ubc-value-step">--</div>
          </div>
          <div class="ubc-card ubc-card-estimated" id="${this._cardId}-estimated">
            <div class="ubc-card-label">预估账单</div>
            <div class="ubc-card-value ubc-value-estimated">--</div>
            <div class="ubc-card-unit">¥</div>
          </div>
        </div>
        <div class="ubc-progress-section" id="${this._cardId}-progress">
          <div class="ubc-progress-label">
            <span>${this._progressLabel}</span>
            <span id="${this._cardId}-progress-text">--</span>
          </div>
          <div class="ubc-progress-bar">
            <div class="ubc-progress-fill" id="${this._cardId}-progress-fill"></div>
          </div>
          <div class="ubc-step-info" id="${this._cardId}-step-info">
            <div class="ubc-step-item"><span class="ubc-step-num">一</span><span class="ubc-step-val" id="${this._cardId}-s1">--</span></div>
            <div class="ubc-step-item"><span class="ubc-step-num">二</span><span class="ubc-step-val" id="${this._cardId}-s2">--</span></div>
            <div class="ubc-step-item ubc-step-3"><span class="ubc-step-num">三</span><span class="ubc-step-val" id="${this._cardId}-s3">--</span></div>
          </div>
        </div>
        <div class="ubc-info-row">
          <div class="ubc-info-item">
            <span class="ubc-info-label">上月用量</span>
            <span class="ubc-info-value" id="${this._cardId}-last-month">--</span>
          </div>
          <div class="ubc-info-item">
            <span class="ubc-info-label">${this._avgLabel}</span>
            <span class="ubc-info-value" id="${this._cardId}-avg">--</span>
          </div>
          <div class="ubc-info-item">
            <span class="ubc-info-label">对比均值</span>
            <span class="ubc-info-value" id="${this._cardId}-vs-avg">--</span>
          </div>
        </div>
        <div class="ubc-footer">
          <span id="${this._cardId}-update">--</span>
        </div>
      `;
      this.appendChild(card);
      this._cardEl = card;
      this._injectStyles();
    }

    _injectStyles() {
      if (document.getElementById('utility-bill-card-styles')) return;
      const style = document.createElement('style');
      style.id = 'utility-bill-card-styles';
      style.textContent = `
        .ubc-container {
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
          border-radius: 16px;
          padding: 16px;
          color: #fff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 20px rgba(0,0,0,0.3);
          transition: all 0.3s ease;
          height: 100%;
          box-sizing: border-box;
        }
        .ubc-container:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 25px rgba(0,0,0,0.4);
        }
        .ubc-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .ubc-title { display: flex; align-items: center; gap: 8px; }
        .ubc-icon { font-size: 24px; }
        .ubc-title-text { font-size: 16px; font-weight: 600; }
        .ubc-status-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: #4ade80;
          box-shadow: 0 0 8px #4ade80;
        }
        .ubc-status-dot.warning { background: #fbbf24; box-shadow: 0 0 8px #fbbf24; }
        .ubc-status-dot.error { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
        .ubc-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }
        .ubc-card {
          background: rgba(255,255,255,0.1);
          border-radius: 12px;
          padding: 12px;
          text-align: center;
          transition: all 0.3s ease;
        }
        .ubc-card:hover { background: rgba(255,255,255,0.15); }
        .ubc-card-label { font-size: 11px; color: rgba(255,255,255,0.7); margin-bottom: 4px; }
        .ubc-card-value { font-size: 20px; font-weight: 700; }
        .ubc-card-unit { font-size: 11px; color: rgba(255,255,255,0.5); }
        .ubc-value-balance { color: #4ade80; }
        .ubc-value-usage { color: #38bdf8; }
        .ubc-value-step { color: #a78bfa; }
        .ubc-value-estimated { color: #fbbf24; }
        .ubc-progress-section {
          background: rgba(255,255,255,0.05);
          border-radius: 12px;
          padding: 12px;
          margin-bottom: 12px;
        }
        .ubc-progress-label {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
          color: rgba(255,255,255,0.7);
          margin-bottom: 8px;
        }
        .ubc-progress-bar {
          height: 8px;
          background: rgba(255,255,255,0.1);
          border-radius: 4px;
          overflow: hidden;
          margin-bottom: 8px;
        }
        .ubc-progress-fill {
          height: 100%;
          border-radius: 4px;
          background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ef4444);
          transition: width 0.5s ease;
        }
        .ubc-step-info {
          display: flex;
          justify-content: space-around;
          font-size: 12px;
        }
        .ubc-step-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2px;
        }
        .ubc-step-item.ubc-step-3 { opacity: 0.7; }
        .ubc-step-num { color: rgba(255,255,255,0.5); font-size: 10px; }
        .ubc-step-val { color: #fff; font-weight: 600; }
        .ubc-info-row {
          display: flex;
          justify-content: space-between;
          padding: 8px 0;
          border-top: 1px solid rgba(255,255,255,0.1);
        }
        .ubc-info-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2px;
        }
        .ubc-info-label { font-size: 10px; color: rgba(255,255,255,0.5); }
        .ubc-info-value { font-size: 13px; color: #fff; }
        .ubc-footer {
          text-align: center;
          font-size: 10px;
          color: rgba(255,255,255,0.4);
          margin-top: 8px;
        }
      `;
      document.head.appendChild(style);
    }

    set hass(hass) {
      this._hass = hass;
      this._update();
    }

    _getCardPrefix() {
      // 从 entity 提取卡片前缀，如 sensor.wenzhou_water_账户余额 -> wenzhou_water
      const entity = this._config.entity;
      const match = entity.match(/^sensor\.([^_]+_[^_]+)_/);
      return match ? match[1] : '';
    }

    _getEntity(entityId) {
      return this._hass?.states[entityId];
    }

    _getState(state) {
      return state ? state.state : 'unknown';
    }

    _formatNumber(val, decimals = 1) {
      const n = parseFloat(val);
      return isNaN(n) ? '--' : n.toFixed(decimals);
    }

    _update() {
      if (!this._hass || !this._cardEl) return;

      const prefix = this._getCardPrefix();
      if (!prefix) return;

      // 根据类型选择对应的实体 ID
      let balance, usage, currentStep, estimated;
      let s1, s2, s3;
      let avg, vsAvg, status, updateTime, lastMonth;
      let threshold1 = 17, threshold2 = 30;

      if (this._type === 'water') {
        // 温州水务实体映射
        balance = this._getEntity(`sensor.${prefix}_账户余额`);
        usage = this._getEntity(`sensor.${prefix}_本期用水量`);
        currentStep = this._getEntity(`sensor.${prefix}_当前阶梯`);
        estimated = this._getEntity(`sensor.${prefix}_预估本月账单`);
        s1 = this._getEntity(`sensor.${prefix}_本期一阶用水量`);
        s2 = this._getEntity(`sensor.${prefix}_本期二阶用水量`);
        s3 = this._getEntity(`sensor.${prefix}_本期三阶用水量`);
        avg = this._getEntity(`sensor.${prefix}_历史月均用水`);
        vsAvg = this._getEntity(`sensor.${prefix}_与均值对比`);
        status = this._getEntity(`sensor.${prefix}_集成状态`);
        updateTime = this._getEntity(`sensor.${prefix}_最后更新时间`);
        lastMonth = this._getEntity(`sensor.${prefix}_上期用水量`);
        threshold1 = 17;
        threshold2 = 30;
      } else {
        // 华润燃气实体映射
        balance = this._getEntity(`sensor.${prefix}_account_balance`);
        usage = this._getEntity(`sensor.${prefix}_this_gas_used`);
        currentStep = this._getEntity(`sensor.${prefix}_current_step`);
        estimated = this._getEntity(`sensor.${prefix}_estimated_gas_bill_amount`);
        s1 = this._getEntity(`sensor.${prefix}_step1_gas_used`);
        s2 = this._getEntity(`sensor.${prefix}_step2_gas_used`);
        s3 = this._getEntity(`sensor.${prefix}_step3_gas_used`);
        avg = this._getEntity(`sensor.${prefix}_year_avg_gas`);
        vsAvg = this._getEntity(`sensor.${prefix}_usage_vs_avg`);
        status = this._getEntity(`sensor.${prefix}_integration_status`);
        updateTime = this._getEntity(`sensor.${prefix}_last_update_time`);
        lastMonth = this._getEntity(`sensor.${prefix}_last_month_gas`);
        threshold1 = 5;
        threshold2 = 10;
      }

      // 更新数值
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };

      setVal(`${this._cardId}-balance`, '¥' + this._formatNumber(balance?.state));
      setVal(`${this._cardId}-usage`, this._formatNumber(usage?.state));
      setVal(`${this._cardId}-step`, currentStep?.state || '--');
      setVal(`${this._cardId}-estimated`, '¥' + this._formatNumber(estimated?.state));
      setVal(`${this._cardId}-s1`, this._formatNumber(s1?.state, 2));
      setVal(`${this._cardId}-s2`, this._formatNumber(s2?.state, 2));
      setVal(`${this._cardId}-s3`, this._formatNumber(s3?.state, 2));
      setVal(`${this._cardId}-avg`, this._formatNumber(avg?.state) + 'm³');
      
      // 对比均值显示带 %
      const vsAvgVal = vsAvg?.state;
      if (vsAvgVal && vsAvgVal !== '--') {
        const n = parseFloat(vsAvgVal);
        const sign = n >= 0 ? '+' : '';
        setVal(`${this._cardId}-vs-avg`, sign + this._formatNumber(vsAvgVal) + '%');
      } else {
        setVal(`${this._cardId}-vs-avg`, vsAvgVal || '--');
      }
      
      setVal(`${this._cardId}-last-month`, this._formatNumber(lastMonth?.state) + 'm³');
      setVal(`${this._cardId}-update`, '更新: ' + (updateTime?.state || '--'));

      // 状态指示灯
      const dot = document.getElementById(`${this._cardId}-dot`);
      const st = status?.state || 'normal';
      dot.className = 'ubc-status-dot';
      if (st !== 'normal' && st !== 'unknown') {
        dot.classList.add(st.includes('error') || st.includes('expired') ? 'error' : 'warning');
      }

      // 阶梯进度条
      const totalUsage = parseFloat(usage?.state) || 0;
      const step1Val = parseFloat(s1?.state) || 0;
      const step2Val = parseFloat(s2?.state) || 0;
      const step3Val = parseFloat(s3?.state) || 0;

      let percent = 0;
      if (totalUsage <= threshold1) {
        percent = (totalUsage / threshold1) * 33;
      } else if (totalUsage <= threshold2) {
        percent = 33 + ((totalUsage - threshold1) / (threshold2 - threshold1)) * 33;
      } else {
        percent = 66 + Math.min(((totalUsage - threshold2) / threshold2) * 34, 34);
      }

      const fill = document.getElementById(`${this._cardId}-progress-fill`);
      if (fill) fill.style.width = Math.min(percent, 100) + '%';

      setVal(`${this._cardId}-progress-text`, this._formatNumber(totalUsage, 2) + 'm³');
    }
  }

  customElements.define('utility-bill-card', UtilityBillCard);
})();
