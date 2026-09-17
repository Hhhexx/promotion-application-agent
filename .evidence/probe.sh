#!/usr/bin/env bash
# 探针：确认 agent-browser 输出格式，并复现垫付解析崩溃（修复前基线）
set -u
SD="C:/Users/hu/code/mst/.evidence"
ab() { timeout 45 agent-browser "$@"; }

ab open http://127.0.0.1:8000/
ab wait --load load

echo "### 输出格式探针"
echo "-- get url:";                          ab get url
echo "-- get text '#input-status':";         ab get text '#input-status'
echo "-- is enabled '#btn-commit':";         ab is enabled '#btn-commit'
echo "-- get count '.queue-item':";          ab get count '.queue-item'
echo "-- get text '#stepper':";              ab get text '#stepper'
echo "-- get text '#ledger-host':";          ab get text '#ledger-host'
echo "-- eval typeof lucide:";               ab eval "typeof window.lucide"
echo "-- eval theme btn html:";              ab eval "document.querySelector('#btn-theme').innerHTML"

echo
echo "### 安装错误收集器"
ab eval 'window.__errs=[];window.addEventListener("error",function(e){window.__errs.push("error: "+e.message+" @"+(e.filename||"")+":"+e.lineno)});window.addEventListener("unhandledrejection",function(e){window.__errs.push("rejection: "+(e.reason&&e.reason.message||e.reason))});"ok"'

echo
echo "### 复现：垫付示例解析（修复前基线）"
ab click '.tab[data-biz="advance"]'
ab click '#btn-sample'
ab click '#btn-parse'
ab wait 1500
echo "-- 状态栏:";              ab get text '#input-status'
echo "-- 校验总览副标题:";       ab get text '#validation-sub'
echo "-- 计数区:";              ab get text '#counts'
echo "-- 裁决队列条目数:";       ab get count '.queue-item'
echo "-- 动作面板:";            ab get html '#actions'
echo "-- page errors:";         ab errors
echo "-- 运行时收集器:";         ab eval "JSON.stringify(window.__errs)"
echo "-- toast 内容:";          ab get text '#toast-host'
ab screenshot --screenshot-dir "$SD" --full
echo "-- 截图已存"
