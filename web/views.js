/* 渲染层·共享件：列名映射、流程步骤、计数/元信息渲染，以及跨子文件复用的取数工具。
   本文件**最后加载**：加载时 views-worker.js / views-report.js 里的渲染函数已挂到全局，
   故末尾 `const Views = {...}` 能一次性收齐全部渲染函数。
   `COL_LABEL` / `STEPS` 为顶层 const，只在**运行期**被其它文件读取，不构成 TDZ 问题。 */

const COL_LABEL = {
  type: '类型', douyin_nickname: '抖音昵称', douyin_id: '抖音号', quote_price: '报价',
  doujia_amount: '抖加', doujia_payer: '抖加支付人', is_paid: '是否打款', payer: '打款人',
  pay_date: '打款日期', publish_date: '发布日期', accepted: '是否接单',
  review_result: '审核结果', remark: '备注',
};

const STEPS = [
  { key: 'table', label: '登记测试副本' },
  { key: 'input', label: '粘贴申请文本' },
  { key: 'parse', label: '解析与校验' },
  { key: 'judge', label: '人工裁决' },
  { key: 'commit', label: '写入副本' },
  { key: 'report', label: '汇总与汇报' },
];

function renderStepper(flags) {
  document.getElementById('stepper').innerHTML = STEPS.map((step, idx) => {
    const status = flags[step.key] || 'idle';
    const cls = status === 'done' ? 'step done' : status === 'active' ? 'step active' : 'step';
    return `<span class="${cls}">${UI.esc(String(idx + 1).padStart(2, '0'))}　${UI.esc(step.label)}</span>`;
  }).join('');
  UI.refreshIcons();
}

/* 表级体检项（code 前缀 TABLE_ / rule 前缀 table.）排在队尾 —— 它们不来自本次文本。
   取值一律先兜底成字符串，避免上游字段缺失时把整个面板渲染打断。 */
function isTableLevelAnomaly(a) {
  const code = a && a.code ? String(a.code) : '';
  const rule = a && a.rule_id ? String(a.rule_id) : '';
  return code.indexOf('TABLE_') === 0 || rule.indexOf('table.') === 0;
}

function countBySeverity(result) {
  const out = { P0: 0, P1: 0, P2: 0, open: 0, total: 0 };
  if (!result || !Array.isArray(result.anomalies)) return out;
  result.anomalies.forEach((a) => {
    const sev = a && a.severity;
    if (sev === 'P0' || sev === 'P1' || sev === 'P2') out[sev] += 1;
    out.total += 1;
    if (!a.resolved && a.blocking) out.open += 1;
  });
  return out;
}

function renderCounts(result, filter) {
  const host = document.getElementById('counts');
  if (!result) {
    host.innerHTML = UI.emptyState('尚未解析。载入或粘贴申请文本后开始校验。', 'scan-text');
    return;
  }
  const c = countBySeverity(result);
  const cells = [
    { tone: 'block', sev: 'P0', label: '阻断', value: c.P0, note: '禁止写入' },
    { tone: 'warn', sev: 'P1', label: '警告', value: c.P1, note: '可写但标注待确认' },
    { tone: 'ok', sev: 'P2', label: '提示', value: c.P2, note: '观察性提示' },
  ];
  host.innerHTML = cells.map((cell) => `
    <button class="counter" type="button" data-tone="${cell.tone}" data-sev="${cell.sev}"
      data-active="${filter === cell.sev}">
      ${UI.icon(cell.sev === 'P2' ? 'info' : UI.SEV_TONE[cell.sev] === 'block' ? 'octagon-alert' : 'triangle-alert', 16)}
      <span>${UI.esc(cell.label)}</span>
      <span class="num">${cell.value}</span>
      <span class="pill">${UI.esc(cell.note)}</span>
    </button>`).join('');
  UI.refreshIcons();
}

function renderMeta(result) {
  const host = document.getElementById('request-meta');
  if (!result) {
    host.innerHTML = '';
    return;
  }
  const c = result.cross_check;
  const bizLabel = result.biz_type === 'doujia' ? '抖加申请' : '垫付申请';
  host.innerHTML = `
    <div><strong>${UI.esc(bizLabel)}</strong>　批次 ${UI.esc(result.batch_id)}</div>
    <div>申请日 ${UI.esc(result.request_date)}　明细 ${c.line_items_len} 行　声明 `+
    `${UI.esc(c.declared_count === null ? '—' : c.declared_count)} 笔 / 折算 ${UI.esc(c.split_count_sum)} 笔</div>
    <div>明细求和 ${UI.esc(UI.money(c.line_items_sum))}　声明总额 ${UI.esc(UI.money(c.declared_total_amount))}</div>`;
  UI.refreshIcons();
}

/* 账号表行在接口里是**扁平字典**：{"row_ref":"7","douyin_nickname":"葵花夫妇", ...}，
   没有 .values 嵌套。这里兼容两种形态（防御集成层可能的包装变更），
   一律归一为「列名 → 单元格值」；取不到就退化为空值展示，不抛异常。 */
function rowValues(row) {
  if (!row || typeof row !== 'object') return {};
  const nested = row.values;
  return nested && typeof nested === 'object' && !Array.isArray(nested) ? nested : row;
}

function sheetRowTable(row, conflictField) {
  if (!row) return '';
  const values = rowValues(row);
  const keys = Object.keys(COL_LABEL);
  const head = ['字段', '单元格值'].map((h) => `<th>${UI.esc(h)}</th>`).join('');
  const body = keys.map((key) => {
    const raw = values[key];
    const empty = raw === null || raw === undefined || String(raw).trim() === '';
    const cls = key === conflictField ? 'cell-conflict' : empty ? 'cell-empty' : '';
    return `<tr><td>${UI.esc(COL_LABEL[key])}</td><td class="${cls}">${UI.plain(raw)}</td></tr>`;
  }).join('');
  return `<table class="sheet-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* 「匹配歧义」的候选目标行**必须**取自解析结果的 match_result.candidates
 * （文本第 line_no 行 → 命中台账多行，含 row_ref / 昵称 / 抖音号 的实测值）。
 * 不解析 evidence_note 的自然语言文案来反推行号：那是给人看的说明，
 * 措辞一变取数即失效，且会把展示层文本当成数据源。 */
function ambiguousCandidates(result, anomaly) {
  const items = result && Array.isArray(result.line_items) ? result.line_items : [];
  const line = items.find((li) => li && li.line_no === anomaly.line_no);
  const match = line && line.match_result ? line.match_result : null;
  const raw = match && Array.isArray(match.candidates) ? match.candidates : [];
  const seen = Object.create(null);
  return raw.reduce((out, cand) => {
    if (!cand || cand.row_ref === null || cand.row_ref === undefined) return out;
    const ref = String(cand.row_ref);
    if (seen[ref]) return out;
    seen[ref] = true;
    out.push({ ref, name: cand.douyin_nickname || '', id: cand.douyin_id || '' });
    return out;
  }, []);
}

const Views = {
  renderStepper, renderCounts, renderMeta, renderQueue, renderEvidence,
  renderActions, renderResolved, renderSummary, renderReport, renderLedger, countBySeverity,
};
