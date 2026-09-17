#!/usr/bin/env bash
# 前端演示路径端到端实测（12 步 + 三口径算术断言）。
#
# 必须整段在**单次调用**内跑完：agent-browser 守护进程只在同一次调用内保持存活；
# 不同 CLI 调用之间守护会丢。视口固定 1600x2800（整页可见），避免滚动导致点击坐标漂移；
# 不用 upload（file chooser 会把守护进程搞死），改 fill 模拟粘贴。
#
# 前置：后端 http://127.0.0.1:8000 已启动；agent-browser CLI 可用。
# 产物：截图与表快照写入 $REPO/.e2e-out/（临时目录，非版本库内容）。
#
# ── 相对上一版（.evidence/run_final.sh）修正的两类断言 ──────────────────────────────
# ① 正则双重转义：`[\s\S]*` 是 JS 里的写法，`grep -qE`（POSIX ERE）不支持 `\s`，
#    会退化成「字面反斜杠 + s」，导致 5 条恒假失败。且 ck() 已用 flat() 把实际值压成单行，
#    跨行匹配本就不需要 `[\s\S]` —— 一律改用 `.*`。
# ② 期望值必须锚定**真值**，不能照抄实现输出（本项目要求 test-integrity-anti-gaming）：
#    抖加 = 4 条明细求和 = ¥700.00（4 笔明细 / 7 笔声明）；
#    垫付 = 950 + 300 + 300 + 200 + 500 = ¥2,250.00（5 笔明细 / 7 笔声明）；
#    汇报卡「已确认金额 + 待确认金额」必须等于垫付合计。
set -u
REPO="/c/Users/hu/code/mst"
cd "$REPO" || exit 1
OUT_DIR_REL=".e2e-out"                        # 相对路径：python 脚本在 cwd=REPO 下读写
SD="C:/Users/hu/code/mst/.e2e-out"            # CLI 的 Node 只认 Windows 风格路径
mkdir -p "$OUT_DIR_REL"
PY="C:/Users/hu/.workbuddy/binaries/python/envs/mst/Scripts/python.exe"

PASS=0; FAIL=0
flat(){ printf '%s' "$1" | tr '\n\r\t' '   ' | tr -s ' '; }
ck(){ local a; a=$(flat "$2");
  if printf '%s' "$a" | grep -qE "$3"; then printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1));
  else printf '  [FAIL] %s\n         实际=<%s>\n         期望匹配=/%s/\n' "$1" "$a" "$3"; FAIL=$((FAIL+1)); fi; }
