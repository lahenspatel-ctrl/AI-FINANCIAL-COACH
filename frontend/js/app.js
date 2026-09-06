/**
 * AI Financial Coach — Frontend App
 * Vanilla ES modules, no build step.
 */

const API     = '';
const USER_ID = 'demo';

// ── Utility ──────────────────────────────────────────────────────────────────

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function escHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

const CAT_EMOJI = {
  'Food & Dining': '🍔', 'Shopping': '🛍️', 'Transportation': '🚗',
  'Housing': '🏠', 'Utilities': '💡', 'Healthcare': '💊',
  'Entertainment': '🎬', 'Travel': '✈️', 'Education': '📚',
  'Personal Care': '💆', 'Income': '💰', 'Transfers': '↔️',
  'Investments': '📈', 'Fees & Charges': '💸', 'Other': '📦',
};
const catEmoji = (cat) => CAT_EMOJI[cat] || '📦';

// ── Currency ──────────────────────────────────────────────────────────────────

const CURRENCIES = {
  USD: { rate: 1,      symbol: '$',   flag: '🇺🇸', name: 'US Dollar' },
  EUR: { rate: 0.92,   symbol: '€',   flag: '🇪🇺', name: 'Euro' },
  GBP: { rate: 0.79,   symbol: '£',   flag: '🇬🇧', name: 'British Pound' },
  CAD: { rate: 1.36,   symbol: 'C$',  flag: '🇨🇦', name: 'Canadian Dollar' },
  AUD: { rate: 1.53,   symbol: 'A$',  flag: '🇦🇺', name: 'Australian Dollar' },
  JPY: { rate: 149.5,  symbol: '¥',   flag: '🇯🇵', name: 'Japanese Yen' },
  INR: { rate: 83.2,   symbol: '₹',   flag: '🇮🇳', name: 'Indian Rupee' },
  CHF: { rate: 0.90,   symbol: 'Fr',  flag: '🇨🇭', name: 'Swiss Franc' },
  MXN: { rate: 17.1,   symbol: 'MX$', flag: '🇲🇽', name: 'Mexican Peso' },
  BRL: { rate: 4.97,   symbol: 'R$',  flag: '🇧🇷', name: 'Brazilian Real' },
  SGD: { rate: 1.35,   symbol: 'S$',  flag: '🇸🇬', name: 'Singapore Dollar' },
};

let currentCurrency = localStorage.getItem('fc_currency') || 'USD';

function fmt(n) {
  const info = CURRENCIES[currentCurrency];
  const converted = n * (info?.rate || 1);
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currentCurrency, maximumFractionDigits: 0,
    }).format(converted);
  } catch { return `${info?.symbol || '$'}${Math.round(converted).toLocaleString()}`; }
}

function fmtFull(n) {
  const info = CURRENCIES[currentCurrency];
  const converted = n * (info?.rate || 1);
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currentCurrency,
    }).format(converted);
  } catch { return `${info?.symbol || '$'}${converted.toFixed(2)}`; }
}

function updateCurrencyPill() {
  const info = CURRENCIES[currentCurrency];
  if (info) $('#currencyPill').textContent = `${info.flag} ${currentCurrency}`;
}

function openCurrencyModal() {
  const grid = $('#currencyGrid');
  grid.innerHTML = '';
  Object.entries(CURRENCIES).forEach(([code, info]) => {
    const btn = document.createElement('button');
    btn.className = `currency-opt${code === currentCurrency ? ' active' : ''}`;
    btn.innerHTML = `
      <span class="currency-flag">${info.flag}</span>
      <span class="currency-code">${code}</span>
      <span class="currency-name">${info.name}</span>`;
    btn.addEventListener('click', () => {
      currentCurrency = code;
      localStorage.setItem('fc_currency', code);
      updateCurrencyPill();
      closeCurrencyModal();
      // Re-render all displayed data
      loadDashboard();
      loadTransactions();
    });
    grid.appendChild(btn);
  });
  $('#currencyModal').hidden = false;
}

function closeCurrencyModal() { $('#currencyModal').hidden = true; }

// ── Theme ─────────────────────────────────────────────────────────────────────

let currentTheme = localStorage.getItem('fc_theme') || 'light';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = $('#themeToggleBtn');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  currentTheme = theme;
}

// ── State ─────────────────────────────────────────────────────────────────────

let categoryChart = null;
let trendChart    = null;
let txnOffset     = 0;
let currentRunId  = null;
let lastDashData  = null;  // cached for income statement re-render

