/* API 客户端与示例文本。
 *
 * 示例文本直接内嵌：演示环境无需联网、无需额外接口即可载入物料原文
 * （避免为"填充示例"新增契约外的端点）。 */

const SAMPLES = {
  doujia: `【抖加金额统计】今日已支付：¥700（2026-09-02）

明细如下：
歌名：《你是我的仰望》- 博主名：初秋 - 金额：¥300（分 3 笔）
歌名：《你是我的仰望》- 博主名：艳红 - 金额：¥200（分 2 笔）
歌名：《你是我的仰望》- 博主名：唐山第一女泵工 - 金额：¥100
歌名：《你是我的仰望》- 博主名：戎大姨 - 金额：¥100

今日共 7 笔支付申请，合并同博主后为 4 笔。

抖加支付人：爆火音乐`,
  advance: `【垫付统计】今日已垫付：¥2250（2026-09-03）

明细如下：
申请为【达人：初秋】垫付 ¥950（歌曲《你是我的仰望》）
申请为【达人：艳红】垫付 ¥300（歌曲《你是我的仰望》）
申请为【达人：戎大姨】垫付 ¥300（歌曲《你是我的仰望》）
申请为【达人：高高】垫付 ¥200（歌曲《你是我的仰望》）
申请为【达人：葵花夫妇】垫付 ¥500（歌曲《你是我的仰望》）


今日共 7 笔垫付申请。

打款人：林老师
预计打款日期：26/08/31`,
};

class ApiError extends Error {
  constructor(message, status, code, pending) {
    super(message);
    this.status = status;
    this.code = code;
    this.pending = pending || [];
  }
}

async function request(method, path, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  let payload = null;
  try {
    payload = await res.json();
  } catch (err) {
    payload = { code: -1, message: '响应不是合法 JSON' };
  }
  if (!res.ok || (payload && payload.code !== 0)) {
    const pending = payload && payload.data && payload.data.pending ? payload.data.pending : [];
    throw new ApiError((payload && payload.message) || '请求失败', res.status, payload && payload.code, pending);
  }
  return payload.data;
}

const API = {
  ensureTable() {
    return request('POST', '/api/v1/account-tables');
  },
  getTable(tableId) {
    return request('GET', `/api/v1/account-tables/${encodeURIComponent(tableId)}`);
  },
  parse(rawText, bizTypeHint, tableId) {
    const body = { raw_text: rawText, biz_type_hint: bizTypeHint || null, enable_llm: false };
    /* 必须带上 table_id：服务端用该表做匹配校验，写表时也要求是**同一张表**，
       否则提交被拒（code 1001「是依据账号表 X 校验的，不能用 Y 写表」）。
       不传时服务端会退回进程内默认表，和页面登记的副本不是同一张。 */
    if (tableId) body.table_id = tableId;
    return request('POST', '/api/v1/requests/parse', body);
  },
  getRequest(requestId) {
    return request('GET', `/api/v1/requests/${encodeURIComponent(requestId)}`);
  },
  resolve(requestId, payload) {
    return request('POST', `/api/v1/requests/${encodeURIComponent(requestId)}/resolutions`, payload);
  },
  commit(requestId, tableId) {
    return request('POST', `/api/v1/requests/${encodeURIComponent(requestId)}/commit`, { table_id: tableId });
  },
  summary(date) {
    return request('GET', `/api/v1/summary?date=${encodeURIComponent(date)}`);
  },
  createReport(date) {
    return request('POST', '/api/v1/reports/daily', { date, include_unresolved: true });
  },
  decisionsUrl(requestId, format) {
    return `/api/v1/requests/${encodeURIComponent(requestId)}/decisions?format=${format}`;
  },
};