ab(){ timeout 120 agent-browser "$@"; }
sec(){ printf '\n========== %s ==========\n' "$1"; if ! ab eval "1" >/dev/null 2>&1; then printf '!!! 守护进程丢失，中止于 [%s]\n' "$1"; echo "PASS=$PASS FAIL=$FAIL"; exit 9; fi; }
shot(){ timeout 90 agent-browser screenshot "" "$SD/$1" >/dev/null 2>&1; echo "  截图: $OUT_DIR_REL/$1"; }
ev(){ local v; v=$(ab eval "$1" | tr -d '\r\n'); v="${v%\"}"; v="${v#\"}"; [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
pgerr(){ local v; v=$(ab errors | tr -d '\r\n'); [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
cons(){ local v; v=$(ab console | tr -d '\r\n'); [ -z "$v" ] && v="(empty)"; printf '%s' "$v"; }
errs(){ ev "JSON.stringify(window.__errs||[])"; }
gridjson(){ ev 'JSON.stringify(Array.from(document.querySelectorAll("#summary-grid .summary-cell")).map(function(c){return {label:(c.querySelector(".label")||{}).textContent.trim(),value:(c.querySelector(".value")||{}).textContent,sub:(c.querySelector(".sub")||{}).textContent,rows:Array.from(c.querySelectorAll(".caliber-row")).map(function(r){return r.children[0].textContent.trim()+"="+r.children[1].textContent.trim()})}}))'; }
caliber(){ ev '(function(){return Array.from(document.querySelectorAll("#summary-grid .summary-cell")).map(function(c){var m={};c.querySelectorAll(".caliber-row").forEach(function(r){m[r.children[0].textContent.trim()]=r.children[1].textContent.trim()});var v=(c.querySelector(".value")||{}).textContent;return (c.querySelector(".label")||{}).textContent.trim()+"[总额="+v+" 声明="+(m["文本声明额"]||"-")+" 明细求和="+(m["明细求和"]||"-")+" 表内列累计="+(m["表内该列累计"]||"-")+" 未混入="+(v===m["明细求和"]&&v!==m["表内该列累计"])+"]"}).join(" ;; ")})()'; }
# 汇报卡金额自洽：已确认 + 待确认 必须等于 垫付合计
repsum(){ ev '(function(){function g(k){var d=Array.from(document.querySelectorAll("#report-host .report-numbers div"));for(var i=0;i<d.length;i++){var lab=(d[i].querySelector(".label")||{}).textContent||"";if(lab.trim()===k)return ((d[i].querySelector(".value")||{}).textContent||"").trim()}return ""}function num(s){return Number(String(s).replace(/[^0-9.]/g,""))}var c=num(g("已确认金额")),p=num(g("待确认金额")),a=num(g("垫付合计"));return "已确认="+g("已确认金额")+" 待确认="+g("待确认金额")+" 垫付合计="+g("垫付合计")+" 和=垫付合计:"+(Math.abs((c+p)-a)<0.005)})()'; }

echo "### 演示路径实测 $(date '+%F %T')  http://127.0.0.1:8000/"

# =============================================================== STEP 1
sec "STEP 1 · 首屏加载"
ab open http://127.0.0.1:8000/ >/dev/null
ab wait --load load >/dev/null
ab set viewport 1600 2800 >/dev/null
echo "-- 视口 $(ev "innerWidth")x$(ev "innerHeight") / 文档 $(ev "document.documentElement.scrollHeight")"
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- page errors: $(pgerr) / console: $(cons)"
shot 01-STEP1-首屏.png
ck "STEP1 无 page errors"        "$(pgerr)" '^\(empty\)$'
ck "STEP1 无 console 报错"       "$(cons)" '^\(empty\)$'
ck "STEP1 状态栏已登记副本"       "$(ab get text '#input-status')" '已登记账号表测试副本 tbl_copy_[0-9]+'
ck "STEP1 写入按钮初始 disabled"  "$(ab is enabled '#btn-commit')" '^false$'

ev '(function(){window.__errs=[];window.__net=[];window.__opened=[];window.__csv="";window.__clip="";
window.addEventListener("error",function(e){window.__errs.push("error: "+e.message)});
window.addEventListener("unhandledrejection",function(e){window.__errs.push("rejection: "+String(e.reason&&e.reason.message||e.reason))});
var of=window.fetch;window.fetch=function(){var a=arguments,u=String(a[0]);return of.apply(this,a).then(function(r){var c=r.clone();c.text().then(function(t){window.__net.push(r.status+" "+u+" :: "+t.slice(0,80))});return r});};
var ow=window.open;window.open=function(u,n,f){window.__opened.push(String(u));return ow.call(window,u,n,f)};
try{Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:function(t){window.__clip=String(t).slice(0,80);return Promise.resolve()}})}catch(e){window.__clip="(hijack失败)"}
return "ok"})()' >/dev/null

# =============================================================== STEP 2
sec "STEP 2 · 抖加示例 → 解析"
ab click '.tab[data-biz="doujia"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2200
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 总览: $(flat "$(ab get text '#request-meta')")"
echo "-- 闸门: $(ab get text '#gate-note')"
shot 02-STEP2-抖加解析0阻断.png
ck "STEP2 4 条明细"            "$(ab get text '#input-status')" '解析完成：4 条明细'
ck "STEP2 声明总额 700"         "$(ab get text '#request-meta')" '声明总额 ¥700\.00'
ck "STEP2 0 项阻断"            "$(ab get text '#input-status')" '阻断 0 项'
ck "STEP2 写入按钮变可用"        "$(ab is enabled '#btn-commit')" '^true$'
ck "STEP2 闸门提示可写入"        "$(ab get text '#gate-note')" '无未裁决阻断项'
ck "STEP2 无运行时异常"          "$(errs)" '^\[\]$'