// ── On load ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  applyTheme(currentTheme);
  updateCurrencyPill();
  initBots();

  await Promise.all([
    loadDashboard(),
    loadTransactions(),
    loadChatHistory(),
    loadDebtList(),
    loadIncomeList(),
    loadKeys(),
  ]);

  bindEvents();
});

// ── Dashboard data ────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const res = await fetch(`${API}/api/dashboard/summary?user_id=${USER_ID}`);
    if (!res.ok) return;
    const data = await res.json();
    lastDashData = data;
    updateStats(data);
    renderCharts(data);
    renderDebtCard(data);
    renderIncomeStatement(data);
  } catch (e) {
    console.warn('Dashboard load failed:', e);
  }
}

function updateStats(data) {
  $('#statIncome').textContent   = fmt(data.total_income);
  $('#statExpenses').textContent = fmt(data.total_expenses);
  $('#statDebt').textContent     = fmt(data.total_debt);
  $('#statSavings').textContent  = data.savings_rate != null
    ? `${(data.savings_rate * 100).toFixed(1)}%` : '—';
}

function renderCharts(data) {
  if (data.top_categories?.length || data.monthly_trend?.length) {
    $('#chartsSection').hidden = false;
  }

  if (data.top_categories?.length) {
    const labels = data.top_categories.map(c => c.category);
    const values = data.top_categories.map(c => c.amount * (CURRENCIES[currentCurrency]?.rate || 1));
    const colors = ['#0ea5e9','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16'];

    if (categoryChart) categoryChart.destroy();
    categoryChart = new Chart($('#categoryChart'), {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true,
        cutout: '65%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 10, weight: '700' }, padding: 10, boxWidth: 10 } },
          tooltip: { callbacks: { label: ctx => ` ${fmtFull(ctx.raw / (CURRENCIES[currentCurrency]?.rate || 1))}` } },
        },
      },
    });
  }

  if (data.monthly_trend?.length) {
    const trend = data.monthly_trend.slice(-6);
    const rate = CURRENCIES[currentCurrency]?.rate || 1;
    if (trendChart) trendChart.destroy();
    trendChart = new Chart($('#trendChart'), {
      type: 'bar',
      data: {
        labels: trend.map(t => t.month),
        datasets: [
          { label: 'Income',   data: trend.map(t => t.income * rate),   backgroundColor: '#10b981', borderRadius: 6, borderSkipped: false },
          { label: 'Expenses', data: trend.map(t => t.expenses * rate), backgroundColor: '#ef444466', borderRadius: 6, borderSkipped: false },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { font: { size: 10, weight: '700' }, boxWidth: 10 } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 9 } } },
          y: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 9 }, callback: v => fmt(v / rate) } },
        },
      },
    });
  }
}

function renderDebtCard(data) {
  if (!data.total_debt) return;
  $('#debtSection').hidden = false;
  $('#debtTotal').textContent = fmt(data.total_debt);
  $('#avalancheMonths').textContent = data.debt_payoff_months_avalanche
    ? `${data.debt_payoff_months_avalanche} mo` : '—';
  $('#snowballMonths').textContent = data.debt_payoff_months_snowball
    ? `${data.debt_payoff_months_snowball} mo` : '—';
}

// ── Income Statement ─────────────────────────────────────────────────────────

