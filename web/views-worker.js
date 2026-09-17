/* 渲染层·异常裁决工作台：裁决队列、证据对照、裁决动作、已裁决回执。
   依赖 views.js 里的共享件（sheetRowTable / ambiguousCandidates / COL_LABEL 等）——
   那些只在**运行期**（用户交互后）被调用，因此本文件先于 views.js 加载是安全的。 */

function renderQueue(state) {
  const host = document.getElementById('queue');
  const chips = document.getElementById('queue-chips');
  const result = state.result;
  if (!result) {
    chips.innerHTML = '';
    host.innerHTML = UI.emptyState('解析后在此列出待裁决项，阻断项排在最前。', 'list-filter');
    return;
  }
  const groups = [
    { key: 'P0', label: '口径不自洽 / 重复 / 日期', n: 0 },
    { key: 'P1', label: '字段缺失 / 待确认', n: 0 },
    { key: 'P2', label: '提示项', n: 0 },
  ];
  const rank = { P0: 0, P1: 1, P2: 2 };
  const cached = result.anomalies.filter(isTableLevelAnomaly);
  const scoped = result.anomalies.filter((a) => !isTableLevelAnomaly(a));
  const render = scoped.concat(cached);
  render.forEach((a) => {
    const group = groups.find((g) => g.key === a.severity);
    if (group) group.n += 1;
  });

  chips.innerHTML = '<button class="chip" data-filter="all" aria-pressed="' + (state.filter === 'all') + '">全部 ' +
    result.anomalies.length + '</button>' +
    groups.map((g) => `<button class="chip" data-filter="${g.key}" aria-pressed="${state.filter === g.key}">${UI.esc(g.label)} ${g.n}</button>`).join('');

  const list = render
    .filter((a) => !state.filter || state.filter === 'all' || a.severity === state.filter)
    .sort((a, b) => (rank[a.severity] - rank[b.severity]) ||
      ((b.impact_amount || 0) - (a.impact_amount || 0)));

  if (!list.length) {
    host.innerHTML = UI.emptyState('没有符合筛选条件的项目。', 'inbox');
    return;
  }
  host.innerHTML = list.map((a) => `
    <li class="queue-item${a.resolved ? ' is-resolved' : ''}" data-sev="${a.severity}"
        data-id="${UI.esc(a.anomaly_id)}" aria-current="${state.selectedId === a.anomaly_id}">
      <span class="sev"></span>
      <span>
        <span class="qi-title">${UI.esc(a.message)}</span>
        <span class="qi-meta">
          <span class="pill">${UI.esc(a.exc_id || a.code)}</span>
          ${a.account_ref ? `<span>${UI.icon('user-round', 16)} ${UI.esc(a.account_ref)}</span>` : ''}
          ${a.line_no ? `<span>第 ${UI.esc(a.line_no)} 行</span>` : ''}
          ${a.resolved ? `<span class="pill" data-tone="ok">${UI.icon('circle-check', 16)}已裁决</span>` : ''}
        </span>
      </span>
      <span>${UI.sevPill(a.severity)}</span>
    </li>`).join('');
  UI.refreshIcons();
}

function renderEvidence(state) {
  const host = document.getElementById('evidence');
  const result = state.result;
  const anomaly = result && state.selectedId
    ? result.anomalies.find((a) => a.anomaly_id === state.selectedId)
    : null;
  if (!anomaly) {
    host.innerHTML = UI.emptyState('在左侧队列选择一项，查看问题、证据与影响。', 'quote');
    return;
  }
  const row = state.tableDetail && anomaly.sheet_row_ref
    ? state.tableDetail.rows.find((r) => r.row_ref === anomaly.sheet_row_ref)
    : null;

  let leftBody;
  if (anomaly.source_span) {
    leftBody = UI.highlightSource(state.rawText || '', anomaly.source_span, anomaly.text_value);
  } else if (anomaly.text_value) {
    leftBody = UI.highlightToken(state.rawText || '', anomaly.text_value);
  } else {
    leftBody = '<span class="ev-text">（本项为表级体检，无对应文本片段）</span>';
  }
  const leftLabel = anomaly.source_span ? '来源文本片段' : '文本侧取值';

  let rightBody;
  if (row) {
    rightBody = sheetRowTable(row, anomaly.target_field);
  } else if (anomaly.sheet_value) {
    rightBody = `<div class="ev-text">${UI.esc(anomaly.sheet_value)}</div>`;
  } else {
    rightBody = '<div class="ev-text">（台账侧无对应取值）</div>';
  }
  const rightLabel = row ? `账号表 · 第 ${row.row_ref} 行` : '台账 / 明细侧取值';

  const impact = [];
  if (anomaly.impact_amount !== null && anomaly.impact_amount !== undefined) {
    impact.push(`影响金额 ${UI.money(anomaly.impact_amount)}`);
  }
  if (anomaly.action_required) impact.push(UI.esc(anomaly.action_required));
  if (anomaly.suggestion) impact.push(`建议：${UI.esc(anomaly.suggestion)}`);
  if (anomaly.evidence_note) impact.push(UI.esc(anomaly.evidence_note));

  host.innerHTML = `
    <p class="ev-claim">${UI.esc(anomaly.message)}</p>
    <div style="display:flex;gap:var(--space-2);flex-wrap:wrap;">
      ${UI.sevPill(anomaly.severity)}
      <span class="pill">${UI.icon('gavel', 16)}规则 ${UI.esc(anomaly.rule_id)}</span>
      <span class="pill">${UI.esc(anomaly.exc_id || anomaly.code)}</span>
      <span class="pill" data-tone="${anomaly.blocking ? 'block' : 'info'}">${anomaly.blocking ? '阻断写表' : '不阻断'}</span>
    </div>
    <div class="ev-section">
      <h4>② 证据对照</h4>
      <div class="ev-compare">
        <div class="ev-pane"><h5>${UI.icon('quote', 16)} ${UI.esc(leftLabel)}</h5>${leftBody}</div>
        <div class="ev-pane"><h5>${UI.icon('table-2', 16)} ${UI.esc(rightLabel)}</h5>${rightBody}</div>
      </div>
    </div>
    <div class="ev-section">
      <h4>③ 影响与所需确认</h4>
      <div class="ev-impact" data-sev="${anomaly.severity}">
        ${impact.length ? impact.join('<br>') : '（本项为观察性提示，无金额影响）'}
      </div>
    </div>
    ${anomaly.resolved ? `<div class="ev-section"><h4>已裁决</h4><div class="ev-text">${
      UI.esc(anomaly.resolution ? `${anomaly.resolution.decision} · ${anomaly.resolution.operator} · ${anomaly.resolution.resolved_at}` : '')
    }</div></div>` : ''}`;
  UI.refreshIcons();
}