# =============================================================== STEP 3
sec "STEP 3 · 写入测试副本 ×2（幂等）"
ab click '#btn-commit' >/dev/null; ab wait 2400
TID=$(ev "document.querySelector('#ledger-host .mono')?document.querySelector('#ledger-host .mono').textContent:''")
echo "-- 副本 id: $TID"
echo "-- 账本: $(flat "$(ab get text '#ledger-host')")"
shot 03a-STEP3-首次写入4条.png
ck "STEP3 首次写入成功 4 条"      "$(ab get text '#ledger-host')" '成功 4 条，跳过 0 条'
"$PY" -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/account-tables/$TID'))['data']
json.dump({r['row_ref']:r for r in d['rows']},open('$OUT_DIR_REL/table-after-commit1.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('  快照A已存（rows=%d）'%len(d['rows']))"
ab click '#btn-commit' >/dev/null; ab wait 2400
echo "-- 二次写入账本: $(flat "$(ab get text '#ledger-host')")"
shot 03b-STEP3-二次写入幂等.png
ck "STEP3 二次写入全部跳过"       "$(ab get text '#ledger-host')" '成功 0 条，跳过 4 条'
ck "STEP3 幂等原因 SKIPPED"      "$(ab get text '#ledger-host')" 'SKIPPED_ALREADY_WRITTEN'
"$PY" -c "
import json,urllib.request
a=json.load(open('$OUT_DIR_REL/table-after-commit1.json',encoding='utf-8'))
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/account-tables/$TID'))['data']
b={r['row_ref']:r for r in d['rows']}
json.dump(b,open('$OUT_DIR_REL/table-after-commit2.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('  [%s] 二次写入后表内容逐格不变（%d 行）'%('PASS' if a==b else 'FAIL',len(b)))"

# =============================================================== STEP 7a
sec "STEP 7a · 当日汇总三口径（抖加）"
echo "-- 网格: $(gridjson)"
echo "-- 口径: $(caliber)"
shot 04-STEP7a-抖加三口径并列.png
ck "STEP7a 三口径并列"           "$(gridjson)" '文本声明额|明细求和|表内该列累计'
# 真值：4 条明细求和 = 700（不是被重复解析放大后的 2100/4500）
ck "STEP7a 抖加合计=¥700.00"      "$(gridjson)" '抖加合计.*¥700\.00'
ck "STEP7a 抖加=4 笔明细/7 笔声明"  "$(gridjson)" '4 笔明细　7 笔声明'
ck "STEP7a 总额=明细求和且≠表内列累计" "$(caliber)" '抖加合计\[总额=.*未混入=true\]'

# =============================================================== STEP 4
sec "STEP 4 · 垫付示例 → 解析（3 阻断 / 闸门关闭）"
ab click '.tab[data-biz="advance"]' >/dev/null
ab click '#btn-sample' >/dev/null
ab click '#btn-parse' >/dev/null
ab wait 2400
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- 闸门: $(ab get text '#gate-note')"
shot 05-STEP4-垫付解析3阻断闸门灰.png
ck "STEP4 解析成功（不再报 douyin_nickname）" "$(ab get text '#input-status')" '解析完成：5 条明细'
ck "STEP4 3 项阻断"             "$(ab get text '#input-status')" '阻断 3 项'
ck "STEP4 写入按钮变灰"          "$(ab is enabled '#btn-commit')" '^false$'
ck "STEP4 闸门提示禁用写入"       "$(ab get text '#gate-note')" '存在 3 项未裁决阻断'
ck "STEP4 无运行时异常"          "$(errs)" '^\[\]$'

# ================================================== 表级异常证据面板（扁平行）
sec "STEP 5a · 表级异常证据面板（修复前整面板崩）"
ab scrollintoview '.queue-item[data-id="anm_09"]' >/dev/null
ab click '.queue-item[data-id="anm_09"]' >/dev/null; ab wait 1200
echo "-- 选中: $(ev "var el=document.querySelector('.queue-item[aria-current=\"true\"]');el?el.getAttribute('data-id'):'(none)'")"
echo "-- 面板标题: $(ev "Array.from(document.querySelectorAll('#evidence .ev-pane h5')).map(function(h){return h.textContent.trim()}).join(' ;; ')")"
echo "-- 台账行: $(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")"
shot 06-STEP5a-表级异常证据面板扁平行.png
ck "STEP5a 右栏=台账行号"        "$(ev "var h=document.querySelectorAll('#evidence .ev-pane h5');h.length>1?h[1].textContent.trim():''")" '账号表 · 第 8 行'
ck "STEP5a 台账行取值渲染(张栋梁)" "$(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")" '张栋梁'
# 修正：命令式 grep(E) 不支持 [\s\S]；且实际值已被 flat() 压成单行 → 用 .*
ck "STEP5a 台账行多列取值非空"    "$(ev "var t=document.querySelector('#evidence .ev-pane:last-child table');t?t.textContent:''")" '2098172078.*100.*200'
ck "STEP5a paint 未中断"         "$(ab get text '#gate-note')" '存在 3 项未裁决阻断'
ck "STEP5a 无运行时异常"         "$(errs)" '^\[\]$'

# =============================================================== STEP 5b
sec "STEP 5 · COUNT_MISMATCH / DATE_ORDER_INVALID → 确认无误"
ab scrollintoview '.queue-item[data-id="anm_02"]' >/dev/null
ab click '.queue-item[data-id="anm_02"]' >/dev/null; ab wait 1000
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2200
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- 已裁决: $(flat "$(ev "document.querySelector('#resolved-box').textContent")")"
ck "STEP5 COUNT_MISMATCH 已裁决"  "$(ev "document.querySelector('#resolved-box').textContent")" 'EXC-01'
ab scrollintoview '.queue-item[data-id="anm_03"]' >/dev/null
ab click '.queue-item[data-id="anm_03"]' >/dev/null; ab wait 1000
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2200
ck "STEP5 DATE_ORDER_INVALID 已裁决" "$(ev "document.querySelector('#resolved-box').textContent")" 'EXC-02'
echo "-- 闸门: $(ab get text '#gate-note')"

# =============================================================== STEP 5c
sec "STEP 5c · MATCH_AMBIGUOUS：确认无误禁用 + 候选行可读 + 修正为目标行"
ab scrollintoview '.queue-item[data-id="anm_01"]' >/dev/null
ab click '.queue-item[data-id="anm_01"]' >/dev/null; ab wait 1300
echo "-- 确认无误 enabled = $(ab is enabled '#actions button[data-action="accept"]')（应 false）"
echo "-- 候选下拉: $(ev "Array.from(document.querySelectorAll('#target option')).map(function(o){return o.value+' => '+o.textContent}).join(' ;; ')")"
shot 07-STEP5c-歧义候选行可读.png
ck "STEP5c 确认无误被禁用"        "$(ab is enabled '#actions button[data-action="accept"]')" '^false$'
ck "STEP5c 候选行可读(第7行)"      "$(ev "document.querySelector('#target').textContent")" '第 7 行 · 葵花夫妇 · 抖音号 LBXXnvzhuang'
ck "STEP5c 候选行可读(第9行空号)"  "$(ev "document.querySelector('#target').textContent")" '第 9 行 · 葵花夫妇 · 抖音号 （空）'
ab select '#target' '7' >/dev/null
echo "-- 已选目标行: $(ab get value '#target')"
ab click '#actions button[data-action="override"]' >/dev/null; ab wait 2600
echo "-- 闸门: $(ab get text '#gate-note')"
echo "-- 未决 P0: $(ev "Array.from(document.querySelectorAll('.queue-item[data-sev=\"P0\"]:not(.is-resolved)')).map(function(li){return li.getAttribute('data-id')}).join(',')")"
shot 08-STEP5d-修正为目标行.png

# =============================================================== STEP 6
sec "STEP 6 · 新出现的 P0（打款人 林老师 vs 木木老师）"
NEWID=$(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?el.getAttribute('data-id'):''})()")
NEWMSG=$(ev "(function(){var el=document.querySelector('.queue-item[data-sev=\"P0\"]:not(.is-resolved)');return el?el.querySelector('.qi-title').textContent:''})()")
echo "-- 新 P0: $NEWID / $NEWMSG"
ck "STEP6 新 P0 为打款人字段冲突"  "$NEWMSG" '林老师.*木木老师'
ab scrollintoview ".queue-item[data-id=\"$NEWID\"]" >/dev/null
ab click ".queue-item[data-id=\"$NEWID\"]" >/dev/null; ab wait 1200
ab click '#actions button[data-action="accept"]' >/dev/null; ab wait 2600
echo "-- 闸门: $(ab get text '#gate-note')"
echo "-- 已裁决: $(flat "$(ev "document.querySelector('#resolved-box').textContent")")"
shot 09-STEP6-阻断归零后可写入.png
ck "STEP6 剩余阻断归零"          "$(ab get text '#gate-note')" '无未裁决阻断项'
ck "STEP6 写入按钮恢复可用"       "$(ab is enabled '#btn-commit')" '^true$'
ck "STEP6 裁决累计"             "$(ev "document.querySelector('#resolved-box').textContent")" '已裁决 [0-9]+ 项'
ck "STEP6 无运行时异常"          "$(errs)" '^\[\]$'

# =============================================================== STEP 7
sec "STEP 7 · 写入垫付 + 当日汇总（垫付口径）"
ab click '#btn-commit' >/dev/null; ab wait 3000
echo "-- 账本: $(flat "$(ab get text '#ledger-host')")"
echo "-- 网格: $(gridjson)"
echo "-- 口径: $(caliber)"
shot 10-STEP7-垫付写入与汇总.png
ck "STEP7 垫付写入 5 条"          "$(ab get text '#ledger-host')" '成功 5 条'
# 真值：950+300+300+200+500 = 2250（5 笔明细 / 7 笔声明），不是重复解析放大后的 9000
ck "STEP7 垫付合计 2250"          "$(gridjson)" '垫付合计.*¥2,250\.00'
ck "STEP7 垫付=5 笔明细/7 笔声明"   "$(gridjson)" '5 笔明细　7 笔声明'
ck "STEP7 垫付总额=明细求和≠表内列累计" "$(caliber)" '垫付合计\[总额=.*未混入=true\]'

# =============================================================== STEP 8
sec "STEP 8 · 生成汇报 + 复制为文本 + 下载 Markdown"
ab click '#btn-report' >/dev/null; ab wait 2400
echo "-- 汇报卡: $(flat "$(ab get text '#report-host')")"
echo "-- 金额自洽: $(repsum)"
shot 11-STEP8-汇报卡.png
ck "STEP8 汇报有标题"            "$(ab get text '#report-host')" '当日汇报 · 2026-09-0'
ck "STEP8 有结论正文"            "$(ab get text '#report-host')" '垫付 ¥[0-9]'
ck "STEP8 已确认/待确认金额并列"   "$(ab get text '#report-host')" '已确认金额.*待确认金额'
ck "STEP8 抖加/垫付合计并列"      "$(ab get text '#report-host')" '抖加合计.*垫付合计'
# 真值自洽：已确认 + 待确认 = 垫付合计
ck "STEP8 已确认+待确认=垫付合计"   "$(repsum)" '和=垫付合计:true'
ck "STEP8 有需决策项"            "$(ab get text '#report-host')" '需决策|需运营|需财务|无待决策项'
ab scrollintoview '#btn-copy-report' >/dev/null
ab click '#btn-copy-report' >/dev/null; ab wait 1200
echo "-- 剪贴板收到: $(ev "window.__clip")"
echo "-- 即时 toast: <$(ab get text '#toast-host')>"
ck "STEP8 复制调到剪贴板 API"      "$(ev "window.__clip")" '当日汇报'
ck "STEP8 复制有成功反馈"         "$(ab get text '#toast-host')" '已复制|复制失败'
ab scrollintoview '#btn-download-report' >/dev/null
ab click '#btn-download-report' >/dev/null; ab wait 1800
echo "-- 下载后 page errors: $(pgerr)"
ck "STEP8 复制/下载无未捕获异常"   "$(errs)" '^\[\]$'

# =============================================================== STEP 10
sec "STEP 10 · 深浅色切换"
ab scrollintoview '#btn-theme' >/dev/null
ab click '#btn-theme' >/dev/null; ab wait 1000
echo "-- theme=$(ev "document.documentElement.getAttribute('data-theme')") label=$(ab get text '#theme-label') 图标=$(ev "document.querySelector('#btn-theme svg')?document.querySelector('#btn-theme svg').getAttribute('data-lucide'):'(无)'")"
echo "-- body 前景/背景=$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")"
shot 12-STEP10-深色模式.png
ck "STEP10 切到 dark"            "$(ev "document.documentElement.getAttribute('data-theme')")" '^dark$'
ck "STEP10 图标跟随= sun"         "$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")" '^sun$'
ck "STEP10 深色=浅字深底"         "$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")" 'rgb\(233, 236, 243\) / rgb\(13, 16, 23\)'
ab click '#btn-theme' >/dev/null; ab wait 1000
echo "-- theme=$(ev "document.documentElement.getAttribute('data-theme')") label=$(ab get text '#theme-label') 图标=$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")"
shot 13-STEP10-浅色模式.png
ck "STEP10 切回 light"           "$(ev "document.documentElement.getAttribute('data-theme')")" '^light$'
ck "STEP10 图标跟随= moon"        "$(ev "document.querySelector('#btn-theme svg').getAttribute('data-lucide')")" '^moon$'
ck "STEP10 浅色=深字浅底"         "$(ev "var s=getComputedStyle(document.body);s.color+' / '+s.backgroundColor")" 'rgb\(20, 23, 31\) / rgb\(247, 248, 251\)'

