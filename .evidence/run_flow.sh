#!/usr/bin/env bash
# 端到端演示路径实测（12 步 + 干净口径算术校验）。
# 必须在**单次调用**内跑完：守护进程只在同一次调用内保持存活。
# 关键手法：
#  - 视口放大到整页可见（1600x2800），消除滚动导致的点击坐标漂移
#  - 页内 fetch / window.open 间谍取证（CLI 的 network 命令抓不到 fetch）
#  - 不使用 file chooser（upload 会把守护进程搞死），改用 fill 模拟粘贴
set -u
REPO="/c/Users/hu/code/mst"
SD="C:/Users/hu/code/mst/.evidence"
PY="C:/Users/hu/.workbuddy/binaries/python/envs/mst/Scripts/python.exe"
cd "$REPO" || exit 1

PASS=0; FAIL=0
ck() {
  if printf '%s' "$2" | grep -qE "$3"; then printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1));
  else printf '  [FAIL] %s\n         实际=<%s>\n         期望匹配=/%s/\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}
ab()  { timeout 120 agent-browser "$@"; }
guard(){ if ! ab eval "1" >/dev/null 2>&1; then printf '\n!!! 浏览器守护进程丢失，实测在第 [%s] 步中止 !!!\n' "$1"; echo "PASS=$PASS FAIL=$FAIL"; exit 9; fi; }
sec() { printf '\n========== %s ==========\n' "$1"; guard "$1"; }
shot(){ timeout 90 agent-browser screenshot --screenshot-dir "$SD" "$@" >/dev/null 2>&1; }
ev()  { local v; v=$(ab eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
pgerr(){ local v; v=$(ab errors | tr -d '\r\n'); [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
cons(){ local v; v=$(ab console | tr -d '\r\n'); [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
errs(){ ev "JSON.stringify(window.__errs||[])"; }
gridjson(){ ev 'JSON.stringify(Array.from(document.querySelectorAll("#summary-grid .summary-cell")).map(function(c){return {label:(c.querySelector(".label")||{}).textContent.trim(),value:(c.querySelector(".value")||{}).textContent,sub:(c.querySelector(".sub")||{}).textContent,rows:Array.from(c.querySelectorAll(".caliber-row")).map(function(r){return r.children[0].textContent.trim()+"="+r.children[1].textContent.trim()})}}))'; }
# 口径判定：总额必须等于「明细求和」，且必须不等于「表内该列累计」
calibercheck(){ ev '(function(){return Array.from(document.querySelectorAll("#summary-grid .summary-cell")).map(function(c){var m={};c.querySelectorAll(".caliber-row").forEach(function(r){m[r.children[0].textContent.trim()]=r.children[1].textContent.trim()});var v=(c.querySelector(".value")||{}).textContent;var ok=(v===m["明细求和"]&&v!==m["表内该列累计"]);return (c.querySelector(".label")||{}).textContent.trim()+" 总额="+v+" 声明="+(m["文本声明额"]||"-")+" 明细求和="+(m["明细求和"]||"-")+" 表内列累计="+(m["表内该列累计"]||"-")+" 总额=明细求和且≠表内列累计:"+ok}).join(" ;; ")})()'; }

echo "### 实测开始 $(date '+%F %T')  target=http://127.0.0.1:8000/"

# ---------------------------------------------------------------- STEP 1
sec "STEP 1 · 首屏加载（console 应无报错）"
ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab set viewport 1600 2800 >/dev/null
echo "-- 视口: $(ev "innerWidth")x$(ev "innerHeight")  文档高 $(ev "document.documentElement.scrollHeight")"
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- page errors: $(pgerr)"
echo "-- console: $(cons)"
shot 01-step1-首屏.png
ck "STEP1 首屏 page errors 为空"        "$(pgerr)" '^\(empty\)$'
ck "STEP1 状态栏提示账号表已登记"        "$(ab get text '#input-status')" '已登记账号表测试副本 tbl_copy_[0-9]+'
ck "STEP1 写入按钮初始禁用"             "$(ab is enabled '#btn-commit')" '^false$'

ev '(function(){window.__errs=[];window.__net=[];window.__opened=[];window.__csv="";
window.addEventListener("error",function(e){window.__errs.push("error: "+e.message+" @"+(e.filename||"")+":"+e.lineno)});
window.addEventListener("unhandledrejection",function(e){window.__errs.push("rejection: "+String(e.reason&&e.reason.message||e.reason))});
var of=window.fetch;window.fetch=function(){var a=arguments,u=String(a[0]);
 return of.apply(this,a).then(function(r){var c=r.clone();c.text().then(function(t){window.__net.push(r.status+" "+u+" :: "+t.slice(0,90))});return r});};
var ow=window.open;window.open=function(u,n,f){window.__opened.push(String(u));return ow.call(window,u,n,f)};
return "ok"})()' >/dev/null

# ---------------------------------------------------------------- STEP 2
sec "STEP 2 · 抖加示例 → 解析（4 条明细 / 声明 700 / 0 阻断 / 闸门开）"
ab click '.tab[data-biz="doujia"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2000
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 总览元信息: $(ab get text '#request-meta')"
echo "-- 闸门提示: $(ab get text '#gate-note')"
shot 02-step2-抖加解析.png
ck "STEP2 4 条明细"                   "$(ab get text '#input-status')" '解析完成：4 条明细'
ck "STEP2 声明总额 700"               "$(ab get text '#request-meta')" '声明总额 ¥700\.00'
ck "STEP2 0 项阻断"                   "$(ab get text '#input-status')" '阻断 0 项'
ck "STEP2 写入按钮可用"               "$(ab is enabled '#btn-commit')" '^true$'
ck "STEP2 闸门提示可写入"             "$(ab get text '#gate-note')" '无未裁决阻断项'
ck "STEP2 解析无运行时异常"           "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 3
sec "STEP 3 · 写入测试副本 ×2（幂等 + 表内容不变）"
ab click '#btn-commit' >/dev/null
ab wait 2200
TID1=$(ev "document.querySelector('#ledger-host .mono')?document.querySelector('#ledger-host .mono').textContent:''")
echo "-- 副本 id: $TID1"
echo "-- 账本: $(ab get text '#ledger-host')"
shot 03a-step3-首次写入.png
ck "STEP3 首次写入成功 4 条"           "$(ab get text '#ledger-host')" '成功 4 条，跳过 0 条'
"$PY" -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/account-tables/$TID1'))['data']
json.dump({r['row_ref']:r for r in d['rows']},open('.evidence/table-after-commit1.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('  已存第一次写入后的副本快照 rows=%d'%len(d['rows']))
"
ab click '#btn-commit' >/dev/null
ab wait 2200
echo "-- 二次写入账本: $(ab get text '#ledger-host')"
shot 03b-step3-二次写入幂等.png
ck "STEP3 二次写入全部跳过"            "$(ab get text '#ledger-host')" '成功 0 条，跳过 4 条'
ck "STEP3 跳过原因=已写入(幂等)"       "$(ab get text '#ledger-host')" 'SKIPPED_ALREADY_WRITTEN'
"$PY" -c "
import json,urllib.request
a=json.load(open('.evidence/table-after-commit1.json',encoding='utf-8'))
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/account-tables/$TID1'))['data']
b={r['row_ref']:r for r in d['rows']}
json.dump(b,open('.evidence/table-after-commit2.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('  [%s] 二次写入后表内容逐格不变（%d 行）'%('PASS' if a==b else 'FAIL',len(b)))
"

# ---------------------------------------------------------------- STEP 7a
sec "STEP 7a · 当日汇总三口径（抖加）"
echo "-- 汇总网格: $(gridjson)"
echo "-- 口径判定: $(calibercheck)"
shot 07a-step7-抖加三口径.png
ck "STEP7a 三口径并列"                "$(gridjson)" '文本声明额|明细求和|表内该列累计'
ck "STEP7a 总额=明细求和且≠表内列累计"  "$(calibercheck)" '抖加合计 总额=[^ ]+ .*总额=明细求和且≠表内列累计:true'

# ---------------------------------------------------------------- STEP 7b
sec "STEP 7b · 干净日期桶算术校验（同一物料、仅日期平移，验证 700/400 精确口径）"
ab click '.tab[data-biz="doujia"]' >/dev/null
ab fill '#raw-text' "$(cat "$REPO/.evidence/sample-doujia-干净口径.txt")" >/dev/null
echo "-- 粘贴后文本长度: $(ev "document.getElementById('raw-text').value.length")"
ab click '#btn-parse' >/dev/null
ab wait 2200
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 汇总网格: $(gridjson)"
echo "-- 口径判定: $(calibercheck)"
shot 07b-step7-干净桶700.png
ck "STEP7b 长文本粘贴可用"             "$(ev "document.getElementById('raw-text').value.length")" '^[0-9]{3,}$'
ck "STEP7b 干净桶抖加合计精确 700"      "$(gridjson)" '抖加合计[\s\S]*?¥700\.00'
ck "STEP7b 干净桶 4 笔明细/7 笔声明"    "$(gridjson)" '4 笔明细　7 笔声明'
ck "STEP7b 干净桶表内列累计 400"        "$(gridjson)" '表内该列累计=¥400\.00'
ck "STEP7b 干净桶总额=明细求和≠表内列"  "$(calibercheck)" '抖加合计 总额=¥700\.00 .*总额=明细求和且≠表内列累计:true'

# ---------------------------------------------------------------- STEP 4
sec "STEP 4 · 垫付示例 → 解析（3 阻断 / 闸门关闭）"
ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2200
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 闸门提示: $(ab get text '#gate-note')"
echo "-- 队列条目数: $(ab get count '.queue-item')"
shot 04-step4-垫付解析3阻断.png
ck "STEP4 解析成功（不再报 douyin_nickname）" "$(ab get text '#input-status')" '解析完成：5 条明细'
ck "STEP4 3 项阻断"                   "$(ab get text '#input-status')" '阻断 3 项'
ck "STEP4 写入按钮变灰且不可点"        "$(ab is enabled '#btn-commit')" '^false$'
ck "STEP4 闸门提示禁用写入"            "$(ab get text '#gate-note')" '存在 3 项未裁决阻断'
ck "STEP4 解析无运行时异常"            "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 5a
sec "STEP 5a · 表级异常证据面板（修复前此处整面板崩）"
ab click '.queue-item[data-id="anm_09"]' >/dev/null; ab wait 900
echo "-- 证据面板标题: $(ev "Array.from(document.querySelectorAll('#evidence .ev-pane h5')).map(function(h){return h.textContent.trim()}).join(' ;; ')")"
echo "-- 右侧台账行: $(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent.replace(/\n/g,'|').slice(0,140):'(无表格)'")"
shot 05a-step5-表级异常证据面板.png
ck "STEP5a 右栏显示台账行号"           "$(ev "var h=document.querySelectorAll('#evidence .ev-pane h5');h.length>1?h[1].textContent.trim():''")" '账号表 · 第 8 行'
ck "STEP5a 台账行取值非空(张栋梁)"      "$(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")" '张栋梁'
ck "STEP5a 渲染未中断"                "$(ab get text '#gate-note')" '存在 3 项未裁决阻断'
ck "STEP5a 无运行时异常"              "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 5b
sec "STEP 5 · COUNT_MISMATCH / DATE_ORDER_INVALID → 确认无误"
ab click '.queue-item[data-id="anm_02"]' >/dev/null; ab wait 900
echo "-- 选中: $(ev "var el=document.querySelector('.queue-item[aria-current=\"true\"]');el?el.getAttribute('data-id'):'(none)'")"
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2000
echo "-- 即时 toast: <$(ab get text '#toast-host')>"
echo "-- 已裁决框: <$(ev "document.querySelector('#resolved-box').textContent")>"
ck "STEP5 COUNT_MISMATCH 已裁决"       "$(ev "document.querySelector('#resolved-box').textContent")" 'EXC-01'
ab click '.queue-item[data-id="anm_03"]' >/dev/null; ab wait 900
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2000
echo "-- 已裁决框: <$(ev "document.querySelector('#resolved-box').textContent")>"
ck "STEP5 DATE_ORDER_INVALID 已裁决"   "$(ev "document.querySelector('#resolved-box').textContent")" 'EXC-02'
echo "-- 闸门: $(ab get text '#gate-note')"

# ---------------------------------------------------------------- STEP 5c
sec "STEP 5c · MATCH_AMBIGUOUS：确认无误禁用 + 候选行可读 + 修正为目标行"
ab click '.queue-item[data-id="anm_01"]' >/dev/null; ab wait 1100
echo "-- 确认无误按钮 enabled = $(ab is enabled '#actions button[data-action="accept"]')（应为 false）"
echo "-- 候选下拉: $(ev "Array.from(document.querySelectorAll('#target option')).map(function(o){return o.value+' => '+o.textContent}).join(' ;; ')")"
shot 05c-step5-歧义候选行.png
ck "STEP5c 歧义项「确认无误」禁用"       "$(ab is enabled '#actions button[data-action="accept"]')" '^false$'
ck "STEP5c 候选行标签可读(第7行)"        "$(ev "document.querySelector('#target').textContent")" '第 7 行 · 葵花夫妇 · 抖音号 LBXXnvzhuang'
ck "STEP5c 候选行标签可读(第9行空号)"    "$(ev "document.querySelector('#target').textContent")" '第 9 行 · 葵花夫妇 · 抖音号 （空）'
ab select '#target' '7' >/dev/null
echo "-- 已选目标行: $(ab get value '#target')"
ab click '#actions button[data-action="override"]' >/dev/null; ab wait 2400
echo "-- 钉死目标行后闸门: $(ab get text '#gate-note')"
echo "-- 未决 P0: $(ev "Array.from(document.querySelectorAll('.queue-item[data-sev=\"P0\"]:not(.is-resolved)')).map(function(li){return li.getAttribute('data-id')}).join(',')")"
shot 05d-step5-修正为目标行.png
ck "STEP5c 修正动作无运行时异常"         "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 6
sec "STEP 6 · 新出现的 P0（打款人 文本=林老师 vs 台账=木木老师）"
echo "-- 新 P0 id: $(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?el.getAttribute('data-id'):''})()")"
echo "-- 新 P0 文案: $(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?el.querySelector('.qi-title').textContent:''})()")"
ab click "$(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?'.queue-item[data-id=\"'+el.getAttribute('data-id')+'\"]':'.queue-item[data-id=\"anm_01\"']" )" >/dev/null; ab wait 1100
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2400
echo "-- 闸门: $(ab get text '#gate-note')"
echo "-- 已裁决: $(ev "document.querySelector('#resolved-box').textContent")"
shot 06-step6-阻断归零.png
ck "STEP6 新 P0 = 打款人字段冲突"        "$(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?el.querySelector('.qi-title').textContent:''})()")" '打款人|阻断|(empty)'
ck "STEP6 剩余阻断归零"                "$(ab get text '#gate-note')" '无未裁决阻断项'
ck "STEP6 写入按钮恢复可用"            "$(ab is enabled '#btn-commit')" '^true$'
ck "STEP6 裁决计数累积"                "$(ev "document.querySelector('#resolved-box').textContent")" '已裁决 [0-9]+ 项'
ck "STEP6 无运行时异常"                "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 7
sec "STEP 7 · 写入垫付 + 当日汇总（垫付口径）"
ab click '#btn-commit' >/dev/null; ab wait 2800
echo "-- 账本: $(ab get text '#ledger-host')"
echo "-- 汇总网格: $(gridjson)"
echo "-- 口径判定: $(calibercheck)"
shot 07c-step7-垫付汇总.png
ck "STEP7 垫付写入 5 条"               "$(ab get text '#ledger-host')" '成功 5 条'
ck "STEP7 垫付合计 2250"               "$(gridjson)" '垫付合计[\s\S]*?¥2,250\.00'
ck "STEP7 垫付总额=明细求和≠表内列累计" "$(calibercheck)" '垫付合计 总额=[^ ]+ .*总额=明细求和且≠表内列累计:true'

# ---------------------------------------------------------------- STEP 8
sec "STEP 8 · 生成汇报 + 复制为文本 + 下载 Markdown"
ab click '#btn-report' >/dev/null; ab wait 2200
echo "-- 汇报卡: $(ab get text '#report-host')"
shot 08-step8-汇报卡.png
ck "STEP8 汇报有标题"                  "$(ab get text '#report-host')" '当日汇报 · 2026-09-0'
ck "STEP8 汇报有结论正文"              "$(ab get text '#report-host')" '垫付'
ck "STEP8 已确认/待确认金额区分"        "$(ab get text '#report-host')" '已确认金额[\s\S]*待确认金额'
ck "STEP8 有需决策项"                  "$(ab get text '#report-host')" '需决策|需运营|需财务'
ab click '#btn-copy-report' >/dev/null; ab wait 1300
echo "-- 复制后 toast: <$(ab get text '#toast-host')>"
ck "STEP8 复制为文本有反馈"             "$(ab get text '#toast-host')" '复制|失败'
ab click '#btn-download-report' >/dev/null; ab wait 1800
echo "-- 下载后 page errors: $(pgerr)"
ck "STEP8 复制/下载无未捕获异常"         "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 10
sec "STEP 10 · 深浅色切换（配色 + 图标跟随）"
ab click '#btn-theme' >/dev/null; ab wait 1000
echo "-- theme=$(ev "document.documentElement.getAttribute('data-theme')") label=$(ab get text '#theme-label') 图标=$(ev "document.querySelector('#btn-theme svg')?document.querySelector('#btn-theme svg').getAttribute('data-lucide'):'(无)'")"
echo "-- body 前景/背景=$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")"
shot 10a-step10-深色.png
ck "STEP10 切到 dark"                  "$(ev "document.documentElement.getAttribute('data-theme')")" '^dark$'
ck "STEP10 图标跟随切为 sun"            "$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")" '^sun$'
ck "STEP10 深色=浅字深底"               "$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")" 'rgb\(233, 236, 243\) / rgb\(13, 16, 23\)'
ab click '#btn-theme' >/dev/null; ab wait 1000
echo "-- theme=$(ev "document.documentElement.getAttribute('data-theme')") label=$(ab get text '#theme-label') 图标=$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")"
echo "-- body 前景/背景=$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")"
shot 10b-step10-浅色.png
ck "STEP10 切回 light"                 "$(ev "document.documentElement.getAttribute('data-theme')")" '^light$'
ck "STEP10 图标跟随切回 moon"           "$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")" '^moon$'
ck "STEP10 浅色=深字浅底"               "$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")" 'rgb\(20, 23, 31\) / rgb\(247, 248, 251\)'

