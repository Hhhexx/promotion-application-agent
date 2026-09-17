"""端到端冒烟验证入口（对应 Spec v1.0 §12 端到端验证步骤）。

不启动真实端口，直接用 TestClient 走完整链路：
  健康检查 -> 登记账号表 -> 解析抖加（期望 0 个 P0）-> 写表 -> 幂等重放
  -> 解析垫付（期望 3 个 P0）-> 写表被 409 拦截 -> 逐条裁决 -> 写表成功
  -> 跨表写表被拒 -> 非授权列零改动 -> 当日汇总 -> 负责人汇报
  -> 裁决日志导出 -> 错误路径 -> 源表 sha256 全程不变

**零副作用设计**：本脚本**不删除任何文件**，也不往仓库写任何产物。
它把运行期可写目录整体重定向到系统临时目录（`MST_DATA_DIR`），退出后留在 OS 临时区
由系统回收。之所以这么做，是因为递归删除会被运行环境的 safe-delete 守卫拦截
（守卫无法区分"脚本清理自己的输出目录"和"误删用户数据"），
而改路径比硬删文件更可靠、也更符合"可重复运行"的要求。
唯一的例外是仓库内的只读源表 —— 它全程只被读取，且结束时断言 sha256 未变。

模块划分（每个文件都控制在 300 代码行内）：
  e2e_harness.py        断言登记器 + 路径常量 + 源表直读（不走被测代码，避免自证）
  e2e_checks_intake.py  链路「进」：解析 / 校验证据 / 闸门拦截 / 裁决收敛
  e2e_checks_output.py  链路「出」：写表 / 写入核查 / 汇总 / 汇报 / 审计导出
  e2e_smoke.py          本文件：隔离环境 + 按序驱动 + 汇总退出码

用法：
  <venv>/python.exe tools/e2e_smoke.py
退出码 0 = 全绿；1 = 存在断言失败。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在 import app.* 之前生效：app.core.config 在导入期就把 DATA_DIR 定下来了。
_SANDBOX = Path(tempfile.mkdtemp(prefix="mst-e2e-"))
os.environ["MST_DATA_DIR"] = str(_SANDBOX)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from tools.e2e_checks_intake import (  # noqa: E402
    check_advance_parse,
    check_bad_resolutions,
    check_doujia_commit,
    check_doujia_parse,
    check_gate_blocks,
    check_health,
    check_idempotent_replay,
    check_register_table,
    check_resolution_convergence,
)
from tools.e2e_checks_output import (  # noqa: E402
    check_audit_export,
    check_commit_unlocked,
    check_cross_table_guard,
    check_error_paths,
    check_report,
    check_summary,
    check_written_content,
)
from tools.e2e_harness import SOURCE, Checker, Ctx, sha256  # noqa: E402


def main() -> int:
    ck = Checker()
    ctx = Ctx(source_hash_before=sha256(SOURCE))
    print(f"隔离数据目录：{_SANDBOX}（仓库内 data/ 不会被写入）")

    with TestClient(app) as client:
        check_health(client, ck)
        check_register_table(client, ck, ctx)
        check_doujia_parse(client, ck, ctx)
        check_doujia_commit(client, ck, ctx)
        check_idempotent_replay(client, ck, ctx)
        check_advance_parse(client, ck, ctx)
        check_gate_blocks(client, ck, ctx)
        ambiguous = check_bad_resolutions(client, ck, ctx)
        check_resolution_convergence(client, ck, ctx, ambiguous)
        check_commit_unlocked(client, ck, ctx)
        check_cross_table_guard(client, ck, ctx)
        check_written_content(client, ck, ctx)
        check_summary(client, ck, ctx)
        check_report(client, ck, ctx)
        check_audit_export(client, ck, ctx)
        check_error_paths(client, ck, ctx)

    return ck.report()


if __name__ == "__main__":
    raise SystemExit(main())
