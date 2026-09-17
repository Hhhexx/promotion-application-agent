#!/usr/bin/env bash
# 诊断 3：把视口放大到整页可见（消除滚动导致的坐标漂移），验证点击是否可靠
set -u
cd /c/Users/hu/code/mst || exit 1
ab()  { timeout 45 agent-browser "$@"; }
ev()  { local v; v=$(timeout 45 agent-browser eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; printf '%s' "$v"; }

ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab set viewport 1600 2800 >/dev/null
echo "-- 视口高: $(ev "innerHeight")  宽: $(ev "innerWidth")"
echo "-- 文档高: $(ev "document.documentElement.scrollHeight")"

ev '(function(){window.__hits=[];document.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest("button[data-action]");window.__hits.push(e.target.tagName+(b?":action="+b.getAttribute("data-action"):""))},true);return "ok"})()' >/dev/null

ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 1500
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 解析后命中: $(ev "JSON.stringify(window.__hits)")"

ab click '.queue-item[data-id="anm_02"]' >/dev/null
ab wait 500
echo "-- 选中: $(ev "var el=document.querySelector('.queue-item[aria-current=\"true\"]');el?el.getAttribute('data-id'):'(none)'")"
echo "-- 证据首行: $(ev "(document.querySelector('#evidence .ev-claim')||{}).textContent")"

ab network requests --clear >/dev/null 2>&1
ab click '#actions button[data-action="accept"]' >/dev/null
ab wait 2500
echo "-- 点击命中: $(ev "JSON.stringify(window.__hits)")"
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- resolved-box: <$(ab get text '#resolved-box')>"
echo "-- 闸门: <$(ab get text '#gate-note')>"
echo "-- 网络: "; ab network requests

echo
echo "### 继续点 override（歧义项）"
ab click '.queue-item[data-id="anm_01"]' >/dev/null
ab wait 500
ab select '#target' '7' >/dev/null
ab click '#actions button[data-action="override"]' >/dev/null
ab wait 2500
echo "-- 点击命中: $(ev "JSON.stringify(window.__hits)")"
echo "-- 闸门: <$(ab get text '#gate-note')>"
echo "-- resolved-box: <$(ab get text '#resolved-box')>"
echo "-- 队列未决 P0: $(ev "Array.from(document.querySelectorAll('.queue-item[data-sev=\"P0\"]:not(.is-resolved)')).map(function(li){return li.getAttribute('data-id')}).join(',')")"
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- 网络: "; ab network requests
