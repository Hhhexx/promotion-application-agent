#!/usr/bin/env bash
# 补证：三处尚未取得浏览器实证的点
#  A) 表级异常证据面板渲染扁平行（修复前整面板崩）—— 点队列深处的项需先 scrollintoview
#  B) 汇报卡「复制为文本」是否真的调到剪贴板 API（headless 剪贴板策略不可靠，用间谍证）
#  C) 「导出裁决 CSV」是否真的打开 decisions?format=csv 且返回 200 text/csv
set -u
REPO="/c/Users/hu/code/mst"
SD="C:/Users/hu/code/mst/.evidence"
cd "$REPO" || exit 1
PASS=0; FAIL=0
ck(){ if printf '%s' "$2" | grep -qE "$3"; then printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1)); else printf '  [FAIL] %s\n         实际=<%s>\n         期望匹配=/%s/\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
ab(){ timeout 120 agent-browser "$@"; }
ev(){ local v; v=$(ab eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
errs(){ ev "JSON.stringify(window.__errs||[])"; }
pgerr(){ local v; v=$(ab errors | tr -d '\r\n'); [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }

echo "### 补证开始 $(date '+%F %T')"
ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab set viewport 1600 2800 >/dev/null
ev '(function(){window.__errs=[];window.__net=[];window.__opened=[];window.__csv="";window.__clip="";
window.addEventListener("error",function(e){window.__errs.push("error: "+e.message)});
window.addEventListener("unhandledrejection",function(e){window.__errs.push("rejection: "+String(e.reason&&e.reason.message||e.reason))});
var of=window.fetch;window.fetch=function(){var a=arguments,u=String(a[0]);return of.apply(this,a).then(function(r){var c=r.clone();c.text().then(function(t){window.__net.push(r.status+" "+u+" :: "+t.slice(0,80))});return r});};
var ow=window.open;window.open=function(u,n,f){window.__opened.push(String(u));return ow.call(window,u,n,f)};
try{Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:function(t){window.__clip=String(t).slice(0,60);return Promise.resolve()}})}catch(e){window.__clip="(hijack失败:"+e.message+")"}
return "ok"})()' >/dev/null

echo
echo "===== A) 表级异常证据面板（扁平行渲染） ====="
ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2200
echo "-- 解析: $(ab get text '#input-status')"
ab scrollintoview '.queue-item[data-id="anm_09"]' >/dev/null
ab click '.queue-item[data-id="anm_09"]' >/dev/null
ab wait 1200
echo "-- 选中项: $(ev "var el=document.querySelector('.queue-item[aria-current=\"true\"]');el?el.getAttribute('data-id'):'(none)'")"
echo "-- 证据面板标题: $(ev "Array.from(document.querySelectorAll('#evidence .ev-pane h5')).map(function(h){return h.textContent.trim()}).join(' ;; ')")"
echo "-- 右侧台账表: $(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent.replace(/\n/g,'|').slice(0,170):'(无表格)'")"
echo "-- 闸门(证明 paint 未中断): $(ab get text '#gate-note')"
ab screenshot --screenshot-dir "$SD" A-表级异常证据面板.png >/dev/null 2>&1
ck "A 右栏标题=台账行号"        "$(ev "var h=document.querySelectorAll('#evidence .ev-pane h5');h.length>1?h[1].textContent.trim():''")" '账号表 · 第 8 行'
ck "A 台账行取值非空(张栋梁)"    "$(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")" '张栋梁'
ck "A 台账行取值非空(报价/抖加)"  "$(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")" '100'
ck "A 渲染未中断"              "$(ab get text '#gate-note')" '存在 3 项未裁决阻断'
ck "A 无运行时异常"            "$(errs)" '^\[\]$'

echo
echo "===== B) 汇报卡 + 复制为文本（剪贴板间谍） ====="
ab click '#btn-report' >/dev/null
ab wait 2200
echo "-- 汇报卡首行: $(ev "(document.querySelector('#report-host .report-headline')||{}).textContent")"
echo "-- 金额四项: $(ev "Array.from(document.querySelectorAll('#report-host .report-numbers div')).map(function(d){return d.textContent.trim()}).join(' | ')")"
echo "-- 卡片含结论/数据来源: $(ev "var t=document.querySelector('#report-host').textContent;t.indexOf('结论')<0?'(无结论二字,含headline正文即可)':''")"
ab scrollintoview '#btn-copy-report' >/dev/null
ab click '#btn-copy-report' >/dev/null
ab wait 1200
echo "-- 剪贴板间谍收到: $(ev "window.__clip")"
echo "-- 即时 toast: <$(ab get text '#toast-host')>"
ck "B 汇报标题"                 "$(ev "(document.querySelector('#report-host h3')||{}).textContent")" '当日汇报 · 2026-09-03'
ck "B 已确认/待确认金额并列"     "$(ev "document.querySelector('#report-host .report-numbers').textContent")" '已确认金额[\s\S]*待确认金额'
ck "B 汇报金额含 2250"          "$(ev "document.querySelector('#report-host .report-numbers').textContent")" '2,250\.00'
ck "B 复制为文本调到剪贴板 API"  "$(ev "window.__clip")" '当日汇报'
ab scrollintoview '#btn-download-report' >/dev/null
ab click '#btn-download-report' >/dev/null
ab wait 1500
echo "-- 下载后 page errors: $(pgerr)"
ck "B 复制/下载无未捕获异常"      "$(errs)" '^\[\]$'

echo
echo "===== C) 导出裁决 CSV ====="
ab scrollintoview '#btn-csv' >/dev/null
echo "-- 按钮 disabled: $(ab is enabled '#btn-csv')"
ab click '#btn-csv' >/dev/null
ab wait 1500
echo "-- window.open: $(ev "JSON.stringify(window.__opened)")"
ev '(function(){var u=window.__opened[0];if(!u){window.__csv="(未调用)";return}fetch(u).then(function(r){return r.text().then(function(t){window.__csv=r.status+" | "+r.headers.get("content-type")+" | 行数="+t.trim().split("\n").length+" | 表头="+t.split("\n")[0]})}).catch(function(e){window.__csv="ERR "+e.message})})()' >/dev/null
ab wait 2000
echo "-- CSV 结果: $(ev "window.__csv")"
echo "-- tab 列表:"; ab tab list
ab screenshot --screenshot-dir "$SD" C-导出裁决CSV.png >/dev/null 2>&1
ck "C 导出按钮 enabled"          "$(ab is enabled '#btn-csv')" '^true$'
ck "C 调用了 window.open"        "$(ev "JSON.stringify(window.__opened)")" 'decisions\?format=csv'
ck "C CSV 端点 200 + text/csv"   "$(ev "window.__csv")" '^200 \| text/csv'
ck "C CSV 有表头非空"            "$(ev "window.__csv")" '表头=ts,request_id'
ck "C 导出无未捕获异常"          "$(errs)" '^\[\]$'

echo
echo "===== D) 页内请求流水（状态码） ====="
ev "window.__net.join('\n   ')"
echo
echo "PASS=$PASS FAIL=$FAIL"
echo "-- 全程 page errors: $(pgerr)"
echo "-- 全程运行时异常: $(errs)"
echo "### 补证结束 $(date '+%F %T')"