function renderIncomeStatement(data) {
  const section = $('#incomeStatementSection');
  const card    = $('#incomeStatementCard');

  if (!data.total_income && !data.total_expenses) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  const net = (data.total_income || 0) - (data.total_expenses || 0);
  const cats = data.top_categories || [];

  // Calculate other expenses not in top_categories
  const catTotal = cats.reduce((s, c) => s + c.amount, 0);
  const other = (data.total_expenses || 0) - catTotal;

  const catRows = cats.map(c => `
    <div class="pnl-row">
      <span>${escHtml(c.category)}</span>
      <span class="pnl-debit">(${fmtFull(c.amount)})</span>
    </div>`).join('');

  const otherRow = other > 0.5 ? `
    <div class="pnl-row">
      <span>Other</span>
      <span class="pnl-debit">(${fmtFull(other)})</span>
    </div>` : '';

  const periods = data.monthly_trend?.length || 1;
  const periodLabel = periods > 1 ? `${periods}-month period` : 'current period';

  card.innerHTML = `
    <div class="pnl-section">
      <div class="pnl-section-title">Revenue — ${escHtml(periodLabel)}</div>
      <div class="pnl-row">
        <span>Total Income</span>
        <span class="pnl-credit">${fmtFull(data.total_income || 0)}</span>
      </div>
    </div>
    <div class="pnl-divider"></div>
    <div class="pnl-section">
      <div class="pnl-section-title">Expenses by Category</div>
      ${catRows || '<div class="pnl-row"><span style="color:var(--slate-400)">No expense data yet</span></div>'}
      ${otherRow}
      <div class="pnl-row pnl-subtotal">
        <span>Total Expenses</span>
        <span class="pnl-debit">(${fmtFull(data.total_expenses || 0)})</span>
      </div>
    </div>
    <div class="pnl-divider pnl-divider-bold"></div>
    <div class="pnl-section">
      <div class="pnl-row pnl-net">
        <span>NET INCOME</span>
        <span class="${net >= 0 ? 'pnl-credit' : 'pnl-debit'}">${net >= 0 ? fmtFull(net) : `(${fmtFull(Math.abs(net))})`}</span>
      </div>
      ${data.savings_rate != null ? `
      <div class="pnl-row pnl-savings-rate">
        <span>Savings Rate</span>
        <span style="font-weight:700;color:${data.savings_rate >= 0.2 ? 'var(--success)' : 'var(--warning)'}">${(data.savings_rate * 100).toFixed(1)}%</span>
      </div>` : ''}
    </div>`;
}

// ── Transactions — grouped by month ─────────────────────────────────────────

let allTxns = [];
let displayedMonths = 3;

async function loadTransactions(append = false) {
  if (!append) { txnOffset = 0; allTxns = []; displayedMonths = 3; }

  try {
    const res = await fetch(`${API}/api/dashboard/transactions?user_id=${USER_ID}&limit=200&offset=${txnOffset}`);
    if (!res.ok) return;
    const txns = await res.json();
    if (txns.length === 0 && txnOffset === 0) return;

    txnOffset += txns.length;
    allTxns = append ? [...allTxns, ...txns] : txns;

    renderGroupedTransactions(allTxns, displayedMonths);
    $('#txnSection').hidden = false;
  } catch (e) {
    console.warn('Transaction load failed:', e);
  }
}

function renderGroupedTransactions(txns, monthLimit = Infinity) {
  const feed = $('#activityFeed');
  feed.innerHTML = '';

  // Group by YYYY-MM
  const groups = {};
  for (const t of txns) {
    const key = (t.date || '').substring(0, 7);
    if (!groups[key]) groups[key] = [];
    groups[key].push(t);
  }

  const sortedKeys = Object.keys(groups).sort().reverse();
  const keysToShow = sortedKeys.slice(0, monthLimit);

  for (const key of keysToShow) {
    const [year, month] = key.split('-');
    if (!year || !month) continue;
    const monthName = new Date(Number(year), Number(month) - 1, 1)
      .toLocaleString('default', { month: 'long' });
    const groupTxns = groups[key];
    const total = groupTxns.reduce((s, t) => s + t.amount, 0);

    const header = document.createElement('div');
    header.className = 'txn-group-header';
    header.innerHTML = `
      <span class="txn-group-month">${escHtml(monthName)} ${escHtml(year)}</span>
      <span class="txn-group-net ${total >= 0 ? 'credit' : 'debit'}">${total >= 0 ? '+' : ''}${fmtFull(total)}</span>`;
    feed.appendChild(header);

    for (const t of groupTxns) {
      const el = document.createElement('div');
      el.className = 'activity-item';
      const isCredit = t.amount > 0;
      el.innerHTML = `
        <div class="activity-avatar">${catEmoji(t.category)}</div>
        <div class="activity-info">
          <div class="activity-desc">${escHtml(t.description || '—')}</div>
          <div class="activity-cat">${escHtml(t.category || 'Uncategorized')}${t.sub_category ? ' · ' + escHtml(t.sub_category) : ''}</div>
        </div>
        <div class="activity-right">
          <div class="activity-amount ${isCredit ? 'credit' : 'debit'}">${isCredit ? '+' : ''}${fmtFull(t.amount)}</div>
          <div class="activity-date">${escHtml(t.date)}</div>
        </div>`;
      feed.appendChild(el);
    }

    const totalEl = document.createElement('div');
    totalEl.className = 'txn-group-total';
    totalEl.innerHTML = `
      <span>Monthly Total</span>
      <span class="${total >= 0 ? 'credit' : 'debit'}">${total >= 0 ? '+' : ''}${fmtFull(total)}</span>`;
    feed.appendChild(totalEl);
  }

  // Update load-more button
  $('#loadMoreBtn').hidden = (keysToShow.length >= sortedKeys.length);
}

