/* 交互动作层：解析 / 裁决 / 写入 / 汇报等有副作用的动作，以及 DOM 事件装配。
   本文件**不持有全局状态**——由 app.js 通过 AppActions.create(ctx) 注入
   { state, paint, status, currentBiz }，从而让 IIFE 的私有 state 仍只闭包在 app.js 内，
   动作层经 ctx 间接读写它。所有动作函数共享同一个 ctx，彼此调用（如 doParse→refreshSummary）无需再传参。 */

const AppActions = {
  create(ctx) {
    const { state, paint, status, currentBiz } = ctx;

    async function initTable() {
      state.tableId = (await API.ensureTable()).table_id;
      state.tableDetail = await API.getTable(state.tableId);
      status(`已登记账号表测试副本 ${state.tableId}（${state.tableDetail.row_count} 行有效数据，原表只读）。`);
      paint();
    }

    async function doParse() {
      const text = document.getElementById('raw-text').value.trim();
      if (!text) {
        status('尚未输入文本。请粘贴申请原文，或点「填充示例」载入物料原文。');
        UI.toast('请先粘贴申请文本，或点「填充示例」载入物料原文。', 'block');
        return;
      }
      if (!state.tableId) {
        status('账号表副本尚未登记完成，请稍候再解析。');
        UI.toast('账号表副本尚未登记完成，请稍候再试。', 'block');
        return;
      }
      state.rawText = document.getElementById('raw-text').value;
      status('解析中…');
      let result;
      try {
        result = await API.parse(state.rawText, currentBiz(), state.tableId);
      } catch (err) {
        state.result = null;
        state.requestId = null;
        state.selectedId = null;
        status('解析失败：' + err.message);
        UI.toast(err.message, 'block');
        paint();
        return;
      }
      /* 写表必须与校验用的是同一张表：以服务端回传的 table_id 为准对齐本地副本。 */
      if (result.table_id && result.table_id !== state.tableId) {
        state.tableId = result.table_id;
        try {
          state.tableDetail = await API.getTable(state.tableId);
        } catch (err) {
          state.tableDetail = null;
        }
      }
      state.result = result;
      state.requestId = result.request_id;
      state.commitResult = null;
      state.report = null;
      const p0 = result.anomalies.filter((a) => a.blocking);
      const first = result.anomalies.find((a) => a.blocking) || result.anomalies[0];
      state.selectedId = first ? first.anomaly_id : null;
      document.getElementById('summary-date').value = result.request_date;
      status(`解析完成：${result.line_items.length} 条明细，${result.anomalies.length} 项异常（阻断 ${p0.length} 项）。`);
      await refreshSummary();
      await loadDecisions();
      paint();
      UI.toast(p0.length ? `检出 ${p0.length} 项阻断，写表闸门已关闭。` : '未检出阻断项，可写入测试副本。', p0.length ? 'block' : 'ok');
    }

    async function doResolve(action) {
      if (!state.result) return;
      const operator = document.getElementById('op').value.trim() || '未署名';
      const reason = document.getElementById('reason').value.trim();
      const target = document.getElementById('target').value.trim();
      if (action === 'ignore' && !reason) {
        UI.toast('打回重提必须填写理由。', 'block');
        return;
      }
      if (action === 'override' && !target) {
        UI.toast('「修正为某值」必须提供修正值或目标行。', 'block');
        return;
      }
      try {
        await API.resolve(state.requestId, {
          anomaly_id: state.selectedId,
          decision: action,
          override_value: action === 'override' ? target : null,
          operator,
          note: reason || null,
        });
        state.result = await API.getRequest(state.requestId);
        await loadDecisions();
        const openP0 = state.result.anomalies.filter((a) => a.blocking && !a.resolved);
        if (openP0.length && !openP0.some((a) => a.anomaly_id === state.selectedId)) {
          state.selectedId = openP0[0].anomaly_id;
        }
        await refreshSummary();
        paint();
        UI.toast(openP0.length ? `已记录裁决，仍有 ${openP0.length} 项阻断待处理。` : '已记录裁决，闸门已解除。', 'ok');
      } catch (err) {
        UI.toast('HTTP ' + err.status + ' · ' + err.message, 'block');
      }
    }

    async function doCommit() {
      if (!state.result) return;
      try {
        const outcome = await API.commit(state.requestId, state.tableId);
        state.commitResult = outcome;
        state.tableDetail = await API.getTable(state.tableId);
        state.result = await API.getRequest(state.requestId);
        await refreshSummary();
        paint();
        UI.toast(`写入完成：成功 ${outcome.written_count} 条，跳过 ${outcome.skipped_count} 条。`, 'ok');
      } catch (err) {
        UI.toast('HTTP ' + err.status + ' · ' + err.message + '（未发生任何写入）', 'block');
      }
    }

    async function refreshSummary() {
      try {
        state.summary = await API.summary(document.getElementById('summary-date').value);
      } catch (err) {
        state.summary = null;
      }
    }

    async function doReport() {
      try {
        state.report = await API.createReport(document.getElementById('summary-date').value);
        paint();
      } catch (err) {
        UI.toast('生成汇报失败：' + err.message, 'block');
      }
    }

    async function loadDecisions() {
      if (!state.requestId) return;
      try {
        const res = await fetch(API.decisionsUrl(state.requestId, 'json'));
        state.decisions = await res.json();
      } catch (err) {
        state.decisions = [];
      }
    }

    function wire() {
      document.getElementById('btn-parse').addEventListener('click', doParse);
      document.getElementById('btn-sample').addEventListener('click', () => {
        const biz = currentBiz();
        document.getElementById('raw-text').value = SAMPLES[biz];
        state.rawText = SAMPLES[biz];
        status('已载入物料原文示例（' + (biz === 'doujia' ? '抖加申请' : '垫付申请') + '）。');
        paint();
      });
      document.getElementById('btn-clear').addEventListener('click', () => {
        document.getElementById('raw-text').value = '';
        state.rawText = '';
        state.result = null;
        state.requestId = null;
        state.selectedId = null;
        state.commitResult = null;
        state.report = null;
        status('已清空。');
        paint();
      });
      document.getElementById('btn-upload').addEventListener('click', () => document.getElementById('file-input').click());
      document.getElementById('file-input').addEventListener('change', async (ev) => {
        const file = ev.target.files[0];
        if (!file) return;
        const text = await file.text();
        document.getElementById('raw-text').value = text;
        state.rawText = text;
        status(`已载入文件 ${file.name}（${text.length} 字符）。`);
        paint();
      });
      document.getElementById('biz-tabs').addEventListener('click', (ev) => {
        const tab = ev.target.closest('.tab');
        if (!tab) return;
        document.querySelectorAll('#biz-tabs .tab').forEach((t) => t.setAttribute('aria-selected', String(t === tab)));
      });
      document.getElementById('queue').addEventListener('click', (ev) => {
        const item = ev.target.closest('.queue-item');
        if (!item) return;
        state.selectedId = item.getAttribute('data-id');
        paint();
      });
      document.getElementById('queue-chips').addEventListener('click', (ev) => {
        const chip = ev.target.closest('.chip');
        if (!chip) return;
        state.filter = chip.getAttribute('data-filter');
        paint();
      });
      document.getElementById('counts').addEventListener('click', (ev) => {
        const counter = ev.target.closest('.counter');
        if (!counter) return;
        const sev = counter.getAttribute('data-sev');
        state.filter = state.filter === sev ? 'all' : sev;
        paint();
      });
      document.getElementById('actions').addEventListener('click', (ev) => {
        const btn = ev.target.closest('button[data-action]');
        if (!btn || btn.disabled) return;
        doResolve(btn.getAttribute('data-action'));
      });
      document.getElementById('btn-commit').addEventListener('click', doCommit);
      document.getElementById('btn-summary').addEventListener('click', async () => { await refreshSummary(); paint(); });
      document.getElementById('summary-date').addEventListener('change', async () => { await refreshSummary(); paint(); });
      document.getElementById('btn-report').addEventListener('click', doReport);
      document.getElementById('btn-csv').addEventListener('click', () => {
        if (state.requestId) window.open(API.decisionsUrl(state.requestId, 'csv'), '_blank');
      });
      document.getElementById('btn-theme').addEventListener('click', () => {
        const root = document.documentElement;
        const dark = root.getAttribute('data-theme') === 'dark';
        root.setAttribute('data-theme', dark ? 'light' : 'dark');
        document.getElementById('theme-label').textContent = dark ? '深色' : '浅色';
        /* lucide 会把 <i data-lucide> 就地换成 <svg data-lucide>，之后按 "i" 就选不到了，
           所以要按 data-lucide 属性找当前图标节点（svg / i 都认）。 */
        const ico = document.querySelector('#btn-theme [data-lucide]') || document.querySelector('#btn-theme svg');
        if (ico) {
          const holder = document.createElement('i');
          holder.setAttribute('data-lucide', dark ? 'moon' : 'sun');
          holder.setAttribute('data-size', '16');
          ico.replaceWith(holder);
          UI.refreshIcons();
        }
      });
      document.getElementById('btn-help').addEventListener('click', () => {
        UI.toast('口径说明：抖加是流量券费用，与合作报价是两回事；是否打款/打款人/打款日期须人工确认后才写入；跨源总额不可验证，只标注不阻断。');
      });
    }

    return { initTable, doParse, doResolve, doCommit, refreshSummary, doReport, loadDecisions, wire };
  },
};
