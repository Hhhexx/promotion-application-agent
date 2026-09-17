/* 渲染辅助：转义、图标、语义徽章、证据高亮、提示条。
   所有状态一律"颜色 + 图标 + 文字标签"三通道编码，不依赖颜色单通道。 */

const SEV_LABEL = { P0: '阻断', P1: '警告', P2: '提示' };
const SEV_TONE = { P0: 'block', P1: 'warn', P2: 'info' };
const SEV_ICON = { P0: 'octagon-alert', P1: 'triangle-alert', P2: 'info' };

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function icon(name, size) {
  return `<i data-lucide="${esc(name)}" data-size="${size || 16}"></i>`;
}

function refreshIcons() {
  if (!window.lucide || typeof window.lucide.createIcons !== 'function') return;
  document.querySelectorAll('[data-lucide]').forEach((el) => {
    const size = el.getAttribute('data-size');
    if (size) {
      el.setAttribute('width', size);
      el.setAttribute('height', size);
    }
  });
  window.lucide.createIcons();
}

function money(value) {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return '¥' + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function plain(value) {
  return esc(value === null || value === undefined || value === '' ? '（空）' : value);
}

function sevPill(severity) {
  const tone = SEV_TONE[severity] || 'info';
  return `<span class="pill" data-tone="${tone}">${icon(SEV_ICON[severity] || 'info', 16)}${SEV_LABEL[severity] || '提示'}</span>`;
}

function tonePill(text, tone, iconName) {
  return `<span class="pill" data-tone="${tone}">${icon(iconName || 'info', 16)}${esc(text)}</span>`;
}

function toast(message, tone) {
  const host = document.getElementById('toast-host');
  const node = document.createElement('div');
  node.className = 'toast';
  if (tone) node.setAttribute('data-tone', tone);
  const ico = tone === 'block' ? 'octagon-alert' : tone === 'ok' ? 'circle-check' : 'info';
  node.innerHTML = `${icon(ico, 16)}<span>${esc(message)}</span>`;
  host.appendChild(node);
  refreshIcons();
  window.setTimeout(() => node.remove(), 6000);
}

/* 在原文片段中高亮冲突 token。context 为整段来源文本，span 为精确偏移。 */
function highlightSource(text, span, token) {
  if (!text) return '<span class="ev-text">（无来源片段）</span>';
  let start = null;
  let end = null;
  if (span && typeof span.start === 'number' && span.end === span.start) {
    start = span.start;
    end = span.end;
  } else if (span && typeof span.start === 'number') {
    start = span.start;
    end = span.end;
  }
  if (start === null || start === undefined) {
    return `<span class="ev-text">${esc(text)}</span>`;
  }
  const before = text.slice(0, start);
  const middle = text.slice(start, end === undefined ? start : end);
  const after = text.slice(end === undefined ? start : end);
  const cls = token ? 'hl hl-block' : 'hl';
  return `<span class="ev-text">${esc(before)}<mark class="${cls}">${esc(middle)}</mark>${esc(after)}</span>`;
}

/* 把整段原文按给定 token 高亮（用于无精确偏移时退回展示）。 */
function highlightToken(text, token) {
  if (!text) return '<span class="ev-text">（无来源片段）</span>';
  if (!token) return `<span class="ev-text">${esc(text)}</span>`;
  const idx = text.indexOf(token);
  if (idx < 0) return `<span class="ev-text">${esc(text)}</span>`;
  return (
    `<span class="ev-text">${esc(text.slice(0, idx))}` +
    `<mark class="hl hl-block">${esc(token)}</mark>` +
    `${esc(text.slice(idx + token.length))}</span>`
  );
}

function emptyState(message, iconName) {
  return `<div class="empty">${icon(iconName || 'inbox', 24)}<p>${esc(message)}</p></div>`;
}

const UI = {
  SEV_LABEL, SEV_TONE,
  esc, icon, refreshIcons, money, plain, sevPill, tonePill, toast,
  highlightSource, highlightToken, emptyState,
};
