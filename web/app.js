/* 应用装配：私有状态、绘制与闸门、公开 API、启动。
   动作与事件绑定的实现见 app-actions.js；渲染全部委托给 views*.js。
   IIFE 里只留 state / paint / paintGate / status / currentBiz，其余经 AppActions.create 注入。 */

(function () {
  const state = {
    tableId: null,
    tableDetail: null,
    requestId: null,
    rawText: '',
    result: null,
    selectedId: null,
    filter: 'all',
    biz: 'doujia',
    commitResult: null,
    report: null,
    summary: null,
    decisions: [],
  };

  function stepFlags() {
    const openP0 = state.result ? state.result.anomalies.filter((a) => a.blocking && !a.resolved).length : 0;
    return {
      table: state.tableId ? 'done' : 'active',
      input: state.rawText ? 'done' : 'idle',
      parse: state.result ? 'done' : state.rawText ? 'active' : 'idle',
      judge: state.result ? (openP0 ? 'active' : 'done') : 'idle',
      commit: state.commitResult ? 'done' : openP0 === 0 && state.result ? 'active' : 'idle',
      report: state.report ? 'done' : 'idle',
    };
  }

  function paint() {
    Views.renderStepper(stepFlags());
    Views.renderCounts(state.result, state.filter);
    Views.renderMeta(state.result);
    Views.renderQueue(state);
    Views.renderEvidence(state);
    Views.renderActions(state);
    Views.renderResolved(state);
    Views.renderSummary(state.summary);
    Views.renderReport(state.report);
    Views.renderLedger(state);
    paintGate();
  }

  function paintGate() {
    const btn = document.getElementById('btn-commit');
    const note = document.getElementById('gate-note');
    if (!state.result) {
      btn.disabled = true;
      note.textContent = '';
      note.className = 'gate-note';
      document.getElementById('btn-csv').disabled = true;
      return;
    }
    const openP0 = state.result.anomalies.filter((a) => a.blocking && !a.resolved);
    const returned = state.result.anomalies.filter(
      (a) => a.blocking && a.resolved && a.resolution && a.resolution.decision === 'ignore'
    );
    document.getElementById('btn-csv').disabled = false;
    if (returned.length) {
      btn.disabled = true;
      note.className = 'gate-note';
      note.innerHTML = `${UI.icon('undo-2', 16)}存在 ${returned.length} 项已被打回重提，本批次不得写入`;
    } else if (openP0.length) {
      btn.disabled = true;
      note.className = 'gate-note';
      note.innerHTML = `${UI.icon('octagon-alert', 16)}存在 ${openP0.length} 项未裁决阻断，写入已禁用`;
    } else {
      btn.disabled = false;
      note.className = 'gate-note ready';
      note.innerHTML = `${UI.icon('circle-check', 16)}无未裁决阻断项，可写入测试副本`;
    }
    UI.refreshIcons();
  }

  function status(text) {
    document.getElementById('input-status').textContent = text;
  }

  function currentBiz() {
    return document.querySelector('#biz-tabs .tab[aria-selected="true"]').getAttribute('data-biz');
  }

  /* 动作层不持有状态：把 IIFE 私有的 state 与绘制/状态工具注入进去。 */
  const actions = AppActions.create({ state, paint, status, currentBiz });

  window.App = {
    copyReport(report) {
      navigator.clipboard.writeText(report.markdown).then(
        () => UI.toast('汇报文本已复制，可直接粘贴到群聊。', 'ok'),
        () => UI.toast('复制失败，请手动选择文本。', 'block')
      );
    },
    downloadReport(report) {
      const blob = new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `当日汇报-${report.date}.md`;
      a.click();
      URL.revokeObjectURL(url);
    },
  };

  document.addEventListener('DOMContentLoaded', async () => {
    actions.wire();
    paint();
    try {
      await actions.initTable();
    } catch (err) {
      status('账号表登记失败：' + err.message);
      UI.toast('账号表登记失败：' + err.message, 'block');
    }
  });
})();