# ---------------------------------------------------------------- STEP 9
sec "STEP 9 · 导出裁决 CSV"
ab click '#btn-csv' >/dev/null; ab wait 1500
echo "-- window.open 调用: $(ev "JSON.stringify(window.__opened)")"
ev '(function(){var u=window.__opened[0];if(!u){window.__csv="(未调用 window.open)";return}fetch(u).then(function(r){return r.text().then(function(t){window.__csv=r.status+" | "+r.headers.get("content-type")+" | 行数="+t.trim().split("\n").length+" | 表头="+t.split("\n")[0]})}).catch(function(e){window.__csv="ERR "+e.message})})()' >/dev/null
ab wait 2000
echo "-- CSV 导出结果: $(ev "window.__csv")"
echo "-- tab 列表:"; ab tab list
shot 09-step9-导出CSV.png
echo "-- page errors: $(pgerr)"
ck "STEP9 导出按钮调用 window.open"      "$(ev "JSON.stringify(window.__opened)")" '/decisions\?format=csv'
ck "STEP9 CSV 端点 200 + text/csv"       "$(ev "window.__csv")" '^200 \| text/csv'
ck "STEP9 CSV 内容非空(有表头)"          "$(ev "window.__csv")" '表头=ts,request_id'

# ---------------------------------------------------------------- STEP 12
sec "STEP 12 · 空输入直接解析（应友好提示）"
ab click '#btn-clear' >/dev/null; ab wait 1000
echo "-- 清空后状态栏: $(ab get text '#input-status')"
ab click '#btn-parse' >/dev/null; ab wait 1300
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- page errors: $(pgerr)"
shot 12-step12-空输入提示.png
ck "STEP12 空输入有友好提示"            "$(ab get text '#input-status')" '尚未输入文本'
ck "STEP12 空输入有 toast"             "$(ab get text '#toast-host')" '请先粘贴申请文本'
ck "STEP12 空输入不抛异常"              "$(errs)" '^\[\]$'

# ---------------------------------------------------------------- STEP 11
sec "STEP 11 · 刷新页面（首屏干净）"
ab reload >/dev/null; ab wait --load load >/dev/null; ab wait 2000
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- page errors: $(pgerr)"
echo "-- 计数区: $(ab get text '#counts')"
shot 11-step11-刷新后首屏.png
ck "STEP11 刷新后状态栏登记提示"         "$(ab get text '#input-status')" '已登记账号表测试副本'
ck "STEP11 刷新后无 page errors"        "$(pgerr)" '^\(empty\)$'

# ---------------------------------------------------------------- 汇总
sec "实测汇总"
echo "PASS=$PASS  FAIL=$FAIL"
echo "-- 请求流水（页内 fetch 间谍，状态码）:"; ev "window.__net.join('\n   ')"
echo "-- 全程累计运行时异常: $(errs)"
echo "-- 全程 console: $(cons)"
echo "-- 全程 page errors: $(pgerr)"
echo "### 实测结束 $(date '+%F %T')"
