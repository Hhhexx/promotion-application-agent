/* 渲染层·汇总与汇报：当日三口径汇总、负责人汇报卡、裁决日志/副本溯源。
   数据全部来自接口返回（summary.blocks / report / state），本文件不做任何客户端聚合。 */

function renderSummary(summary) {
  const grid = document.getElementById('summary-grid');
  const note = document.getElementById('summary-note');
  if (!summary) {
    grid.innerHTML = UI.emptyState('解析或写入后刷新，显示当日抖加与垫付金额。', 'sigma');
    note.textContent = '';
    return;
  }
  grid.innerHTML = summary.blocks.map((b) => {
    const label = b.biz_type === 'doujia' ? '抖加合计' : '垫付合计';
    const caliber = [
      { k: '文本声明额', v: b.declared_total_amount },
      { k: '明细求和', v: b.line_items_sum },
      { k: '表内该列累计', v: b.sheet_column_sum },
    ];
    return `<div class="summary-cell">
      <div class="label">${UI.icon('banknote', 16)} ${UI.esc(label)}</div>
      <div class="value">${UI.esc(UI.money(b.total_amount))}</div>
      <div class="sub">${UI.esc(b.entry_count)} 笔明细　${UI.esc(b.declared_count === null ? '—' : b.declared_count)} 笔声明</div>
      <div class="caliber">${caliber.map((c) =>
        `<div class="caliber-row"><span>${UI.esc(c.k)}</span><span class="num">${UI.esc(UI.money(c.v))}</span></div>`).join('')}</div>
    </div>`;
  }).join('');
  note.innerHTML = `<div class="side-note">${summary.blocks.map((b) => UI.esc(b.note)).join('<br>')}</div>`;
  UI.refreshIcons();
}

function renderReport(report) {
  const host = document.getElementById('report-host');
  if (!report) {
    host.innerHTML = UI.emptyState('生成后在此显示给负责人的简短汇报（结论 + 数字 + 需决策项）。', 'file-text');
    return;
  }
  host.innerHTML = `
    <div class="report-card">
      <h3>${UI.icon('file-text', 20)} 当日汇报 · ${UI.esc(report.date)}</h3>
      <p class="report-headline">${UI.esc(report.headline)}</p>
      <div class="report-numbers">
        <div><span class="label">抖加合计</span><span class="value">${UI.esc(UI.money(report.doujia_total))}</span></div>
        <div><span class="label">垫付合计</span><span class="value">${UI.esc(UI.money(report.advance_total))}</span></div>
        <div><span class="label">已确认金额</span><span class="value">${UI.esc(UI.money(report.confirmed_amount))}</span></div>
        <div><span class="label">待确认金额</span><span class="value">${UI.esc(UI.money(report.pending_amount))}</span></div>
      </div>
      ${report.decisions.length ? `<ul class="decision-list">${report.decisions.map((d) => `
        <li data-sev="${UI.esc(d.severity)}">${UI.sevPill(d.severity)}<span>${UI.esc(d.headline)}</span>
        <span class="need">${UI.esc(d.need_from)}</span></li>`).join('')}</ul>` :
        `<p class="fold-note">无待决策项。</p>`}
      ${report.overflow_count ? `<p class="fold-note">另有 ${report.overflow_count} 项，见裁决工作台。</p>` : ''}
      <div class="report-meta">数据来源：账号表测试副本（未触碰原表）　生成时间 ${UI.esc(report.generated_at || '')}</div>
      <div class="toolbar">
        <button class="btn" id="btn-copy-report" type="button">${UI.icon('copy', 16)}复制为文本</button>
        <button class="btn" id="btn-download-report" type="button">${UI.icon('download', 16)}下载 Markdown</button>
      </div>
    </div>`;
  UI.refreshIcons();
  const copy = document.getElementById('btn-copy-report');
  if (copy) copy.addEventListener('click', () => window.App.copyReport(report));
  const dl = document.getElementById('btn-download-report');
  if (dl) dl.addEventListener('click', () => window.App.downloadReport(report));
}

function renderLedger(state) {
  const host = document.getElementById('ledger-host');
  const parts = [];
  if (state.tableId) {
    parts.push(`<div>账号表测试副本：<span class="mono">${UI.esc(state.tableId)}</span>　` +
      `${UI.icon('file-stack', 16)} 源表只读，服务端复制后写入</div>`);
  }
  if (state.commitResult) {
    parts.push(`<div>上次写入：成功 ${UI.esc(state.commitResult.written_count)} 条，跳过 ${UI.esc(state.commitResult.skipped_count)} 条</div>`);
    const rows = state.commitResult.written.map((w) =>
      `<tr><td>${UI.esc(w.row_ref)}</td><td>${UI.esc(w.dedup_key)}</td><td>${UI.esc(Object.keys(w.fields_written).join('、') || '（仅溯源列）')}</td></tr>`).join('');
    if (rows) {
      parts.push(`<table class="sheet-table"><thead><tr><th>目标行</th><th>去重键</th><th>写入字段</th></tr></thead><tbody>${rows}</tbody></table>`);
    }
    const skipped = state.commitResult.skipped.map((s) => `${UI.esc(s.dedup_key)}（${UI.esc(s.reason)}）`).join('<br>');
    if (skipped) parts.push(`<div>跳过明细：<br>${skipped}</div>`);
  }
  if (state.decisions && state.decisions.length) {
    parts.push(`<details><summary>裁决日志（append-only，共 ${state.decisions.length} 条）</summary><pre>${UI.esc(JSON.stringify(state.decisions, null, 2))}</pre></details>`);
  }
  host.innerHTML = parts.length ? parts.join('') : UI.emptyState('写入副本后在此显示溯源信息与裁决日志。', 'scroll-text');
  UI.refreshIcons();
}