// ── File Upload ───────────────────────────────────────────────────────────────

async function uploadFile(file) {
  const status = $('#uploadStatus');
  const fill   = $('#uploadBarFill');
  const text   = $('#uploadStatusText');
  status.hidden = false;
  fill.style.width = '10%';
  text.textContent = `Uploading ${file.name}…`;

  try {
    const fd = new FormData();
    fd.append('file', file);
    fill.style.width = '40%';
    const res = await fetch(`${API}/api/uploads?user_id=${USER_ID}`, { method: 'POST', body: fd });
    fill.style.width = '70%';
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }
    fill.style.width = '100%';
    text.textContent = `Uploaded ${file.name} successfully`;
    toast(`Uploaded ${file.name}`, 'success');
    await loadDashboard();
    await loadTransactions();
    setTimeout(() => { status.hidden = true; fill.style.width = '0%'; }, 2000);
  } catch (e) {
    fill.style.width = '100%';
    fill.style.background = 'var(--danger)';
    text.textContent = `Error: ${e.message}`;
    toast(e.message, 'error');
    setTimeout(() => { status.hidden = true; fill.style.width = '0%'; fill.style.background = ''; }, 3000);
  }
}

// ── Pipeline Streaming ────────────────────────────────────────────────────────

const AGENT_LABELS = {
  orchestrator:   { icon: '🎯', name: 'Orchestrator' },
  categorizer:    { icon: '🏷️', name: 'Categorizer' },
  debt_analyzer:  { icon: '💳', name: 'Debt Analyzer' },
  savings_agent:  { icon: '🏦', name: 'Savings Strategy' },
  budget_advisor: { icon: '📊', name: 'Budget Advisor' },
};

function getOrCreateAgentCard(agentKey) {
  const list = $('#agentList');
  let card = $(`#agent-${agentKey}`, list);
  if (!card) {
    card = document.createElement('div');
    card.id = `agent-${agentKey}`;
    card.className = 'agent-card';
    const meta = AGENT_LABELS[agentKey] || { icon: '🤖', name: agentKey };
    card.innerHTML = `
      <div class="agent-card-header">
        <span class="agent-name">${meta.icon} ${meta.name}</span>
        <span class="agent-badge badge-started" id="badge-${agentKey}">WAITING</span>
      </div>
      <div class="agent-message" id="msg-${agentKey}">Starting…</div>`;
    list.appendChild(card);
  }
  return card;
}

function updateAgentCard(evt) {
  const key  = evt.agent;
  const card = getOrCreateAgentCard(key);
  const badge = $(`#badge-${key}`);
  const msg   = $(`#msg-${key}`);

  card.className = `agent-card ${evt.status}`;
  badge.className = `agent-badge badge-${evt.status}`;
  badge.textContent = evt.status.toUpperCase();
  msg.textContent = evt.message;

  if (evt.status === 'complete' && key === 'debt_analyzer' && evt.message) {
    $('#debtInsightText').textContent = evt.message;
    if (evt.data) {
      if (evt.data.avalanche) $('#avalancheMonths').textContent = `${evt.data.avalanche.months} mo`;
      if (evt.data.snowball)  $('#snowballMonths').textContent  = `${evt.data.snowball.months} mo`;
      if (evt.data.total_current_debt) {
        $('#debtTotal').textContent = fmt(evt.data.total_current_debt);
        $('#debtSection').hidden = false;
      }
    }
  }
}

