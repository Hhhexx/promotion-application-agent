"""由题目物料生成《你是我的仰望》推广账号表 xlsx。

题目只提供了 Markdown 表格，本脚本把它还原为可被 openpyxl 读写的 xlsx，
并**如实保留物料中的异常特征**（不得顺手"修好"，它们是校验规则的断言基线）：

* 第 11 行整行空行（含主键昵称与抖音号均为空）
* 「沙雕小子」行的「备注」被底色高亮但内容为空
* 发布日期三种书写风格混杂：`4.9` / `4.10`（无年份）与 `2026/8/21`（含年份）
* 「葵花夫妇」出现两行，其中一行抖音号为空
* 「马马马叔」是否打款=是，但打款人为空
* 「张栋梁」抖加 200 > 报价 100
* 「@@陈三」昵称含装饰字符

用法：``python tools/make_source_table.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "你是我的仰望-推广账号表.xlsx"
FIXTURE_COPY = ROOT / "tests" / "fixtures" / "推广账号表-测试夹具.xlsx"

HEADERS = [
    "类型",
    "抖音昵称",
    "抖音号",
    "报价",
    "抖加",
    "抖加支付人",
    "是否打款",
    "打款人",
    "打款日期",
    "发布日期",
    "是否接单",
    "审核结果",
    "备注",
]

#: 逐值照抄物料。None 表示空单元格；字符串保留原始书写，不做归一。
ROWS: list[list[object]] = [
    ["音乐号", "初秋", "34579726153", 400, None, None, None, None, None, "4.9", "是", "过", None],
    ["剧情演绎", "艳红", "47657512581", 700, None, None, None, None, None, "4.10", "是", "过", None],
    ["剧情演绎", "唐山第一女泵工", "linwei1314_99", 700, None, None, "是", "木木老师", "2026/8/21", "4.10", "是", "过", None],
    ["剧情演绎", "戎大姨", "1082012992", 800, None, None, None, None, None, "4.10", "是", "过", None],
    ["剧情演绎", "高高", "dq77889966", 1000, 100, "李老师", None, None, None, "4.10", "是", "过", None],
    ["剧情演绎", "葵花夫妇", "LBXXnvzhuang", 1000, None, None, "是", "木木老师", None, "4.10", "是", "过", None],
    ["剧情演绎", "张栋梁", "2098172078", 100, 200, "爆火音乐", "是", "木木老师", "2026/8/17", "4.10", "是", "过", None],
    ["剧情演绎", "葵花夫妇", None, 100, 100, "爆火音乐", None, None, None, "4.10", "是", "过", None],
    ["剧情演绎", "@@陈三", "chensan35195", 700, None, None, None, None, None, None, None, None, None],
    ["沙雕动画", "君君动画（虾仁）", "137844565", 600, None, None, None, None, None, None, "否", None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None],
    ["沙雕动画", "沙雕小子", "shadiaoxiaozil68", 500, None, None, None, None, None, None, "否", None, None],
    ["沙雕动画", "有点雕", "3060906819", 200, None, None, None, None, None, None, "是", "过", None],
    ["陪听号", "一份大喜条", "52056779588", 300, None, None, None, None, None, None, None, None, None],
    ["陪听号", "墨墨", "64715411597", 400, None, None, None, None, None, None, "是", "过", None],
    ["陪听号", "马马马叔", "95739107662", 400, None, None, "是", None, None, None, "是", "过", None],
]

#: 「备注被高亮标记但为空」的行号（Excel 物理行号：表头占第 1 行，故 沙雕小子 为第 13 行）。
HIGHLIGHTED_EMPTY_REMARK_ROWS = [13]

WIDTHS = [10, 18, 18, 8, 8, 12, 10, 10, 12, 10, 10, 10, 24]


def build() -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "推广账号表"

    header_fill = PatternFill("solid", fgColor="E8EBF2")
    for col, name in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col)
        cell.value = name
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = WIDTHS[col - 1]

    for idx, row in enumerate(ROWS, start=2):
        for col, value in enumerate(row, start=1):
            ws.cell(row=idx, column=col).value = value

    mark_fill = PatternFill("solid", fgColor="FFF2CC")
    for row_no in HIGHLIGHTED_EMPTY_REMARK_ROWS:
        ws.cell(row=row_no, column=len(HEADERS)).fill = mark_fill

    ws.freeze_panes = "A2"
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    wb.save(TARGET)
    FIXTURE_COPY.parent.mkdir(parents=True, exist_ok=True)
    wb.save(FIXTURE_COPY)
    return TARGET


if __name__ == "__main__":
    path = build()
    print(f"已生成源表：{path}")
    print(f"已生成测试夹具：{FIXTURE_COPY}")
    sys.exit(0)