# =============================================================== STEP 9
sec "STEP 9 · 导出裁决 CSV"
ab scrollintoview '#btn-csv' >/dev/null
echo "-- 按钮 enabled: $(ab is enabled '#btn-csv')"
ab click '#btn-csv' >/dev/null; ab wait 1600
echo "-- window.open: $(ev "JSON.stringify(window.__opened)")"
ev '(function(){var u=window.__opened[0];if(!u){window.__csv="(未调用)";return}fetch(u).then(function(r){return r.text().then(function(t){window.__csv=r.status+" | "+r.headers.get("content-type")+" | 行数="+t.trim().split("\n").length+" | 表头="+t.split("\n")[0]})}).catch(function(e){window.__csv="ERR "+e.message})})()' >/dev/null
ab wait 2200
echo "-- CSV: $(ev "window.__csv")"
shot 14-STEP9-导出裁决CSV.png
ck "STEP9 导出按钮 enabled"       "$(ab is enabled '#btn-csv')" '^true$'
ck "STEP9 调用了 window.open"     "$(ev "JSON.stringify(window.__opened)")" 'decisions\?format=csv'
ck "STEP9 CSV 200 + text/csv"     "$(ev "window.__csv")" '^200 \| text/csv'
ck "STEP9 CSV 有表头非空"         "$(ev "window.__csv")" '表头=ts,request_id'