async function runPipeline(selectedAgents = null) {
  const btn = $('#runPipelineBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Analyzing…';

  $('#pipelineSection').hidden = false;
  $('#agentList').innerHTML = '';

  try {
    const runRes = await fetch(`${API}/api/pipeline/run?user_id=${USER_ID}`, { method: 'POST' });
    if (!runRes.ok) throw new Error('Failed to start pipeline');
    const { id: runId } = await runRes.json();
    currentRunId = runId;

    let streamUrl = `${API}/api/pipeline/stream/${runId}?user_id=${USER_ID}`;
    if (selectedAgents?.length) streamUrl += `&agents=${selectedAgents.join(',')}`;

    const es = new EventSource(streamUrl);

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        updateAgentCard(evt);
        if (evt.agent === 'orchestrator' && (evt.status === 'complete' || evt.status === 'error')) {
          es.close();
          btn.disabled = false;
          btn.textContent = '⚡ Analyze Again';
          if (evt.status === 'complete') {
            loadDashboard();
            loadTransactions();
            toast('Analysis complete!', 'success');
          }
        }
      } catch (err) {
        console.warn('SSE parse error:', err);
      }
    };

    es.onerror = () => {
      es.close();
      btn.disabled = false;
      btn.textContent = '⚡ Retry';
    };
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.textContent = '⚡ Analyze Now';
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────────

async function loadChatHistory() {
  try {
    const res = await fetch(`${API}/api/chat/history?user_id=${USER_ID}`);
    if (!res.ok) return;
    const msgs = await res.json();
    if (msgs.length === 0) return;
    const container = $('#chatMessages');
    container.innerHTML = '';
    msgs.forEach(m => appendChatMsg(m.role, m.content));
  } catch (e) {
    console.warn('Chat history load failed:', e);
  }
}

function appendChatMsg(role, content) {
  const container = $('#chatMessages');
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  const avatar = role === 'user' ? '👤' : '🤖';
  div.innerHTML = `
    <div class="chat-avatar">${avatar}</div>
    <div class="chat-bubble">${role === 'assistant' ? marked.parse(content || '') : escHtml(content)}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div.querySelector('.chat-bubble');
}

async function sendChat(message) {
  if (!message.trim()) return;
  const input   = $('#chatInput');
  const sendBtn = $('#chatSend');
  input.value = '';
  input.disabled = true;
  sendBtn.disabled = true;

  appendChatMsg('user', message);

  const container = $('#chatMessages');
  const assistDiv = document.createElement('div');
  assistDiv.className = 'chat-msg assistant';
  assistDiv.innerHTML = `<div class="chat-avatar">🤖</div><div class="chat-bubble" id="streaming-bubble"><span class="spinning">⟳</span></div>`;
  container.appendChild(assistDiv);
  container.scrollTop = container.scrollHeight;

  const bubble = $('#streaming-bubble');
  let fullText = '';

  try {
    const res = await fetch(`${API}/api/chat/send?user_id=${USER_ID}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: message }),
    });
    if (!res.ok) throw new Error('Chat request failed');

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'token') {
            fullText += evt.content;
            bubble.innerHTML = marked.parse(fullText);
            container.scrollTop = container.scrollHeight;
          } else if (evt.type === 'tool_start') {
            const ind = document.createElement('div');
            ind.className = 'tool-indicator';
            ind.id = `tool-${evt.tool}`;
            ind.innerHTML = `<span class="spinning">⟳</span> Searching: ${escHtml(evt.tool)}`;
            container.appendChild(ind);
            container.scrollTop = container.scrollHeight;
          } else if (evt.type === 'tool_end') {
            $(`#tool-${evt.tool}`)?.remove();
          } else if (evt.type === 'done') {
            bubble.id = '';
          }
        } catch (_) {}
      }
    }
  } catch (e) {
    bubble.textContent = `Error: ${e.message}`;
    toast(e.message, 'error');
  }

  input.disabled = false;
  sendBtn.disabled = false;
  input.focus();
}

// ── Debt / Income Lists ───────────────────────────────────────────────────────

async function loadDebtList() {
  try {
    const res = await fetch(`${API}/api/dashboard/debts?user_id=${USER_ID}`);
    if (!res.ok) return;
    const debts = await res.json();
    const section = $('#debtListSection');
    const list    = $('#debtList');
    list.innerHTML = '';
    if (debts.length === 0) { section.hidden = true; return; }
    section.hidden = false;
    debts.forEach(d => {
      const el = document.createElement('div');
      el.className = 'data-item';
      el.innerHTML = `
        <div class="data-item-info">
          <div class="data-item-name">${escHtml(d.name)}</div>
          <div class="data-item-sub">${fmtFull(d.balance)} · ${(d.apr * 100).toFixed(1)}% APR · ${fmtFull(d.minimum_payment)}/mo min</div>
        </div>
        <button class="btn-delete" data-id="${escHtml(d.id)}" data-type="debts" title="Delete">✕</button>`;
      list.appendChild(el);
    });
  } catch (e) { console.warn('Debt list load failed:', e); }
}

