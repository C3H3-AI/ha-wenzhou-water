/**
 * water-statistics-card v1.2 — 温州水务用水对比统计卡片
 * 风格完全同 crcgas-statistics-card v4.0
 * - 配置时选择账户（倪合/倪周）
 * - 双年对比折线/柱状图
 * - 用水量/费用切换
 * - 阶梯用水进度条
 * - 通过 friendly_name 动态查找实体（不硬编码 entity_id）
 *
 * 使用方式:
 *   type: 'custom:water-statistics-card'
 *   account: 'ni_he'   # 必选: ni_he / ni_zhou
 *   title: '💧 用水统计'
 */

function _niceStep(maxV) {
  if (maxV < 5) return 1;
  if (maxV < 20) return 5;
  if (maxV < 50) return 10;
  if (maxV < 100) return 20;
  if (maxV < 200) return 50;
  if (maxV < 500) return 100;
  if (maxV < 1000) return 200;
  return Math.round(maxV / 20 / 100) * 100;
}

/** SVG 悬浮提示 */
function _makeTipSVG(month, d1, d2, y1, y2, rate, PL, SX, H, W, pos) {
  const sd1 = d1[month], sd2 = d2[month];
  if (!sd1 && !sd2) return '';
  const g1 = sd1 ? Math.max(0, sd1.change).toFixed(1) : '0.0';
  const g2 = sd2 ? Math.max(0, sd2.change).toFixed(1) : '0.0';
  const c1 = sd1 ? '¥' + (Math.max(0, sd1.change) * rate).toFixed(0) : '¥0';
  const c2 = sd2 ? '¥' + (Math.max(0, sd2.change) * rate).toFixed(0) : '¥0';
  const TW = 100, TH = 44;
  let tx = pos ? Math.max(2, Math.min(W - TW - 2, pos.x - TW / 2)) : 2;
  let ty = pos ? Math.max(2, Math.min(H - TH - 2, pos.y - TH - 8)) : 2;
  if (ty < 2) ty = pos ? Math.min(H - TH - 2, pos.y + 10) : 2;
  return `<g style="pointer-events:none;opacity:0.88">
<rect x="${tx}" y="${ty}" width="${TW}" height="${TH}" rx="4" fill="var(--card-background-color)" stroke="var(--divider-color)" stroke-width="0.5"/>
<text x="${tx+6}" y="${ty+13}" fill="var(--primary-text-color)" font-size="10" font-weight="600">${month+1}月</text>
<text x="${tx+6}" y="${ty+26}" fill="#2196f3" font-size="9">● 本年 ${g1}m³ ${c1}</text>
<text x="${tx+6}" y="${ty+38}" fill="#7c4dff" font-size="9">● 去年 ${g2}m³ ${c2}</text>
</g>`;
}

/** 通过 friendly_name 查找实体的辅助函数 */
function _findEntities(states, cardNameKey, sensorKeywords) {
  // 1. 找出所有 belonging to 该设备（通过 cardNameKey 匹配 friendly_name）
  const deviceEntities = {};
  for (const [eid, stateObj] of Object.entries(states)) {
    const fn = stateObj.attributes?.friendly_name || '';
    if (fn.includes(cardNameKey)) {
      // 按 friendly_name 去掉前缀后的小写 key 存储
      const cleanName = fn.replace(`温州水务 - ${cardNameKey} `, '').trim();
      deviceEntities[cleanName] = eid;
    }
  }

  // 2. 按 sensorKeywords 查找
  const result = {};
  for (const [field, keyword] of Object.entries(sensorKeywords)) {
    // 精确匹配
    if (deviceEntities[keyword]) {
      result[field] = deviceEntities[keyword];
      continue;
    }
    // 模糊匹配（包含 keyword）
    for (const [name, eid] of Object.entries(deviceEntities)) {
      if (name.includes(keyword)) {
        result[field] = eid;
        break;
      }
    }
  }
  return result;
}

/** 账户定义（只含 cardNameKey 用于 friendly_name 匹配） */
const ACCOUNTS = {
  ni_he: {
    label: '倪*禾',
    cardNameKey: '倪*禾',
  },
  ni_zhou: {
    label: '倪*州',
    cardNameKey: '倪*州',
  },
};

class WaterStatisticsCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement('water-statistics-editor');
  }

  static getStubConfig() {
    return { title: '💧 用水统计', account: '' };
  }

  setConfig(config) {
    if (!config) throw new Error('Invalid configuration');
    const account = config.account || '';

    this._config = {
      title: config.title || '💧 用水统计',
      historyEntity: config.history_entity || null,
      account: account,
    };
    this._resetState();
    this._render();
    if (this._hass && this._selectedAccount) this._loadData();
  }

  _resetState() {
    this._yearData = {};
    this._loaded = false;
    this._year = new Date().getFullYear();
    this._viewMode = 'gas';
    this._chartType = 'line';
    this._cardId = 'water-v1-' + Math.random().toString(36).substr(2, 9);
    this._selectedAccount = this._config?.account || null;
    this._liveData = {
      balance: null, usage: null, bill: null, period: null, status: null,
      step1Used: null, step2Used: null, step1Yiyong: null, step1Shangxian: null,
      stepRemain: null, step1Price: null, currentStep: null,
    };
    this._loading = false;
    this._selectedMonth = null;
    this._hoverMonth = null;
    this._hoverPos = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded && this._selectedAccount) this._loadData();
    else if (this._selectedAccount) this._loadCurrentState();
  }

  connectedCallback() {
    if (this._hass && !this._loaded && this._selectedAccount) this._loadData();
    if (!this._boundClick) {
      this._boundClick = (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const action = btn.dataset.action;
        if (action === 'sw') { this._viewMode = btn.dataset.mode; this._selectedMonth = null; this._render(); }
        else if (action === 'ct') { this._chartType = btn.dataset.ct; this._selectedMonth = null; this._render(); }
        else if (action === 'cy') this._cy(Number(btn.dataset.dir));
        else if (action === 'month') {
          this._selectedMonth = { year: Number(btn.dataset.year), month: Number(btn.dataset.month) };
          this._render();
        }
      };
      this.addEventListener('click', this._boundClick);

      this._boundHover = (e) => {
        const btn = e.target.closest('[data-action="month"]');
        if (btn && e.type === 'mouseover') {
          const m = Number(btn.dataset.month);
          if (!this._hoverMonth || this._hoverMonth.month !== m) {
            this._hoverMonth = { year: Number(btn.dataset.year), month: m };
            if (!this._hoverRaf) {
              this._hoverRaf = requestAnimationFrame(() => { this._hoverRaf = null; this._render(); });
            }
          }
        } else if (!btn && e.type === 'mouseout') {
          const chartEl = e.currentTarget.querySelector('.ca svg');
          if (chartEl && !chartEl.contains(e.relatedTarget)) {
            this._hoverMonth = null; this._selectedMonth = null;
            if (!this._hoverRaf) {
              this._hoverRaf = requestAnimationFrame(() => { this._hoverRaf = null; this._render(); });
            }
          }
        }
      };
      this.addEventListener('mouseover', this._boundHover);
      this.addEventListener('mouseout', this._boundHover);
    }
    if (!this._boundMove) {
      this._boundMove = (e) => {
        const svg = e.target.closest('svg');
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        this._hoverPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      };
      this.addEventListener('mousemove', this._boundMove);
    }
  }

  disconnectedCallback() {
    if (this._boundClick) { this.removeEventListener('click', this._boundClick); this._boundClick = null; }
    if (this._boundHover) { this.removeEventListener('mouseover', this._boundHover); this.removeEventListener('mouseout', this._boundHover); this._boundHover = null; }
    if (this._boundMove) { this.removeEventListener('mousemove', this._boundMove); this._boundMove = null; }
  }

  /** 通过 friendly_name 查找该账户的传感器实体 ID */
  _findEntitiesForAccount() {
    if (!this._hass || !this._hass.states || !this._selectedAccount) return {};
    const acct = ACCOUNTS[this._selectedAccount];
    if (!acct) return {};

    const sensorMap = {
      balance: '账户余额',
      usage: '本期用水量',
      bill: '账单金额',
      period: '本期抄表日期',
      status: '集成状态',
      step1Used: '本期一阶用水量',
      step2Used: '本期二阶用水量',
      step1Yiyong: '本年累计一阶用水量',
      step1Shangxian: '一阶上限',
      stepRemain: '阶梯剩余量',
      step1Price: '一阶水价',
      step2Price: '二阶水价',
      currentStep: '当前阶梯',
      estUsage: '预估月用水量',
      estBill: '预估本月账单',
      histAvg: '历史月均用水',
    };

    return _findEntities(this._hass.states, acct.cardNameKey, sensorMap);
  }

  /** 查找历史统计实体（水表历史累计） */
  _findHistEntity() {
    if (this._config.historyEntity) return this._config.historyEntity;
    if (!this._hass || !this._hass.states || !this._selectedAccount) return null;
    const acct = ACCOUNTS[this._selectedAccount];
    if (!acct) return null;

    // 通过 friendly_name 查找 "水表历史累计"
    for (const [eid, stateObj] of Object.entries(this._hass.states)) {
      const fn = stateObj.attributes?.friendly_name || '';
      if (fn.includes(acct.cardNameKey) && fn.includes('水表历史累计')) {
        return eid;
      }
    }
    return null;
  }

  async _loadData() {
    if (!this._hass || this._loaded || !this._selectedAccount) return;
    this._loaded = true;
    this._loading = true;
    this._render();
    this._loadCurrentState();
    try {
      if (!this._yearData[this._year]) await this._loadYear(this._year);
      if (!this._yearData[this._year - 1]) await this._loadYear(this._year - 1);
    } catch (e) {
      console.error('water: load error', e);
    }
    this._loading = false;
    this._render();
  }

  async _loadYear(year) {
    if (this._yearData[year]) return;
    const start = new Date(year, 0, 1).toISOString();
    const end = new Date(year + 1, 0, 1).toISOString();
    try {
      const statisticId = this._findHistEntity();
      if (!statisticId) { this._yearData[year] = {}; return; }
      const result = await this._hass.callWS({
        type: 'recorder/statistics_during_period',
        start_time: start, end_time: end,
        statistic_ids: [statisticId], period: 'month',
      });
      const stats = result?.[statisticId] || [];
      const byMonth = {};
      for (const s of stats) {
        byMonth[new Date(s.start).getMonth()] = { change: s.change || 0, sum: s.sum || s.state || 0, state: s.state || 0 };
      }
      this._yearData[year] = byMonth;
    } catch (e) {
      this._yearData[year] = {};
    }
  }

  _loadCurrentState() {
    if (!this._hass || !this._selectedAccount) return;
    const entityMap = this._findEntitiesForAccount();
    const states = this._hass.states;
    const _val = (id) => id && states[id] ? Number(states[id].state) || 0 : null;
    const _str = (id) => id && states[id] ? states[id].state : null;

    this._liveData = {
      balance: _val(entityMap.balance),
      usage: _val(entityMap.usage),
      bill: _val(entityMap.bill),
      period: _str(entityMap.period),
      status: _str(entityMap.status),
      step1Used: _val(entityMap.step1Used),
      step2Used: _val(entityMap.step2Used),
      step1Yiyong: _val(entityMap.step1Yiyong),
      step1Shangxian: _val(entityMap.step1Shangxian),
      stepRemain: _val(entityMap.stepRemain),
      step1Price: _val(entityMap.step1Price) || 3.5,
      currentStep: _str(entityMap.currentStep),
      estUsage: _val(entityMap.estUsage),
      estBill: _val(entityMap.estBill),
      histAvg: _val(entityMap.histAvg),
    };
    if (!this._loading) this._render();
  }

  _renderChart(y1, y2, mode, chartType, hoverMonth, hoverPos) {
    const d1 = this._yearData[y1] || {}, d2 = this._yearData[y2] || {};
    const p = this._liveData?.step1Price || 3.5;
    const months = 12;
    const v1 = [], v2 = [];
    for (let m = 0; m < months; m++) {
      let a = d1[m] ? d1[m].change : 0, b = d2[m] ? d2[m].change : 0;
      if (mode === 'cost') { a *= p; b *= p; }
      v1.push(Math.max(0, a));
      v2.push(Math.max(0, b));
    }
    const maxV = Math.max(...v1, ...v2, 1);
    const W = 280, H = 140, PT = 16, PB = 22, PL = 30, PR = 6;
    const CW = W - PL - PR, CH = H - PT - PB;
    const SX = CW / (months > 1 ? months - 1 : 1);
    const BW = months > 1 ? CW / months * 0.22 : 8;
    const C1 = '#2196f3', C2 = '#7c4dff';
    const py = (v) => PT + CH - (v / maxV) * CH * 0.85;
    const step = _niceStep(maxV);
    const mkGrid = () => {
      let g = '';
      for (let i = 0; i < 4; i++) {
        const y = PT + (CH / 3) * i, val = step * (3 - i);
        g += `<line x1="${PL}" y1="${y.toFixed(1)}" x2="${W-PR}" y2="${y.toFixed(1)}" stroke="var(--divider-color)" stroke-width="0.5"/><text x="${PL-4}" y="${y.toFixed(1)+3}" text-anchor="end" fill="var(--secondary-text-color)" font-size="8">${val > 0 ? val : '0'}</text>`;
      }
      return g;
    };
    const mkHC = (h) => h !== null ? `<rect x="${(Math.max(PL, PL + h * SX - SX * 0.45)).toFixed(1)}" y="${PT}" width="${(SX * 0.9).toFixed(1)}" height="${CH.toFixed(1)}" class="crc-hover" rx="4"/>` : '';
    const mkTip = (h) => h !== null ? _makeTipSVG(h, d1, d2, y1, y2, p, PL, SX, H, W, hoverPos) : '';

    if (chartType === 'bar') {
      let bars = '', labels = '';
      for (let i = 0; i < months; i++) {
        const cx = PL + i * SX;
        const h1 = v1[i] > 0 ? (v1[i] / maxV) * CH * 0.85 : 0;
        const h2 = v2[i] > 0 ? (v2[i] / maxV) * CH * 0.85 : 0;
        const yb = H - PB;
        if (h1 > 0) bars += `<rect x="${(cx - BW).toFixed(1)}" y="${(yb - h1).toFixed(1)}" width="${BW.toFixed(1)}" height="${h1.toFixed(1)}" fill="${C1}" opacity="0.85" rx="2" cursor="pointer" data-action="month" data-year="${y1}" data-month="${i}"/><rect x="${(cx - BW).toFixed(1)}" y="${PT}" width="${BW.toFixed(1)}" height="${(CH*0.85).toFixed(1)}" fill="transparent" cursor="pointer" data-action="month" data-year="${y1}" data-month="${i}"/>`;
        if (h2 > 0) bars += `<rect x="${cx.toFixed(1)}" y="${(yb - h2).toFixed(1)}" width="${BW.toFixed(1)}" height="${h2.toFixed(1)}" fill="${C2}" opacity="0.85" rx="2" cursor="pointer" data-action="month" data-year="${y2}" data-month="${i}"/><rect x="${cx.toFixed(1)}" y="${PT}" width="${BW.toFixed(1)}" height="${(CH*0.85).toFixed(1)}" fill="transparent" cursor="pointer" data-action="month" data-year="${y2}" data-month="${i}"/>`;
        if (i % 2 === 0) labels += `<text x="${cx.toFixed(1)}" y="${H-4}" text-anchor="middle" fill="var(--secondary-text-color)" font-size="9">${i+1}月</text>`;
      }
      return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block;"><style>.crc-hover{fill:var(--primary-color);opacity:0.08;pointer-events:none}</style>${mkGrid()}${mkHC(hoverMonth)}${bars}${labels}${mkTip(hoverMonth)}</svg>`;
    }

    const lineSVG = (vals, color, year) => {
      let pts = '', dots = '', area = '';
      for (let i = 0; i < months; i++) {
        const x = PL + i * SX, y = Math.max(PT, Math.min(H - PB, py(vals[i])));
        pts += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
        if (vals[i] > 0) dots += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5" fill="${color}" opacity="0.9" cursor="pointer" data-action="month" data-year="${year}" data-month="${i}"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="14" fill="transparent" cursor="pointer" data-action="month" data-year="${year}" data-month="${i}"/>`;
      }
      const lx = PL + (months - 1) * SX;
      area = pts + ` L${lx.toFixed(1)},${(H-PB).toFixed(1)} L${PL.toFixed(1)},${(H-PB).toFixed(1)} Z`;
      return `<path d="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><path d="${area}" fill="${color}" opacity="0.08"/>${dots}`;
    };

    let labels = '';
    for (let i = 0; i < months; i += 2) {
      labels += `<text x="${(PL + i * SX).toFixed(1)}" y="${H-4}" text-anchor="middle" fill="var(--secondary-text-color)" font-size="9">${i+1}月</text>`;
    }
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block;pointer-events:auto;"><style>.crc-hover{fill:var(--primary-color);opacity:0.08;pointer-events:none}</style>${mkGrid()}${mkHC(hoverMonth)}${lineSVG(v1, C1, y1)}${lineSVG(v2, C2, y2)}${labels}${mkTip(hoverMonth)}</svg>`;
  }

  _render() {
    const y1 = this._year, y2 = this._year - 1, mode = this._viewMode;
    const d1 = this._yearData[y1] || {}, d2 = this._yearData[y2] || {};
    const ld = this._liveData || {};
    const p = ld.step1Price || 3.5;
    const maxMonth = new Date().getMonth();
    const y1Total = Object.entries(d1).filter(([m]) => Number(m) <= maxMonth).reduce((s, [,v]) => s + Math.max(0, v.change || 0), 0);
    const y2Total = Object.entries(d2).filter(([m]) => Number(m) <= maxMonth).reduce((s, [,v]) => s + Math.max(0, v.change || 0), 0);
    const y1Cost = y1Total * p, y2Cost = y2Total * p;
    const diff = mode === 'gas' ? y1Total - y2Total : y1Cost - y2Cost;
    const diffColor = diff > 0 ? '#f44336' : diff < 0 ? '#4caf50' : 'var(--secondary-text-color)';
    const diffSym = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
    // 从统计数据中找最近有数据的月份（确保和图表的月份一致）
    const _latestDataMonth = Object.keys(d1).filter(m => Number(m) <= maxMonth && (d1[m]?.change || 0) > 0).map(Number).sort((a,b)=>b-a)[0];
    const periodLabel = _latestDataMonth !== undefined ? (_latestDataMonth+1)+'月' : (ld.period||'最近一期');

    if (!this._selectedAccount) {
      this.innerHTML = `
<style>#${this._cardId}{font-family:var(--paper-font-body1_-_font-family)}#${this._cardId} ha-card{border-radius:12px;overflow:hidden}#${this._cardId} .b{padding:20px}#${this._cardId} .ldg{text-align:center;padding:30px;color:var(--secondary-text-color);font-size:14px}#${this._cardId} .ht{font-size:16px;font-weight:600;color:var(--primary-text-color);margin-bottom:10px}</style>
<div id="${this._cardId}"><ha-card><div class="b"><div class="ht">${this._config.title}</div><div class="ldg">⚠️ 请在卡片配置中选择账户（倪合/倪周）</div></div></ha-card></div>`;
      return;
    }

    this.innerHTML = `
<style>
#${this._cardId}{font-family:var(--paper-font-body1_-_font-family)}
#${this._cardId} ha-card{border-radius:12px;overflow:hidden}
#${this._cardId} .b{padding:14px}
#${this._cardId} .h{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
#${this._cardId} .ht{font-size:16px;font-weight:600;color:var(--primary-text-color)}
#${this._cardId} .ha{display:flex;align-items:center;gap:6px}
#${this._cardId} .nb{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:6px;padding:3px 8px;cursor:pointer;font-size:14px;color:var(--primary-text-color);line-height:1.4}
#${this._cardId} .nb:hover{background:var(--primary-color);color:#fff}
#${this._cardId} .nb.a{background:var(--primary-color);color:#fff;border-color:var(--primary-color)}
#${this._cardId} .yt{font-size:14px;font-weight:500;min-width:44px;text-align:center;color:var(--primary-text-color)}
#${this._cardId} .cl{display:flex;justify-content:center;gap:20px;font-size:11px;margin-bottom:4px}
#${this._cardId} .li{display:flex;align-items:center;gap:4px}
#${this._cardId} .ld{width:8px;height:8px;border-radius:50%}
#${this._cardId} .ca{position:relative}
#${this._cardId} .sr{display:flex;gap:6px;margin-bottom:10px}
#${this._cardId} .sc{flex:1;background:var(--secondary-background-color);border-radius:8px;padding:8px 6px;text-align:center;min-width:0}
#${this._cardId} .sv{font-size:15px;font-weight:700;color:var(--primary-text-color)}
#${this._cardId} .sl{font-size:10px;color:var(--secondary-text-color);margin-top:1px}
#${this._cardId} .sd{font-size:10px;margin-top:1px}
#${this._cardId} .ts{margin-bottom:10px}
#${this._cardId} .st{margin-bottom:8px}
#${this._cardId} .st:last-child{margin-bottom:0}
#${this._cardId} .sh{display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px}
#${this._cardId} .shl{color:var(--primary-text-color);font-weight:500}
#${this._cardId} .shr{color:var(--secondary-text-color)}
#${this._cardId} .sp{height:8px;border-radius:4px;overflow:hidden;background:var(--divider-color)}
#${this._cardId} .sf{height:100%;border-radius:4px;background:linear-gradient(90deg,#42a5f5,#1e88e5);transition:width .3s}
#${this._cardId} .f{margin-top:10px}
#${this._cardId} .fr{display:flex;justify-content:space-between;padding:3px 0;font-size:13px;border-top:1px solid var(--divider-color);color:var(--primary-text-color)}
#${this._cardId} .fv{font-weight:600}
#${this._cardId} .ldg{text-align:center;padding:30px 0;color:var(--secondary-text-color);font-size:14px}
#${this._cardId} .sep{width:1px;height:18px;background:var(--divider-color);margin:0 2px}
#${this._cardId} .acct-tag{font-size:13px;font-weight:500;color:var(--primary-color);margin-right:4px}
</style>
<div id="${this._cardId}"><ha-card><div class="b">
<div class="h"><span class="ht"><span class="acct-tag">${ACCOUNTS[this._selectedAccount]?.label||''}</span> ${this._config.title}</span>
<div class="ha">
<button class="nb${mode==='gas'?' a':''}" data-action="sw" data-mode="gas">m³</button><button class="nb${mode==='cost'?' a':''}" data-action="sw" data-mode="cost">¥</button>
<span class="sep"></span>
<button class="nb${this._chartType==='line'?' a':''}" data-action="ct" data-ct="line">📈</button><button class="nb${this._chartType==='bar'?' a':''}" data-action="ct" data-ct="bar">📊</button></div></div>
${this._loading?'<div class="ldg">加载中...</div>':''}
${!this._loading?`
<div class="ha" style="justify-content:center;margin-bottom:6px;gap:8px"><button class="nb" data-action="cy" data-dir="-1">&lsaquo;</button><span class="yt">${this._year}</span><button class="nb" data-action="cy" data-dir="1">&rsaquo;</button></div>
<div class="cl"><span class="li"><span class="ld" style="background:#2196f3"></span> 本年</span><span class="li"><span class="ld" style="background:#7c4dff"></span> 去年同期</span></div>
<div class="ca">${this._renderChart(y1,y2,mode,this._chartType,this._hoverMonth?this._hoverMonth.month:null,this._hoverPos)}</div>
<div class="sr">
<div class="sc"><div class="sv">${mode==='gas'?y1Total.toFixed(1):'¥'+y1Cost.toFixed(0)}</div><div class="sl">本年${mode==='gas'?'用水量':'费用'}</div><div class="sd" style="color:${diffColor}">${diffSym} ${Math.abs(diff).toFixed(mode==='gas'?1:0)}${mode==='gas'?'m³':'元'}</div></div>
<div class="sc"><div class="sv">${mode==='gas'?y2Total.toFixed(1):'¥'+y2Cost.toFixed(0)}</div><div class="sl">去年同期${mode==='gas'?'用水量':'费用'}</div></div>
<div class="sc"><div class="sv">${ld.balance!==null?'¥'+ld.balance.toFixed(2):'--'}</div><div class="sl">余额</div></div>
<div class="sc"><div class="sv">${ld.usage!==null?ld.usage.toFixed(1)+'m³':'--'}</div><div class="sl">${periodLabel}用水</div></div>
<div class="sc"><div class="sv">${ld.bill!==null?'¥'+ld.bill.toFixed(1):'--'}</div><div class="sl">${periodLabel}费用</div></div>
</div>
${ld.step1Shangxian!==null?(() => {
  const s1Limit = ld.step1Shangxian;
  const s1Used = ld.step1Yiyong || 0;
  if (s1Used > 0 && s1Limit > 0) {
    const used = Math.min(s1Used, s1Limit);
    const pct = (used / s1Limit * 100).toFixed(0);
    return `<div class="ts"><div class="st"><div class="sh"><span class="shl">一阶已用 ${used}/${s1Limit} m³</span><span class="shr">余 ${s1Limit - used} m³</span></div><div class="sp"><div class="sf" style="width:${pct}%"></div></div></div></div>`;
  }
  return '';
})() : ''}
<div class="f">
<div class="fr"><span>${y1}年用水总计</span><span class="fv">${y1Total.toFixed(1)} m³</span></div>
<div class="fr"><span>${y1}年费用</span><span class="fv">¥${y1Cost.toFixed(0)}</span></div>
${ld.status?`<div class="fr"><span>集成状态</span><span class="fv" style="color:${ld.status==='normal'||ld.status==='正常'?'#4caf50':'#f44336'}">${ld.status}</span></div>`:''}
</div>`:''}
</div></ha-card></div>`;
  }

  _cy(d) {
    this._year += d;
    this._selectedMonth = null;
    this._loading = true;
    this._render();
    Promise.all([
      this._loadYear(this._year).catch(() => {}),
      !this._yearData[this._year-1] ? this._loadYear(this._year-1).catch(() => {}) : Promise.resolve()
    ]).then(() => { this._loading = false; this._render(); });
  }

  getCardSize() { return 7; }
}

class WaterStatisticsEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; if (this._rendered) this._render(); }

  _render() {
    this._rendered = true;
    const cfg = this._config || {};
    this.innerHTML = `
<div style="padding:16px;font-family:var(--paper-font-body1_-_font-family)">
  <div style="margin-bottom:16px">
    <label style="display:block;margin-bottom:4px;font-weight:500;font-size:14px;color:var(--primary-text-color)">标题</label>
    <input id="w-title" value="${cfg.title || '💧 用水统计'}"
      style="width:100%;padding:8px 10px;border:1px solid var(--divider-color);border-radius:6px;background:var(--input-fill);color:var(--primary-text-color);font-size:14px;box-sizing:border-box">
  </div>
  <div style="margin-bottom:16px">
    <label style="display:block;margin-bottom:4px;font-weight:500;font-size:14px;color:var(--primary-text-color)">账户</label>
    <select id="w-account"
      style="width:100%;padding:8px 10px;border:1px solid var(--divider-color);border-radius:6px;background:var(--input-fill);color:var(--primary-text-color);font-size:14px;box-sizing:border-box">
      <option value="">-- 请选择 --</option>
      <option value="ni_he" ${cfg.account==='ni_he'?'selected':''}>${ACCOUNTS.ni_he.label}</option>
      <option value="ni_zhou" ${cfg.account==='ni_zhou'?'selected':''}>${ACCOUNTS.ni_zhou.label}</option>
    </select>
  </div>
</div>`;
    const titleInput = this.querySelector('#w-title');
    const acctSelect = this.querySelector('#w-account');
    const _dispatch = () => {
      if (!this._config || !this._hass) return;
      const event = new Event('config-changed', { bubbles: true, composed: true });
      event.detail = { config: { ...this._config, title: titleInput.value || '💧 用水统计', account: acctSelect.value } };
      this.dispatchEvent(event);
    };
    titleInput.addEventListener('change', _dispatch);
    titleInput.addEventListener('input', _dispatch);
    acctSelect.addEventListener('change', _dispatch);
  }
}

customElements.define('water-statistics-card', WaterStatisticsCard);
customElements.define('water-statistics-editor', WaterStatisticsEditor);
window.customCards = window.customCards || [];
window.customCards.push({ type: 'water-statistics-card', name: '温州水务统计', description: '温州水务用水对比统计 · 配置时选择账户' });