const ACTIONS = [
  { key: 'accept', label: '确认无误', icon: 'circle-check', cls: '', hint: '人工核实后认定该异常不成立，放行本项' },
  { key: 'override', label: '修正为某值', icon: 'pencil-line', cls: '', hint: '歧义匹配必须指定目标行；其余可填正确值' },
  { key: 'ignore', label: '打回重提', icon: 'undo-2', cls: 'btn-warn', hint: '退回发起人补充，本批次不得写入' },
];

function renderActions(state) {
  const host = document.getElementById('actions');
  const result = state.result;
  const anomaly = result && state.selectedId
    ? result.anomalies.find((a) => a.anomaly_id === state.selectedId)
    : null;
  if (!anomaly) {
    host.innerHTML = UI.emptyState('选择一项后可在此裁决。', 'gavel');
    return;
  }
  if (anomaly.resolved) {
    host.innerHTML = `<div class="toast" data-tone="ok">${UI.icon('circle-check', 16)}<span>该项已裁决，无需重复操作。</span></div>`;
    UI.refreshIcons();
    return;
  }
  const isAmbiguous = anomaly.code === 'MATCH_AMBIGUOUS';
  const candidates = isAmbiguous ? ambiguousCandidates(result, anomaly) : [];

  host.innerHTML = ACTIONS.map((action) => {
    const disabled = isAmbiguous && action.key === 'accept';
    const title = disabled ? '歧义匹配不能用「确认无误」放行，请指定目标行或打回重提' : action.hint;
    return `<button class="btn ${action.cls}" data-action="${action.key}" type="button"
      ${disabled ? 'disabled' : ''} title="${UI.esc(title)}">
      ${UI.icon(action.icon, 20)}${UI.esc(action.label)}</button>`;
  }).join('') + `
    <div class="field">
      <label for="op">确认人</label>
      <input id="op" value="运营-小林" />
    </div>
    <div class="field">
      <label for="reason">理由 / 备注${anomaly.blocking ? '（打回重提必填）' : '（可选）'}</label>
      <input id="reason" placeholder="例：已与财务核对，按明细 5 笔入账" />
    </div>
    ${isAmbiguous ? `
    <div class="field">
      <label for="target">目标行（修正为某值时必填）</label>
      <select id="target">
        <option value="">请选择目标行</option>
        ${candidates.length
          ? candidates.map((c) => `<option value="${UI.esc(c.ref)}">第 ${UI.esc(c.ref)} 行 · ${UI.esc(c.name || '（昵称缺失）')} · 抖音号 ${UI.esc(c.id || '（空）')}</option>`).join('')
          : '<option value="" disabled>未取到候选行，请改用「打回重提」</option>'}
      </select>
      ${candidates.length ? '' : `<p class="fold-note">候选行取数失败：解析结果里没有第 ${UI.esc(anomaly.line_no === null || anomaly.line_no === undefined ? '—' : anomaly.line_no)} 行的匹配候选，无法指定目标行。</p>`}
    </div>` : `
    <div class="field">
      <label for="target">修正值（修正为某值时必填）</label>
      <input id="target" placeholder="例：2250 或 木木老师" />
    </div>`}
    <p class="fold-note">${UI.esc(anomaly.action_required || '需业务方确认')}</p>`;
  UI.refreshIcons();
}

function renderResolved(state) {
  const host = document.getElementById('resolved-box');
  if (!state.result) {
    host.innerHTML = '';
    return;
  }
  const done = state.result.anomalies.filter((a) => a.resolved);
  if (!done.length) {
    host.innerHTML = '<div>尚无已裁决记录。</div>';
    return;
  }
  host.innerHTML = `<div>已裁决 ${done.length} 项</div><ul>${done.slice(0, 6).map((a) =>
    `<li>${UI.esc(a.exc_id || a.code)} · ${UI.esc(a.resolution ? a.resolution.decision : '')} · ${UI.esc(a.resolution ? a.resolution.operator : '')}</li>`
  ).join('')}</ul>`;
}