async function loadIncomeList() {
  try {
    const res = await fetch(`${API}/api/dashboard/income?user_id=${USER_ID}`);
    if (!res.ok) return;
    const incomes = await res.json();
    const section = $('#incomeListSection');
    const list    = $('#incomeList');
    list.innerHTML = '';
    if (incomes.length === 0) { section.hidden = true; return; }
    section.hidden = false;
    incomes.forEach(i => {
      const el = document.createElement('div');
      el.className = 'data-item';
      el.innerHTML = `
        <div class="data-item-info">
          <div class="data-item-name">${escHtml(i.source)}</div>
          <div class="data-item-sub">${fmtFull(i.monthly_amount)}/mo · ${escHtml(i.income_type)}</div>
        </div>
        <button class="btn-delete" data-id="${escHtml(i.id)}" data-type="income" title="Delete">✕</button>`;
      list.appendChild(el);
    });
  } catch (e) { console.warn('Income list load failed:', e); }
}

async function deleteItem(type, id) {
  const res = await fetch(`${API}/api/dashboard/${type}/${id}?user_id=${USER_ID}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete ${type}`);
  if (type === 'debts') { await loadDebtList(); } else { await loadIncomeList(); }
  await loadDashboard();
  toast(`${type === 'debts' ? 'Debt' : 'Income'} removed`, 'success');
}

// ── Manual data entry ─────────────────────────────────────────────────────────

