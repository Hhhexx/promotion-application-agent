#!/usr/bin/env bash
# 诊断 4：用页内 fetch 间谍抓解析请求的真实响应
set -u
cd /c/Users/hu/code/mst || exit 1
ab()  { timeout 45 agent-browser "$@"; }
ev()  { local v; v=$(timeout 45 agent-browser eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; printf '%s' "$v"; }

ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab set viewport 1600 2800 >/dev/null

ev '(function(){window.__net=[];
var of=window.fetch;
window.fetch=function(){var a=arguments;var url=String(a[0]);
 return of.apply(this,a).then(function(r){var c=r.clone();
   c.text().then(function(t){window.__net.push("status="+r.status+" url="+url+" body="+t.slice(0,300))});
   return r}).catch(function(e){window.__net.push("FETCH-ERR url="+url+" "+e.message);throw e})};
window.__errs=[];window.addEventListener("error",function(e){window.__errs.push("error:"+e.message)});
window.addEventListener("unhandledrejection",function(e){window.__errs.push("rej:"+String(e.reason&&e.reason.message||e.reason))});
return "ok"})()' >/dev/null

echo "-- 登记完成后 tableId 提示: $(ab get text '#input-status')"
ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2500
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 网络记录:"; ev "window.__net.join('\n@@@\n')"
echo "-- 运行时异常: $(ev "JSON.stringify(window.__errs)")"

echo
echo "### 再点一次解析（同一页面第二次）"
ab click '#btn-parse' >/dev/null
ab wait 2500
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 网络记录:"; ev "window.__net.join('\n@@@\n')"