# =============================================================== STEP 12
sec "STEP 12 · 空输入直接解析（友好提示）"
ab scrollintoview '#btn-clear' >/dev/null
ab click '#btn-clear' >/dev/null; ab wait 1000
echo "-- 清空后状态栏: $(ab get text '#input-status')"
ab click '#btn-parse' >/dev/null; ab wait 1200
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- toast: <$(ab get text '#toast-host')>"
echo "-- page errors: $(pgerr)"
ck "STEP12 友好提示"             "$(ab get text '#input-status')" '尚未输入文本'
ck "STEP12 toast 提示"           "$(ab get text '#toast-host')" '请先粘贴申请文本'
shot 15-STEP12-空输入提示.png
ck "STEP12 不抛异常"             "$(errs)" '^\[\]$'

echo
echo "===== D) 页内请求流水（状态码，reload 前采集） ====="
ev "window.__net.join('\n   ')"
echo "-- 累计运行时异常: $(errs)"

# =============================================================== STEP 11
sec "STEP 11 · 刷新页面（首屏干净）"
ab reload >/dev/null; ab wait --load load >/dev/null; ab wait 2200
echo "-- 状态栏: $(ab get text '#input-status')"
echo "-- page errors: $(pgerr)"
echo "-- 计数区: $(ab get text '#counts')"
shot 16-STEP11-刷新后首屏.png
ck "STEP11 刷新后状态栏登记"      "$(ab get text '#input-status')" '已登记账号表测试副本'
ck "STEP11 刷新后无 page errors"  "$(pgerr)" '^\(empty\)$'

echo
echo "================================================"
echo "最终结果 PASS=$PASS  FAIL=$FAIL"
echo "全程 console: $(cons)"
echo "全程 page errors: $(pgerr)"
echo "### 结束 $(date '+%F %T')"
