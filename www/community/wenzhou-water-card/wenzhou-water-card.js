/**
 * 温州水务 Lovelace 自定义卡片 - v1.4.0
 * 用法示例:
 *   type: custom:wenzhou-water-card
 *   entity: sensor.wenzhou_water_xxx_account_balance
 *   title: 温州水务
 */
(function () {
  'use strict';

  const CARD_VERSION = '1.4.0';

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
          <div class="wwc-card wwc-card-usage" id="${this._cardId}-usage">
            <div class="wwc-card-label">本期用水</div>
            <div class="wwc-card-value wwc-value-usage">--</div>
            <div class="wwc-card-unit">m³</div>
          </div>
          <div class="wwc-card wwc-card-bill" id="${this._cardId}-bill">
            <div class="wwc-card-label">账单金额</div>
            <div class="wwc-card-value wwc-value-bill">--</div>
            <div class="wwc-card-unit">¥</div>
          </div>
          <div class="wwc-card wwc-card-estimate" id="${this._cardId}-estimate">
            <div class="wwc-card-label">预估月用</div>
            <div class="wwc-card-value wwc-value-estimate">--</div>
            <div class="wwc-card-unit">m³</div>
          </div>
        </div>
        <div class="wwc-secondary-row">
          <div class="wwc-info-item" id="${this._cardId}-warning">
            <span class="wwc-info-icon">✅</span>
            <span class="wwc-info-text">正常</span>
          </div>
          <div class="wwc-info-item" id="${this._cardId}-compare">
            <span class="wwc-info-icon">📊</span>
            <span class="wwc-info-text">--</span>
          </div>
          <div class="wwc-info-item" id="${this._cardId}-due">
            <span class="wwc-info-icon">📅</span>
            <span class="wwc-info-text">--</span>
          </div>
        </div>
        <div class="wwc-footer">
          <span class="wwc-footer-text">更新于 <span id="${this._cardId}-time">--</span></span>
        </div>
      `;

      const style = document.createElement('style');
      style.textContent = `
        .wwc-container {
          background: linear-gradient(135deg, #1a2a4a 0%, #0d47a1 50%, #1565c0 100%);
          border-radius: 16px;
          padding: 16px;
          color: #fff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 20px rgba(13, 71, 161, 0.4);
          transition: transform 0.2s, box-shadow 0.2s;
          cursor: default;
          user-select: none;
        }
        .wwc-container:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 28px rgba(13, 71, 161, 0.6);
        }
        .wwc-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 14px;
        }
        .wwc-title { display: flex; align-items: center; gap: 8px; }
        .wwc-icon { font-size: 20px; }
        .wwc-title-text { font-size: 15px; font-weight: 600; letter-spacing: 0.5px; }
        .wwc-status-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: #4caf50;
          box-shadow: 0 0 6px #4caf50;
          transition: background 0.3s;
        }
        .wwc-status-dot.error { background: #f44336; box-shadow: 0 0 6px #f44336; }
        .wwc-status-dot.warn { background: #ff9800; box-shadow: 0 0 6px #ff9800; }
        .wwc-grid {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr 1fr;
          gap: 10px;
          margin-bottom: 12px;
        }
        .wwc-card {
          background: rgba(255,255,255,0.12);
          border-radius: 12px;
          padding: 12px 8px 10px;
          text-align: center;
          backdrop-filter: blur(4px);
          border: 1px solid rgba(255,255,255,0.08);
          transition: background 0.2s, transform 0.2s;
          cursor: default;
        }
        .wwc-card:hover {
          background: rgba(255,255,255,0.2);
          transform: scale(1.03);
        }
        .wwc-card-label {
          font-size: 10px;
          color: rgba(255,255,255,0.7);
          margin-bottom: 4px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .wwc-card-value {
          font-size: 18px;
          font-weight: 700;
          color: #fff;
          line-height: 1.2;
          font-variant-numeric: tabular-nums;
        }
        .wwc-card-unit {
          font-size: 10px;
          color: rgba(255,255,255,0.5);
          margin-top: 2px;
        }
        .wwc-value-balance { color: #4fc3f7; }
        .wwc-value-bill { color: #ffb74d; }
        .wwc-value-usage { color: #81d4fa; }
        .wwc-value-estimate { color: #a5d6a7; }
        .wwc-secondary-row {
          display: flex;
          gap: 8px;
          margin-bottom: 10px;
        }
        .wwc-info-item {
          flex: 1;
          background: rgba(255,255,255,0.08);
          border-radius: 8px;
          padding: 6px 8px;
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 11px;
          color: rgba(255,255,255,0.8);
          border: 1px solid rgba(255,255,255,0.05);
        }
        .wwc-info-icon { font-size: 12px; }
        .wwc-info-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .wwc-info-item.warning { background: rgba(244,67,54,0.2); border-color: rgba(244,67,54,0.3); color: #ff8a80; }
        .wwc-info-item.warn { background: rgba(255,152,0,0.2); border-color: rgba(255,152,0,0.3); color: #ffd180; }
        .wwc-footer {
          text-align: right;
          font-size: 10px;
          color: rgba(255,255,255,0.35);
        }
        @media (max-width: 400px) {
          .wwc-grid { grid-template-columns: 1fr 1fr; }
        }
      `;

      this._styleEl = style;
      this._cardEl = card;
      this.appendChild(style);
      this.appendChild(card);
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._cardEl) return;
      this._update();
    }

    _update() {
      const entityId = this._config.entity;
      const state = this._hass?.states?.[entityId];
      if (!state) return;

      const cid = this._getCardId(state.entity_id);
      const sid = (id) => `${this._cardId}-${id}`;

      // 账户余额
      const balanceEl = document.getElementById(sid('balance'));
      const balance = state.attributes?.account_balance ?? state.state;
      if (balanceEl) {
        const valEl = balanceEl.querySelector('.wwc-card-value');
        if (valEl) valEl.textContent = typeof balance === 'number' ? balance.toFixed(2) : (balance ?? '--');
      }

      // 集成状态
      const dotEl = document.getElementById(sid('dot'));
      const status = state.attributes?.integration_status ?? 'unknown';
      if (dotEl) {
        dotEl.className = 'wwc-status-dot' + (status === 'normal' ? '' : status === 'token_expired' || status === 'api_error' ? ' error' : status === 'network_error' ? ' warn' : '');
      }

      // 本期用水
      const usageEl = document.getElementById(sid('usage'));
      if (usageEl) {
        const valEl = usageEl.querySelector('.wwc-card-value');
        if (valEl) {
          const usage = state.attributes?.water_used ?? '--';
          valEl.textContent = typeof usage === 'number' ? usage.toFixed(1) : usage;
        }
      }

      // 账单金额
      const billEl = document.getElementById(sid('bill'));
      if (billEl) {
        const valEl = billEl.querySelector('.wwc-card-value');
        if (valEl) {
          const bill = state.attributes?.bill_amount ?? '--';
          valEl.textContent = typeof bill === 'number' ? bill.toFixed(2) : bill;
        }
      }

      // 预估月用水
      const estEl = document.getElementById(sid('estimate'));
      if (estEl) {
        const valEl = estEl.querySelector('.wwc-card-value');
        if (valEl) {
          const est = state.attributes?.estimated_monthly_usage;
          valEl.textContent = est != null ? (+est).toFixed(1) : '--';
        }
      }

      // 账户预警
      const warnEl = document.getElementById(sid('warning'));
      if (warnEl) {
        const warn = state.attributes?.account_warning ?? '正常';
        const textEl = warnEl.querySelector('.wwc-info-text');
        const icoEl = warnEl.querySelector('.wwc-info-icon');
        if (textEl) textEl.textContent = warn;
        if (icoEl) {
          if (warn.includes('0') && !warn.includes('¥')) { icoEl.textContent = '🚨'; }
          else if (warn.includes('不足')) { icoEl.textContent = '⚠️'; }
          else if (warn.includes('偏低')) { icoEl.textContent = '💡'; }
          else { icoEl.textContent = '✅'; }
        }
        warnEl.className = 'wwc-info-item' + (warn.includes('0') && !warn.includes('¥') ? ' warning' : warn.includes('不足') || warn.includes('偏低') ? ' warn' : '');
      }

      // 与均值对比
      const cmpEl = document.getElementById(sid('compare'));
      if (cmpEl) {
        const vsAvg = state.attributes?.usage_vs_avg;
        const avgEl = cmpEl.querySelector('.wwc-info-text');
        const icoEl = cmpEl.querySelector('.wwc-info-icon');
        if (avgEl) {
          if (vsAvg != null) {
            const sign = vsAvg > 0 ? '+' : '';
            avgEl.textContent = `${sign}${vsAvg}%`;
            avgEl.style.color = vsAvg > 0 ? '#ff8a80' : vsAvg < 0 ? '#a5d6a7' : '';
          } else {
            avgEl.textContent = '--';
          }
        }
        if (icoEl) {
          icoEl.textContent = vsAvg > 0 ? '📈' : vsAvg < 0 ? '📉' : '📊';
        }
      }

      // 截止日期
      const dueEl = document.getElementById(sid('due'));
      if (dueEl) {
        const due = state.attributes?.due_date;
        const textEl = dueEl.querySelector('.wwc-info-text');
        if (textEl && due) textEl.textContent = due === '未知' ? '--' : due;
      }

      // 更新时间
      const timeEl = document.getElementById(sid('time'));
      if (timeEl) {
        const lastChanged = state.last_changed;
        if (lastChanged) {
          const d = new Date(lastChanged);
          const hh = String(d.getHours()).padStart(2, '0');
          const mm = String(d.getMinutes()).padStart(2, '0');
          timeEl.textContent = `${hh}:${mm}`;
        }
      }
    }

    _getCardId(entityId) {
      // 从 entity_id 提取 card_id
      const match = entityId.match(/sensor\.wenzhou_water_([^_]+)/);
      return match ? match[1] : entityId;
    }

    getCardSize() {
      return 3;
    }
  }

  // 注册自定义卡片
  if (!customElements.get('wenzhou-water-card')) {
    customElements.define('wenzhou-water-card', WenzhouWaterCard);
    console.info(`%c 温州水务卡片 v${CARD_VERSION} 已加载 `, 'background:#1565c0;color:#fff;padding:2px 6px;border-radius:4px');
  }
})();
