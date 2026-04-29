/**
 * 温州水务 Lovelace 自定义卡片 - v1.0.0
 * 新增 v1.0.0:
 *   - 水务数据综合展示
 *   - 阶梯用水量进度条可视化
 *   - 账户余额与预警
 *   - 历史月均用水对比
 *   - 缴费截止日期提醒
 * 用法示例:
 *   type: custom:wenzhou-water-card
 *   entity: sensor.wenzhou_water_账户余额
 *   title: 温州水务
 */
(function () {
  'use strict';

  const CARD_VERSION = '1.0.0';

  class WenzhouWaterCard extends HTMLElement {
    setConfig(config) {
      if (!config.entity) {
        throw new Error('请指定 entity 参数');
      }
      this._config = {
        title: config.title || '温州水务',
        entity: config.entity,
        ...config,
      };
      this._hass = null;
      this._cardId = 'wenzhou-water-' + Math.random().toString(36).substr(2, 9);

      if (this._cardEl) return;
      const card = document.createElement('div');
      card.id = this._cardId;
      card.className = 'wwc-container';
      card.innerHTML = `
        <div class="wwc-header">
          <div class="wwc-title">
            <span class="wwc-icon">💧</span>
            <span class="wwc-title-text">${this._config.title}</span>
          </div>
          <div class="wwc-status-dot" id="${this._cardId}-dot"></div>
        </div>
        <div class="wwc-grid">
          <div class="wwc-card wwc-card-balance" id="${this._cardId}-balance">
            <div class="wwc-card-label">账户余额</div>
            <div class="wwc-card-value wwc-value-balance">--</div>
            <div class="wwc-card-unit">¥</div>
          </div>
          <div class="wwc-card wwc-card-water" id="${this._cardId}-water">
            <div class="wwc-card-label">本期用水</div>
            <div class="wwc-card-value wwc-value-water">--</div>
            <div class="wwc-card-unit">m³</div>
          </div>
          <div class="wwc-card wwc-card-step" id="${this._cardId}-step">
            <div class="wwc-card-label">当前阶梯</div>
            <div class="wwc-card-value wwc-value-step">--</div>
          </div>
          <div class="wwc-card wwc-card-estimated" id="${this._cardId}-estimated">
            <div class="wwc-card-label">预估账单</div>
            <div class="wwc-card-value wwc-value-estimated">--</div>
            <div class="wwc-card-unit">¥</div>
          </div>
        </div>
        <div class="wwc-progress-section" id="${this._cardId}-progress">
          <div class="wwc-progress-label">
            <span>阶梯用水进度</span>
            <span id="${this._cardId}-progress-text">--</span>
          </div>
          <div class="wwc-progress-bar">
            <div class="wwc-progress-fill" id="${this._cardId}-progress-fill"></div>
          </div>
          <div class="wwc-step-info" id="${this._cardId}-step-info">
            <div class="wwc-step-item">
              <span class="wwc-step-num">一阶</span>
              <span class="wwc-step-val" id="${this._cardId}-s1">--</span>
            </div>
            <div class="wwc-step-item">
              <span class="wwc-step-num">二阶</span>
              <span class="wwc-step-val" id="${this._cardId}-s2">--</span>
            </div>
            <div class="wwc-step-item">
              <span class="wwc-step-num">三阶</span>
              <span class="wwc-step-val" id="${this._cardId}-s3">--</span>
            </div>
          </div>
        </div>
        <div class="wwc-info-row">
          <div class="wwc-info-item">
            <span class="wwc-info-label">历史月均</span>
            <span class="wwc-info-value" id="${this._cardId}-avg">--</span>
          </div>
          <div class="wwc-info-item">
            <span class="wwc-info-label">与均值对比</span>
            <span class="wwc-info-value" id="${this._cardId}-vs-avg">--</span>
          </div>
          <div class="wwc-info-item">
            <span class="wwc-info-label">距截止</span>
            <span class="wwc-info-value" id="${this._cardId}-due">--</span>
          </div>
        </div>
        <div class="wwc-warning-row" id="${this._cardId}-warning-row">
          <span class="wwc-warning-icon" id="${this._cardId}-warning-icon">ℹ️</span>
          <span class="wwc-warning-text" id="${this._cardId}-warning">--</span>
        </div>
        <div class="wwc-footer">
          <span id="${this._cardId}-update">--</span>
        </div>
      `;
      this.appendChild(card);
      this._cardEl = card;
      this._injectStyles();
    }

    _injectStyles() {
      if (document.getElementById('wenzhou-water-card-styles')) return;
      const style = document.createElement('style');
      style.id = 'wenzhou-water-card-styles';
      style.textContent = `
        .wwc-container {
          background: linear-gradient(135deg, #0f4c75 0%, #1b262c 100%);
          border-radius: 16px;
          padding: 16px;
          color: #fff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 20px rgba(0,0,0,0.3);
          transition: all 0.3s ease;
          height: 100%;
          box-sizing: border-box;
        }
        .wwc-container:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 25px rgba(0,0,0,0.4);
        }
        .wwc-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .wwc-title { display: flex; align-items: center; gap: 8px; }
        .wwc-icon { font-size: 24px; }
        .wwc-title-text { font-size: 16px; font-weight: 600; }
        .wwc-status-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: #4ade80;
          box-shadow: 0 0 8px #4ade80;
        }
        .wwc-status-dot.warning { background: #fbbf24; box-shadow: 0 0 8px #fbbf24; }
        .wwc-status-dot.error { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
        .wwc-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }
        .wwc-card {
          background: rgba(255,255,255,0.1);
          border-radius: 12px;
          padding: 12px;
          text-align: center;
          transition: all 0.3s ease;
        }
        .wwc-card:hover { background: rgba(255,255,255,0.15); }
        .wwc-card-label { font-size: 11px; color: rgba(255,255,255,0.7); margin-bottom: 4px; }
        .wwc-card-value { font-size: 20px; font-weight: 700; }
        .wwc-card-unit { font-size: 11px; color: rgba(255,255,255,0.5); }
        .wwc-value-balance { color: #4ade80; }
        .wwc-value-water { color: #38bdf8; }
        .wwc-value-step { color: #a78bfa; }
        .wwc-value-estimated { color: #fbbf24; }
        .wwc-progress-section {
          background: rgba(255,255,255,0.05);
          border-radius: 12px;
          padding: 12px;
          margin-bottom: 12px;
        }
        .wwc-progress-label {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
          color: rgba(255,255,255,0.7);
          margin-bottom: 8px;
        }
        .wwc-progress-bar {
          height: 8px;
          background: rgba(255,255,255,0.1);
          border-radius: 4px;
          overflow: hidden;
          margin-bottom: 8px;
        }
        .wwc-progress-fill {
          height: 100%;
          border-radius: 4px;
          background: linear-gradient(90deg, #3b82f6, #06b6d4, #ef4444);
          transition: width 0.5s ease;
        }
        .wwc-step-info {
          display: flex;
          justify-content: space-around;
          font-size: 12px;
        }
        .wwc-step-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2px;
        }
        .wwc-step-num { color: rgba(255,255,255,0.5); font-size: 10px; }
        .wwc-step-val { color: #fff; font-weight: 600; }
        .wwc-info-row {
          display: flex;
          justify-content: space-between;
          padding: 8px 0;
          border-top: 1px solid rgba(255,255,255,0.1);
        }
        .wwc-info-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2px;
        }
        .wwc-info-label { font-size: 10px; color: rgba(255,255,255,0.5); }
        .wwc-info-value { font-size: 13px; color: #fff; }
        .wwc-warning-row {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 10px;
          background: rgba(255,255,255,0.05);
          border-radius: 8px;
          margin-bottom: 8px;
        }
        .wwc-warning-icon { font-size: 14px; }
        .wwc-warning-text { font-size: 12px; color: rgba(255,255,255,0.8); }
        .wwc-warning-row.alert { background: rgba(239,68,68,0.2); }
        .wwc-warning-row.alert .wwc-warning-text { color: #fca5a5; }
        .wwc-warning-row.warning { background: rgba(251,191,36,0.2); }
        .wwc-warning-row.warning .wwc-warning-text { color: #fcd34d; }
        .wwc-footer {
          text-align: center;
          font-size: 10px;
          color: rgba(255,255,255,0.4);
          margin-top: 4px;
        }
      `;
      document.head.appendChild(style);
    }

    set hass(hass) {
      this._hass = hass;
      this._update();
    }

    _getEntity(entityId) {
      return this._hass?.states[entityId];
    }

    _getCardPrefix() {
      // 从 entity 中提取 card_id 前缀
      // 例如: sensor.wenzhou_water_aaa_123_account_balance -> sensor.wenzhou_water_aaa_123_
      const entity = this._config.entity;
      if (!entity) return 'sensor.wenzhou_water_';
      const match = entity.match(/^(sensor\.[^_]+_[^_]+_)/);
      return match ? match[1] : 'sensor.wenzhou_water_';
    }

    _formatNumber(val, decimals = 1) {
      const n = parseFloat(val);
      return isNaN(n) ? '--' : n.toFixed(decimals);
    }

    _update() {
      if (!this._hass || !this._cardEl) return;

      const prefix = this._getCardPrefix();

      // 获取实体数据
      const balance = this._getEntity(prefix + 'account_balance');
      const waterUsed = this._getEntity(prefix + 'water_used');
      const currentStep = this._getEntity(prefix + 'current_step');
      const estimated = this._getEntity(prefix + 'estimated_bill_amount');
      const s1 = this._getEntity(prefix + 'step1_usage');
      const s2 = this._getEntity(prefix + 'step2_usage');
      const s3 = this._getEntity(prefix + 'step3_usage');
      const avg = this._getEntity(prefix + 'history_avg_usage');
      const vsAvg = this._getEntity(prefix + 'usage_vs_avg');
      const status = this._getEntity(prefix + 'integration_status');
      const updateTime = this._getEntity(prefix + 'last_update_time');
      const daysUntilDue = this._getEntity(prefix + 'days_until_due');
      const warning = this._getEntity(prefix + 'account_warning');
      const levelMax = this._getEntity(prefix + 'level_max');

      // 更新数值
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };

      setVal(`${this._cardId}-balance`, '¥' + this._formatNumber(balance?.state));
      setVal(`${this._cardId}-water`, this._formatNumber(waterUsed?.state));
      setVal(`${this._cardId}-step`, currentStep?.state || '--');
      setVal(`${this._cardId}-estimated`, '¥' + this._formatNumber(estimated?.state));
      setVal(`${this._cardId}-s1`, this._formatNumber(s1?.state, 2));
      setVal(`${this._cardId}-s2`, this._formatNumber(s2?.state, 2));
      setVal(`${this._cardId}-s3`, this._formatNumber(s3?.state, 2));
      setVal(`${this._cardId}-avg`, this._formatNumber(avg?.state) + 'm³');

      // 与均值对比显示
      const vsVal = vsAvg?.state;
      if (vsVal !== undefined && vsVal !== '--') {
        const n = parseFloat(vsVal);
        if (!isNaN(n)) {
          setVal(`${this._cardId}-vs-avg`, (n >= 0 ? '+' : '') + n.toFixed(1) + '%');
        } else {
          setVal(`${this._cardId}-vs-avg`, '--');
        }
      } else {
        setVal(`${this._cardId}-vs-avg`, '--');
      }

      // 距截止日期
      const dueVal = daysUntilDue?.state;
      if (dueVal !== undefined && dueVal !== '--') {
        const n = parseInt(dueVal);
        if (!isNaN(n)) {
          if (n < 0) {
            setVal(`${this._cardId}-due`, `逾期${Math.abs(n)}天`);
          } else if (n === 0) {
            setVal(`${this._cardId}-due`, '今天截止');
          } else {
            setVal(`${this._cardId}-due`, `${n}天`);
          }
        } else {
          setVal(`${this._cardId}-due`, '--');
        }
      } else {
        setVal(`${this._cardId}-due`, '--');
      }

      setVal(`${this._cardId}-update`, '更新: ' + (updateTime?.state || '--'));

      // 预警信息
      const warningRow = document.getElementById(`${this._cardId}-warning-row`);
      const warningText = warning?.state || '正常';
      const warningIcon = document.getElementById(`${this._cardId}-warning-icon`);
      setVal(`${this._cardId}-warning`, warningText);

      warningRow.className = 'wwc-warning-row';
      if (warningText.includes('0') || warningText.includes('不足')) {
        warningRow.classList.add('alert');
        warningIcon.textContent = '🚨';
      } else if (warningText.includes('偏低')) {
        warningRow.classList.add('warning');
        warningIcon.textContent = '⚠️';
      } else {
        warningIcon.textContent = 'ℹ️';
      }

      // 状态指示灯
      const dot = document.getElementById(`${this._cardId}-dot`);
      const st = status?.state || 'normal';
      dot.className = 'wwc-status-dot';
      if (st !== 'normal') {
        dot.classList.add(st.includes('error') || st.includes('expired') ? 'error' : 'warning');
      }

      // 阶梯进度条
      const totalWater = parseFloat(waterUsed?.state) || 0;
      const step1Val = parseFloat(s1?.state) || 0;
      const step2Val = parseFloat(s2?.state) || 0;
      const step3Val = parseFloat(s3?.state) || 0;
      const threshold1 = parseFloat(levelMax?.state) || 240; // 默认一阶上限

      let percent = 0;
      if (totalWater <= threshold1) {
        percent = (totalWater / threshold1) * 33;
      } else {
        // 假设二阶上限为一阶的1.75倍
        const threshold2 = threshold1 * 1.75;
        if (totalWater <= threshold2) {
          percent = 33 + ((totalWater - threshold1) / (threshold2 - threshold1)) * 33;
        } else {
          percent = 66 + Math.min(((totalWater - threshold2) / threshold2) * 34, 34);
        }
      }

      const fill = document.getElementById(`${this._cardId}-progress-fill`);
      if (fill) fill.style.width = Math.min(percent, 100) + '%';

      setVal(`${this._cardId}-progress-text`, this._formatNumber(totalWater, 2) + '/' +
        this._formatNumber(threshold1, 0) + 'm³');
    }
  }

  customElements.define('wenzhou-water-card', WenzhouWaterCard);
})();
