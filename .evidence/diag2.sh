#!/usr/bin/env bash
# 诊断 2：点击落在 accept 按钮上，但没有任何副作用。判定 handler 是否执行、是否发出请求。
set -u
cd /c/Users/hu/code/mst || exit 1
ab()  { timeout 45 agent-browser "$@"; }
ev()  { local v; v=$(timeout 45 agent-browser eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; printf '%s' "$v"; }

ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 1500

echo "### 探针：事件路径 + 网络"
ev '(function(){window.__hits=[];window.__rej=[];
document.addEventListener("click",function(e){window.__hits.push("capture:"+e.target.tagName+"#"+(e.target.id||""))},true);
var a=document.getElementById("actions");
window.__actionsSame=!!a;
a.addEventListener("click",function(e){var b=e.target.closest("button[data-action]");window.__hits.push("actions-bubble:action="+(b?b.getAttribute("data-action"):"none")+" disabled="+(b?b.disabled:"-"))});
window.addEventListener("unhandledrejection",function(e){window.__rej.push(String(e.reason&&e.reason.message||e.reason))});
return "ok"})()' >/dev/null

ab click '.queue-item[data-id="anm_02"]' >/dev/null
ab wait 400
echo "-- 选中的异常: $(ev "document.querySelector('.queue-item[aria-current=\"true\"]')?document.querySelector('.queue-item[aria-current=\"true\"]').getAttribute('data-id'):'(none)'")"
echo "-- accept 按钮存在: $(ab get count '#actions button[data-action="accept"]')"
echo "-- accept disabled: $(ab is enabled '#actions button[data-action="accept"]')"
echo "-- #op 存在: $(ab get count '#op')   #reason 存在: $(ab get count '#reason')  #target 存在: $(ab get count '#target')"

ab network requests --clear >/dev/null 2>&1
ab click '#actions button[data-action="accept"]' >/dev/null
ab wait 2500
echo "-- 事件命中: $(ev "JSON.stringify(window.__hits)")"
echo "-- 未处理拒绝: $(ev "JSON.stringify(window.__rej)")"
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- resolved-box: <$(ab get text '#resolved-box')>"
echo "-- 网络请求: "; ab network requests
echo "-- 页面错误: "; ab errors

echo
echo "### 对照：同一套委托机制的 #counts 计数按钮"
ab click '#counts .counter[data-sev="P1"]' >/dev/null
ab wait 500
echo "-- 事件命中: $(ev "JSON.stringify(window.__hits)")"

echo
echo "### 对照：直接用 DOM 调用 UI.toast，确认 toast 可用"
ev "UI.toast('探针测试 toast','ok')" >/dev/null
ab wait 300
echo "-- toast: <$(ab get text '#toast-host')>"
