#!/usr/bin/env bash
# 诊断：为什么「裁决动作」等按钮的坐标点击没触发 handler？
# 检查 toast-host / topbar 是否遮挡，以及 fill 对 date input 是否生效
set -u
REPO="/c/Users/hu/code/mst"
cd "$REPO" || exit 1
ab()  { timeout 45 agent-browser "$@"; }
ev()  { local v; v=$(timeout 45 agent-browser eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; printf '%s' "$v"; }

ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ev 'window.__errs=[];window.addEventListener("error",function(e){window.__errs.push("error: "+e.message)});"ok"' >/dev/null

ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 400

echo "### 覆盖面元素自身几何"
echo "-- toast-host style: $(ev "var s=getComputedStyle(document.getElementById('toast-host'));['pos='+s.position,'z='+s.zIndex,'pe='+s.pointerEvents,'top='+s.top,'right='+s.right,'bottom='+s.bottom,'left='+s.left].join(' ')")"
echo "-- toast-host rect:  $(ev "JSON.stringify(document.getElementById('toast-host').getBoundingClientRect())")"
echo "-- 现存 toast 数: $(ab get count '#toast-host .toast')"
echo "-- toast rect:       $(ev "var t=document.querySelector('#toast-host .toast');t?JSON.stringify(t.getBoundingClientRect()):'(none)'")"
echo "-- topbar style: $(ev "var s=getComputedStyle(document.querySelector('.topbar'));['pos='+s.position,'z='+s.zIndex].join(' ')")"
echo "-- topbar rect:  $(ev "JSON.stringify(document.querySelector('.topbar').getBoundingClientRect())")"

echo
echo "### 点击动作按钮前的落点检查"
ab click '.queue-item[data-id="anm_02"]' >/dev/null
ab scrollintoview '#actions button[data-action="accept"]' >/dev/null
echo "-- accept 按钮 rect: $(ev "JSON.stringify(document.querySelector('#actions button[data-action=\"accept\"]').getBoundingClientRect())")"
echo "-- 视口/滚动: $(ev "JSON.stringify({vh:innerHeight,scrollY:window.scrollY})")"
echo "-- 中心点落点元素: $(ev "(function(){var b=document.querySelector('#actions button[data-action=\"accept\"]');var r=b.getBoundingClientRect();var cx=r.left+r.width/2,cy=r.top+r.height/2;var el=document.elementFromPoint(cx,cy);return el?el.tagName+'#'+el.id+'.'+(el.className&&el.className.toString().slice(0,50)):'(null)'})()")"
echo "-- actions 容器 rect: $(ev "JSON.stringify(document.getElementById('actions').getBoundingClientRect())")"

echo
echo "### 真正点一次 accept，立刻看反馈"
ab click '#actions button[data-action="accept"]' >/dev/null
ab wait 700
echo "-- toast(立刻): <$(ab get text '#toast-host')>"
echo "-- resolved-box: <$(ab get text '#resolved-box')>"
echo "-- 闸门: <$(ab get text '#gate-note')>"

echo
echo "### date input fill 行为"
echo "-- 当前 value: <$(ab get value '#summary-date')>"
ab fill '#summary-date' '2026-09-02' >/dev/null
echo "-- fill 后 value: <$(ab get value '#summary-date')>"

echo
echo "### 用 DOM 派发 click 做对照（排除坐标问题）"
ev "(function(){var b=document.querySelector('#actions button[data-action=\"accept\"]');if(!b)return 'no-btn';b.dispatchEvent(new MouseEvent('click',{bubbles:true}));return 'dispatched'})()"
ab wait 1500
echo "-- DOM 派发后 toast: <$(ab get text '#toast-host')>"
echo "-- DOM 派发后 resolved-box: <$(ab get text '#resolved-box')>"
echo "-- DOM 派发后 闸门: <$(ab get text '#gate-note')>"
echo "-- 运行时异常: $(ev "JSON.stringify(window.__errs)")"