async function addDebt(form) {
  const data = Object.fromEntries(new FormData(form));
  data.apr             = parseFloat(data.apr) / 100;
  data.balance         = parseFloat(data.balance);
  data.minimum_payment = parseFloat(data.minimum_payment);
  const res = await fetch(`${API}/api/dashboard/debts?user_id=${USER_ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed to add debt');
  form.reset();
  toast('Debt added!', 'success');
  await loadDashboard();
  await loadDebtList();
}

async function addIncome(form) {
  const data = Object.fromEntries(new FormData(form));
  data.monthly_amount = parseFloat(data.monthly_amount);
  const res = await fetch(`${API}/api/dashboard/income?user_id=${USER_ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Failed to add income');
  form.reset();
  toast('Income added!', 'success');
  await loadDashboard();
  await loadIncomeList();
}

// ── API Keys ─────────────────────────────────────────────────────────────────

async function loadKeys() {
  try {
    const res = await fetch(`${API}/api/settings/keys`);
    if (!res.ok) return;
    const data = await res.json();

    const orEl = $('#orKeyStatus');
    const tvEl = $('#tvKeyStatus');
    if (orEl) {
      orEl.textContent  = data.openrouter.is_set ? `Configured (${data.openrouter.masked})` : 'Not configured';
      orEl.className    = `api-key-status ${data.openrouter.is_set ? 'key-set' : 'key-unset'}`;
    }
    if (tvEl) {
      tvEl.textContent = data.tavily.is_set ? `Configured (${data.tavily.masked})` : 'Not configured';
      tvEl.className   = `api-key-status ${data.tavily.is_set ? 'key-set' : 'key-unset'}`;
    }
  } catch (e) { console.warn('Failed to load keys:', e); }
}

async function saveKeys() {
  const orKey = $('#orKeyInput')?.value.trim();
  const tvKey = $('#tvKeyInput')?.value.trim();
  if (!orKey && !tvKey) { toast('Enter at least one API key', 'error'); return; }

  try {
    const body = {};
    if (orKey) body.openrouter_api_key = orKey;
    if (tvKey) body.tavily_api_key     = tvKey;

    const res = await fetch(`${API}/api/settings/keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Failed to save keys');

    if ($('#orKeyInput')) $('#orKeyInput').value = '';
    if ($('#tvKeyInput')) $('#tvKeyInput').value = '';
    await loadKeys();
    toast('API keys saved', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

// ── Profile Dropdown ─────────────────────────────────────────────────────────

function openProfile() {
  $('#profileDropdown').hidden  = false;
  $('#profileBackdrop').hidden  = false;
  loadKeys();
}

function closeProfile() {
  $('#profileDropdown').hidden = true;
  $('#profileBackdrop').hidden = true;
}

// ── Debt Insights Modal ───────────────────────────────────────────────────────

async function openDebtModal() {
  $('#debtModal').hidden = false;
  const body = $('#debtModalBody');
  body.innerHTML = '<p class="modal-empty">Loading…</p>';

  try {
    const res = await fetch(`${API}/api/dashboard/debts?user_id=${USER_ID}`);
    const debts = await res.json();

    if (debts.length === 0) {
      body.innerHTML = '<p class="modal-empty">No debts on file. Add debts to see payoff analysis.</p>';
      return;
    }

    const totalBalance = debts.reduce((s, d) => s + d.balance, 0);
    const totalMin     = debts.reduce((s, d) => s + d.minimum_payment, 0);
    const avalText     = $('#avalancheMonths').textContent;
    const snowText     = $('#snowballMonths').textContent;
    const insight      = $('#debtInsightText').textContent;

    const debtRows = debts.map(d => `
      <div class="debt-row">
        <div class="debt-row-info">
          <div class="debt-row-name">${escHtml(d.name)}</div>
          <div class="debt-row-type">${escHtml(d.debt_type || 'debt')} · ${(d.apr * 100).toFixed(1)}% APR</div>
        </div>
        <div>
          <div class="debt-row-balance">${fmtFull(d.balance)}</div>
          <div class="debt-row-min">${fmtFull(d.minimum_payment)}/mo min</div>
        </div>
      </div>`).join('');

    body.innerHTML = `
      <div class="debt-insight-summary">
        <div class="dis-total">${fmtFull(totalBalance)} total debt</div>
        <div class="dis-min">Minimum payments: ${fmtFull(totalMin)}/mo</div>
      </div>
      <div class="debt-strategy-grid">
        <div class="strategy-card avalanche">
          <div class="strategy-name">⚡ Avalanche (recommended)</div>
          <div class="strategy-time">${avalText || '—'}</div>
          <div class="strategy-desc">Pay highest APR first — saves the most interest</div>
        </div>
        <div class="strategy-card snowball">
          <div class="strategy-name">❄️ Snowball</div>
          <div class="strategy-time">${snowText || '—'}</div>
          <div class="strategy-desc">Pay smallest balance first — most motivating</div>
        </div>
      </div>
      <div class="debt-list-title">Your Debts</div>
      <div class="debt-breakdown">${debtRows}</div>
      ${insight ? `<div class="debt-ai-insight">${escHtml(insight)}</div>` : ''}`;
  } catch (e) {
    body.innerHTML = '<p class="modal-empty">Failed to load debt data.</p>';
  }
}

function closeDebtModal() { $('#debtModal').hidden = true; }

// ── AI Bots ───────────────────────────────────────────────────────────────────

const BOT_AGENTS = [
  { icon: '🎯', name: 'Orchestrator',    dur: 9,  delay: 0   },
  { icon: '🏷️', name: 'Categorizer',     dur: 14, delay: 3   },
  { icon: '💳', name: 'Debt Analyzer',   dur: 11, delay: 6.5 },
  { icon: '🏦', name: 'Savings Agent',   dur: 8,  delay: 9   },
  { icon: '📊', name: 'Budget Advisor',  dur: 13, delay: 1.5 },
];

function initBots() {
  const stage = $('#botStage');
  BOT_AGENTS.forEach(agent => {
    const bot = document.createElement('div');
    bot.className = 'bot';
    bot.title     = agent.name;
    bot.textContent = agent.icon;
    bot.style.setProperty('--dur',   `${agent.dur}s`);
    bot.style.setProperty('--delay', `${agent.delay}s`);
    stage.appendChild(bot);
  });
}

// ── Reset all data ────────────────────────────────────────────────────────────

async function resetAllData() {
  if (!confirm('Delete ALL data for this session? This cannot be undone.')) return;
  try {
    const res = await fetch(`${API}/api/dashboard/reset?user_id=${USER_ID}`, { method: 'POST' });
    if (!res.ok) throw new Error('Reset failed');
    toast('All data cleared', 'success');
    await Promise.all([loadDashboard(), loadTransactions(), loadDebtList(), loadIncomeList()]);
    $('#chatMessages').innerHTML = '<div class="chat-msg assistant"><div class="chat-avatar">🤖</div><div class="chat-bubble">Hi! I\'m your AI financial coach. Upload your bank statement or ask me anything about budgeting, debt payoff, or savings.</div></div>';
    closeProfile();
  } catch (err) { toast(err.message, 'error'); }
}

// ── Event bindings ────────────────────────────────────────────────────────────

function bindEvents() {
  // File upload
  $('#fileInput').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (f) uploadFile(f);
    e.target.value = '';
  });

  // Drag & drop on hero card
  const hero = $('.hero-card');
  hero.addEventListener('dragover', (e) => { e.preventDefault(); hero.style.borderColor = 'var(--primary)'; });
  hero.addEventListener('dragleave', () => { hero.style.borderColor = ''; });
  hero.addEventListener('drop', (e) => {
    e.preventDefault(); hero.style.borderColor = '';
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });

  // Analyze button (split main)
  $('#runPipelineBtn').addEventListener('click', () => {
    $('#agentPicker').hidden = true;
    runPipeline(null);
  });

  // Agent picker toggle (split arrow)
  $('#agentPickerBtn').addEventListener('click', () => {
    const picker = $('#agentPicker');
    picker.hidden = !picker.hidden;
  });

  // Run selected agents
  $('#runSelectedBtn').addEventListener('click', () => {
    const selected = $$('#agentPicker input[type="checkbox"]:checked').map(cb => cb.value);
    $('#agentPicker').hidden = true;
    if (selected.length === 0) { toast('Select at least one agent', 'error'); return; }
    runPipeline(selected);
  });

  // Theme toggle
  $('#themeToggleBtn').addEventListener('click', () => {
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
    localStorage.setItem('fc_theme', currentTheme);
  });

  // Currency toggle (header icon + currency pill)
  $('#currencyToggleBtn').addEventListener('click', openCurrencyModal);
  $('#currencyPill').addEventListener('click', openCurrencyModal);
  $('#currencyModalClose').addEventListener('click', closeCurrencyModal);
  $('#currencyModal').addEventListener('click', (e) => {
    if (e.target === $('#currencyModal')) closeCurrencyModal();
  });

  // Profile dropdown
  $('#profileBtn').addEventListener('click', openProfile);
  $('#profileClose').addEventListener('click', closeProfile);
  $('#profileBackdrop').addEventListener('click', closeProfile);
  $('#saveKeysBtn').addEventListener('click', saveKeys);
  $('#profileResetLink').addEventListener('click', resetAllData);

  // Debt insights modal
  $('#viewDebtBtn').addEventListener('click', openDebtModal);
  $('#debtModalClose').addEventListener('click', closeDebtModal);
  $('#debtModal').addEventListener('click', (e) => {
    if (e.target === $('#debtModal')) closeDebtModal();
  });

  // Clickable stat pills
  $('#statPillIncome').addEventListener('click', () => {
    $('#incomeListSection').hidden = false;
    $('#incomeListSection').scrollIntoView({ behavior: 'smooth' });
  });
  $('#statPillIncome').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('#statPillIncome').click();
  });
  $('#statPillExpenses').addEventListener('click', () => {
    $('#txnSection').hidden = false;
    $('#txnSection').scrollIntoView({ behavior: 'smooth' });
  });
  $('#statPillExpenses').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('#statPillExpenses').click();
  });
  $('#statPillDebt').addEventListener('click', () => {
    $('#debtListSection').hidden = false;
    $('#debtListSection').scrollIntoView({ behavior: 'smooth' });
  });
  $('#statPillDebt').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('#statPillDebt').click();
  });

  // Bottom nav
  $$('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.nav-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      if (tab === 'analyze') { runPipeline(null); }
      if (tab === 'chat') $('.chat-section')?.scrollIntoView({ behavior: 'smooth' });
      if (tab === 'transactions') { $('#txnSection').hidden = false; $('#txnSection').scrollIntoView({ behavior: 'smooth' }); }
      if (tab === 'settings') {
        $('#settingsSection').hidden = false;
        $('#settingsSection').scrollIntoView({ behavior: 'smooth' });
      } else {
        if (tab !== 'home') $('#settingsSection').hidden = true;
      }
    });
  });

  // Delete debt / income (event delegation)
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-delete');
    if (!btn) return;
    const { id, type } = btn.dataset;
    try { await deleteItem(type, id); } catch (err) { toast(err.message, 'error'); }
  });

  // Reset all data (settings tab button)
  $('#resetBtn').addEventListener('click', resetAllData);

  // Chat
  $('#chatSend').addEventListener('click', () => sendChat($('#chatInput').value));
  $('#chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat($('#chatInput').value); }
  });

  // Load more transactions
  $('#loadMoreBtn').addEventListener('click', () => {
    displayedMonths += 3;
    renderGroupedTransactions(allTxns, displayedMonths);
  });

  // Manual forms
  $('#debtForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try { await addDebt(e.target); } catch (err) { toast(err.message, 'error'); }
  });
  $('#incomeForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try { await addIncome(e.target); } catch (err) { toast(err.message, 'error'); }
  });

  // Template buttons
  $$('.template-btn').forEach(btn => {
    btn.addEventListener('click', () => $('#fileInput').click());
  });

  // Close agent picker when clicking outside
  document.addEventListener('click', (e) => {
    const picker = $('#agentPicker');
    if (!picker.hidden && !picker.contains(e.target) && e.target !== $('#agentPickerBtn') && e.target !== $('#runPipelineBtn')) {
      picker.hidden = true;
    }
  });
}
