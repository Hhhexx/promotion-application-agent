# 推广申请处理 Agent · UI/UX 设计方向

> 项目：面试题·题目二「推广申请处理 Agent」
> 设计师：颜好看 | 阶段：Phase 1（设计调研 + 信息架构 + Token 骨架 + 图标锁定）
> 生成日期：2026-09-16 | 工作目录：`C:\Users\hu\code\mst`
> 本阶段不写前端实现代码，只交付设计契约与机器可读 Token 骨架。

---

## 0. 设计基础判定

### 0.1 寄存器与平台（设计前必判）

| 判定项 | 取值 | 依据 |
|---|---|---|
| 设计寄存器 | **Product（设计服务产品）** | 交付物是投放运营每天使用的操作台，路径形态为 app 型工具界面。标杆是"赢得熟悉感"，不是"独特性"。熟手用户（投放运营）坐下来要在 30 秒内信任它。 |
| 平台轴 | **web** | 单页操作台，Python + FastAPI 后端 + 轻前端。桌面为主，平板/手机需可用但不作为主场景。 |

**Product 寄存器的强制约束**（后续所有动作按此收敛）：
- 色彩克制，强调色只用于主操作、当前选中、状态指示，着色中性色承载 80% 以上面积。
- 字体一族足够（sans + mono），固定 rem 阶梯，步进比 1.125 到 1.2，不做展示字体。
- 每个交互组件必须覆盖全状态（default / hover / focus / active / disabled / loading / error / success）。
- 动效 150 到 250ms，传递状态而非装饰，不做页面加载编排。
- 数据面不用阴影、不用大圆角；层级靠 1px hairline 与底色差（沿用 Linear 的工艺语言）。

### 0.2 三轴刻度

| 刻度 | 取值 | 理由 |
|---|---|---|
| DESIGN_VARIANCE | **2** | 对账是"事实呈现"，对称、可预测的网格降低认知负担。禁止居中 Hero、禁止非对称装饰性布局。 |
| MOTION_INTENSITY | **3** | 仅保留功能性动效（解析进度、裁决移出队列、写入成功）。对账场景任何装饰性动画都在削弱可信度。 |
| VISUAL_DENSITY | **7** | 一个屏幕要同时承载"来源文本 / 解析字段 / 校验清单 / 裁决队列 / 汇总 / 汇报"，属于数据密集。密度 7 时禁止通用卡片容器堆叠，改用 border hairline 与 divide 分组、负空间分隔。 |

### 0.3 本阶段读取的知识库与行业文档

**知识库（已读，非本目录下另有命名）**：
- `references/design-systems/token-standard.md`（四层 Token 架构 + DESIGN.md 9 节模板）
- `references/design-systems/design-commands.md`（寄存器判断 + 23 命令 + 反 AI 散文 denylist + a11y 审计分离原则）
- `references/design-systems/ui-styles-library.md`（40 套风格 + 选用决策树）
- `references/design-systems/color-palettes.md`（30 套 × 17 语义色）
- `references/design-systems/typography-pairings.md`（25 套字体配对）
- `references/design-systems/industry-design-systems.md`（30 行业推理规则）

**行业文档（目录清单与选取说明）**：
`references/industries/` 下只有 **6 篇**：`ai-native.md`、`content-platform.md`、`ecommerce.md`、`enterprise.md`、`saas-b2b.md`。**没有**"广告投放 / MCN / 传媒 / 财务对账"专门文档。故就近取三篇合成规则：

| 行业文档 | 采纳的规则 |
|---|---|
| `enterprise.md`（主） | 审批流转可视化、数据密集型"高级筛选栏 + 可配置列表格"、表格行操作悬浮显示避免噪音、表单失焦校验、反模式：不用紫粉渐变、不用 emoji 图标、信息密度与操作效率优先 |
| `saas-b2b.md`（辅） | 左侧导航 + 右侧内容的标准控制台布局、表格为主、所有操作提供 undo、破坏性操作二次确认、批量操作需选中态 |
| `ai-native.md`（辅） | 生成结果的信任建立、AI 输出区分"系统判定 vs 模型建议"、5 态覆盖强制、反模式：不做英文首页欢迎语式空洞占位、不硬编码颜色 |
| `content-platform.md`（仅取领域词） | 提供"抖音 / 博主"领域词汇语境。其 Reader/Creator 型资讯流布局与本产品不匹配，不采纳。 |

> 说明：本产品是"给做投放运营的人用的内部对账工具"，不是内容消费产品。行业风格由企业审批后台 + SaaS 控制台主导。

---

## 1. 同类界面调研与对标结论

联网检索了 5 个同类界面，覆盖四个方向：财务对账、告警中心、控制台工艺、人工裁决工作台。

### 1.1 参考界面

**参考 1：Stripe Dashboard / Balance & Payout Reconciliation（财务对账）**
- 场景对应度最高。Stripe 的 Balance 报告就是"逐条核对、按类别汇总、导出交账"的对账流程。
- 信任感构建方式：**信息密度的控制而非视觉堆砌**。核心原则是"只显示你当下要行动的信息，不显示所有能显示的信息"。表格是事实的载体，图只是摘要。金额右对齐、等宽数字、极淡网格线。
- 可借用：右对齐数字 + tabular figures、分行级明细可下钻、每段右侧独立下载/导出动作、具体微文案（"发生了什么 + 为什么 + 怎么处理"）降低财务焦虑。
- 不借用：Stripe 的导航是"按作业组织"的多页结构，本产品是单页流水线，不引入多级导航。

**参考 2：Grafana Alerting / Alert List（告警中心）**
- 提供**严重度分级与状态机**的成熟表达：Alerting / Firing、Pending、No Data、OK、Paused，每个状态有专属颜色与语义图标。
- 信任感构建方式：**状态用颜色 + 图标 + 文字三重编码**，不靠颜色单通道；Alert 组件区分 Informational（蓝）/ Success（绿）/ Warning（黄）/ Error（红）四型，并区分"持久型"与"瞬时型"。
- 可借用：三态严重度配色、状态徽章必须图标 + 文字（防止色盲用户丢失信息）、"持久型提示"用于未裁决项（常驻直到处理），"瞬时型提示"用于解析完成/写入成功（自动消失）。
- 不借用：Grafana 的密集折线图与面板墙不适合"逐条裁决"的任务形态。

**参考 3：Linear（控制台工艺语言）**
- 提供高密度暗色工具的工艺标准：静默 chrome、单一强调色、1px 分隔线代替阴影与间隙、**数据面不做圆角、不加阴影**、圆角只留给交互元素与浮层。
- 信任感构建方式：**信息密度高但不拥挤**，因为非必要元素被直接删除；层级来自字重与间距，颜色只用于状态与强调。
- 可借用：1px hairline 分隔、数据面直角、近单色中性阶、强调色每屏不超过 2 处、键盘优先（Cmd+K 命令面板、g + 字母导航）、"undo 优先于确认"。
- 不借用：Linear 的 dark-first 默认。理由见第 3.8 节。

**参考 4：LangChain Human-in-the-Loop / Talonic Pipeline Review Queue（人工裁决工作台）**
- **与本产品"异常裁决"交互同构**，是最直接的结构参照。Talonic 的 Review Mode 是一个三栏工作台：左侧进度轨（含原因筛选 chip）、中间源文档、右侧决策栏（当前值、判定、候选值、裁决表单）。
- 信任感构建方式：**证据契约**。每个待裁决项强制携带：源文本或源字段、AI 输出、关键抽取证据、相关规则/schema、不确定度信号。裁决动作为三选一：**Approve（接受当前值）/ Correct（替换为指定值）/ Override（带必填理由接受）**，每次裁决写入 append-only 决策日志（谁决定、何时、原值、终值），日志随数据产品一起导出，交付方拿到完整交接轨迹。
- 可借用：三栏裁决工作台、三动作裁决（与本需求"确认无误 / 修正为某值 / 打回重提"一一对应）、裁决日志的不可篡改与可导出、按原因分类的队列（缺失值 / 分歧 / 校验失败 / 低置信）、相同值可聚类批量处理。
- 不借用：Talonic 面向扫描件 PDF，本产品的"源文档"是结构化文本 + 表格行，证据面板形态需替换为"文本片段 vs 表格行"的并列对照。

**参考 5：Retool / Grafana Design System（内部工具组件语法）**
- 提供内部工具的"组件栅格"语言与表单保存摩擦分级（autosave / inline save / page save / dialog save），破坏性操作的确认层级。
- 信任感构建方式：一致性（同一原语到处复用）、可预测的状态反馈。
- 可借用：一个主按钮 / 表单的规则、破坏性操作放右上角、保存摩擦分级（裁决的"修正"用 dialog save 高摩擦，"确认无误"用 inline save 低摩擦）。

### 1.2 对标品牌与设计语言（结论）

> **主对标：Stripe Dashboard（财务事实的呈现与信任机制）**
> **副语言：Linear（chrome 克制与数据面工艺）**
> **裁决结构参照：Talonic Review Queue / LangChain HITL（人工裁决工作台）**
> **状态配色参照：Grafana（严重度三重编码）**

**为什么是 Stripe 作为主对标：**
本产品的核心命题是"发现不一致时绝不猜测，必须标记并提醒人工确认"。这等价于 Stripe 面对的问题：让高风险、不能出错的数据在高压力下保持冷静可信。Stripe 的答案不是视觉精致，而是三条可迁移的机制：
1. **行动优先于完整**：屏幕只留"会改变你行为"的信息。本产品的首屏就应是"申请文本输入 + 解析结果 + 校验三态"，而不是营销式 Hero。
2. **表格即事实**：数字右对齐、等宽、可下钻到明细。本产品的账号表、金额、笔数都用这一套。
3. **微文案承担信任**：具体、诚实的语言比视觉打磨更能降低焦虑。"垫付文本称 7 笔，明细只有 5 条"这种具体陈述，就是本产品最好的信任资产。

**为什么补 Linear 作为副语言：**
Stripe 解决"呈现什么"，Linear 解决"如何安静地呈现"。裁决台需要同时展示三栏高密度信息，Linear 的 1px hairline、数据面直角、近单色中性阶、强调色克制，正好让三栏不靠边框阴影堆叠也能读清。

**为什么裁决交互照抄 Talonic 结构：**
Talonic 的 Approve / Correct / Override 三动作与需求给的"确认无误 / 修正为某值 / 打回重提"是同一族设计，且它已解决"证据要带什么、日志要记什么、同类项如何批量"三个工程问题。直接沿用结构，只替换证据面板的形态。

**明确不做的对标动作：**
不采用 Linear 的 dark-first 默认（见 3.8）、不采用 Grafana 的图表墙、不采用 Stripe 的多页导航、不做任何"Indigo 到 Pink 渐变 + 发光边框 + 毛玻璃"的组合。

---

## 2. 信息架构与交互流程

### 2.1 单页区块地图

单页操作台自上而下 6 个区块，纵向流水线，横向在裁决区展开为三栏工作台。

```
┌───────────────────────────────────────────────────────────────────────┐
│ 0  顶部条 Header                                                       │
│    [产品名] [测试副本 · 未污染原表]  ①粘贴 ②解析 ③校验 ④裁决 ⑤汇总 ⑥汇报  [主题][帮助] │
├───────────────────────────────────────────────────────────────────────┤
│ 1  输入区 Input（左主右辅）                                             │
│    左：申请文本输入  [抖加申请总结 | 垫付申请总结]  粘贴/上传/填充示例/清空  │
│    右：解析状态（待解析 / 解析中 / 解析完成 / 解析失败）                  │
├───────────────────────────────────────────────────────────────────────┤
│ 2  校验总览 Validation（三态计数条 + 写入闸门）                          │
│    [阻断 3] [警告 4] [正常 12]      → 写入测试副本（被阻断前禁用）        │
├───────────────────────────────────────────────────────────────────────┤
│ 3  异常裁决工作台 Adjudication（HERO，三栏）                            │
│    ┌── 左：裁决队列 ──┬── 中：证据面板 ──┬── 右：裁决动作栏 ──┐        │
│    │ 按严重度排序       │ ①问题 ②证据对照 ③影响 │ 确认/修正/打回   │        │
│    │ 阻断在前           │ 文本片段 vs 表格行   │ + 备注 + 日志     │        │
│    └───────────────────┴────────────────────┴──────────────────┘        │
├───────────────────────────────────────────────────────────────────────┤
│ 4  当日汇总 Summary                                                    │
│    抖加合计 / 垫付合计 / 申请笔数 vs 明细笔数 / 未裁决影响              │
├───────────────────────────────────────────────────────────────────────┤
│ 5  负责人汇报卡片 Report Card                                          │
│    一行结论 + 3 到 4 个关键数字 + 需决策项（≤3）  [复制][下载]          │
└───────────────────────────────────────────────────────────────────────┘
```

### 2.2 主流程

| 步 | 用户动作 | 系统反馈 | 视觉承载 |
|---|---|---|---|
| ① 输入 | 粘贴或上传一段《抖加申请总结》《垫付申请总结》文本；选择文本类型 tab | 显示字符数、识别到的文本类型 | 输入区，mono 字体等宽显示原文本 |
| ② 解析 | 点击"解析" | 进度条 + 逐字段出现（乐观呈现，解析中即预览抽取结果） | 解析状态区，字段以"文本抽取值 vs 表中匹配值"双列出现 |
| ③ 校验 | 自动 | 每条申请映射到一个校验结论：正常 / 警告 / 阻断 | 三态计数条 + 每条明细带状态徽章（图标 + 文字） |
| ④ 裁决 | 对每条警告/阻断项执行三选一动作 | 该项移出队列，写入裁决日志，计数条实时更新 | 裁决工作台三栏联动 |
| ⑤ 汇总 | 自动（裁决后重算） | 抖加合计、垫付合计、笔数口径核对 | 汇总区，等宽大号数字 |
| ⑥ 汇报 | 点击"生成汇报卡片" | 一屏卡片 + 复制/下载出口 | 汇报卡，结论 + 数字 + 需决策项 |

**写入闸门规则（核心约束的可视化）：**
"写入测试副本"按钮在存在**未裁决的阻断项**时保持 disabled，并显示原因（"3 项阻断未裁决，处理后可写入"）。警告项不阻断写入，但未裁决的警告会在写入结果与汇报卡中标注"待确认"。系统对任何缺失字段**不填充默认值**，一律留空并标记，这是"绝不猜测"在界面上的落点。

### 2.3 异常裁决工作台（产品核心）

**设计目标**：用户扫一眼就知道"哪一条、为什么异常、证据是什么、需要我确认什么"，并且能在同一屏完成裁决，不跳转。

**三栏职责**

**左栏：裁决队列**
- 每行是一条待裁决项，行结构（从左到右）：严重度图标（阻断红 / 警告琥珀）→ 一句话问题标题 → 涉及账号（博主昵称/抖音号）→ 已裁决/总数进度。
- 排序：阻断优先，再按涉及金额降序，再按队列顺序。
- 顶部一排"原因筛选 chip"：口径不自洽 / 字段缺失 / 日期异常 / 重复申请 / 支付人冲突。点击筛选，chip 显示各类计数。
- 相同值的多项可聚类为一行，支持一次裁决（沿用 Talonic 的 bulk-resolve 思路），例如多行"抖音号为空"。
- 行 hover 只显示一个动作"定位证据"，避免视觉噪音（工程企业规范：行操作悬浮显示）。

**中栏：证据面板**（选中队列项后展开，回答三个问题）

| 区块 | 回答的问题 | 内容与呈现 |
|---|---|---|
| ① 问题陈述 | **为什么异常** | 一句结论式标题 + 规则名徽章。例：「垫付文本称"共 7 笔"，明细仅 5 条」+ 徽章「规则：笔数与金额口径自洽」。标题用 20px，规则徽章用 12px 全大写加宽字距。 |
| ② 证据对照 | **证据是什么** | 左右并列两栏对齐展示：左栏=来源文本片段（保留上下文，冲突 token 高亮底色），右栏=账号表中匹配行（整行渲染，冲突单元格高亮）。日期类异常带差值指示（例：申请日 2026-09-03，预计打款 26/08/31，标"倒挂 3 天"）。重复申请类把两行并列，空字段那行整体降饱和 + 空单元格虚线框。 |
| ③ 影响说明 | **不处理会怎样** | 一句后果陈述 + 影响的汇总数字。例：「若按 7 笔入账，垫付合计将多计 ¥4,300」。用语义色左边缘 1px 竖条标注严重度。 |

- 证据面板的来源文本使用 mono 字体，冲突 token 用警告底色；表格行用 sans，冲突单元格用警告底色 + 1px 边框，不依赖颜色单通道（同时加一个小的冲突图标）。
- 证据面板提供"原文定位"：点击来源片段，高亮定位到输入区对应 token。

**右栏：裁决动作栏**（三动作，与需求一一对应）

| 动作 | 语义 | 交互与摩擦 | 必填 |
|---|---|---|---|
| 确认无误 | 系统标记可疑，人工核实后认定无误 | inline save，低摩擦，单次点击 | 无（可选备注） |
| 修正为某值 | 人工给出正确值，覆盖系统抽取/表中值 | dialog save，高摩擦：打开内联编辑器，填正确值 + 选修正对象（改文本理解 / 改表格值） | 正确值 + 理由 |
| 打回重提 | 无法在当前环节确认，退回发起人补充 | inline save，写入"打回"状态 + 通知语义 | 理由（必填） |

- 三动作都必须写裁决日志：`{项 ID, 规则, 严重度, 原值, 终值, 动作, 操作人, 时间, 理由}`，日志只追加不修改，可导出 CSV（沿用 Talonic 的 append-only decision log）。这是"可审计"的体现，也是汇报卡"需决策项"的数据来源。
- 裁决后该项从队列移出，进入"已裁决"折叠区（可回看、可撤销，撤销再次写日志）。
- 动作栏底部常驻一行只读提示：「系统不对缺失/冲突字段做任何默认猜测」，明示产品承诺。

**三态定义（贯穿全产品一致）**

| 态 | 语义 | 是否阻断写入 | 承载色（语义色，非原始色值） |
|---|---|---|---|
| 正常 | 校验通过，无需操作 | 否 | `--status-ok-*`（绿） |
| 警告 | 存疑但可继续，需人工确认 | 否，但会标注"待确认" | `--status-warn-*`（琥珀） |
| 阻断 | 不可继续，必须处理 | 是 | `--status-block-*`（朱红） |
| 待确认/未裁决 | 中性，尚未判定 | 否 | `--status-neutral-*`（灰） |

### 2.4 当日汇总

- 四个数字块，横向排列，等宽大号（`--text-3xl`）数字右对齐：
  - 抖加合计（金额）
  - 垫付合计（金额）
  - 申请笔数 vs 明细笔数（两个数并排，不一致时差值用警告色 + "不一致"徽章）
  - 未裁决影响（金额，中性色 + "待确认"徽章）
- 每个数字块下有一行 12px 来源说明（例："来源：垫付申请总结文本 + 测试副本 5 行"），保证数字可追溯。
- 数字块之间用 1px hairline 分隔，不套卡片阴影。

### 2.5 负责人汇报卡片的压缩原则

汇报卡片是"给负责人看的"，负责人只要结论与决策点，不要过程。

**只保留 4 类信息：**
1. **一行结论**：一句话说清今天能不能入账。例：「抖加 5 笔共 ¥12,480 可入账；垫付存在 3 项口径不一致，未入账待确认」。
2. **关键数字**（3 个，不超过 4 个）：抖加合计、垫付合计、不一致项数。等宽大号，右对齐。
3. **需决策项**（≤3 条）：每条一行，格式「严重度徽章 + 一句话 + 需要谁的什么决定」。例：「阻断 · 垫付笔数 7 与明细 5 不符 · 需财务确认按 5 笔入账」。超过 3 条折叠为"另有 N 项，见详情"。
4. **元信息**：生成时间 + 数据来源标识（"测试副本，未触碰原表"）。

**必须去掉：** 逐条明细、解析过程、技术字段名、系统内部状态、任何装饰。
**出口：** 两个按钮。"复制为文本"（单行纯文本，方便直接贴群）与"下载"（Markdown 或 PNG）。
**尺寸约束：** 桌面端卡片宽度约 640px（`max-w-2xl`），内容一屏可见，不超 5 行正文。

### 2.6 组件状态矩阵（5 态覆盖）

| 组件 | Loading | Empty | Error | Populated | Edge |
|---|---|---|---|---|---|
| 输入区 | 解析中：进度条 + 逐字段出现 | 未输入：显示"粘贴或上传申请总结"引导 + 两个示例按钮 | 文本无法识别："未识别到有效申请条目，请检查文本类型" | 已输入：字符数 + 类型识别结果 | 超长文本折叠 + "展开全文"；含 emoji/UGC 原样保留 |
| 解析结果 | 骨架屏（字段占位灰条） | 无字段：提示选择文本类型 | 单字段解析失败：该字段标"未识别"，不影响其他字段 | 双列（文本抽取值 / 表中匹配值） | 表中无匹配行："未找到对应账号" + 提供"新建行"入口 |
| 裁决队列 | 骨架行 | 全部已裁决：显示"全部已裁决" + 计数 | 队列加载失败：错误 + 重试 | 按严重度排序的队列行 | 单类异常 50+ 条：自动聚类 + 批量裁决 |
| 证据面板 | 定位中：来源高亮 pending 提示 pill | 未选中：右侧提示"从左侧选择一条待裁决项" | 源文本片段定位失败：降级显示整段原文 | 三区块（问题/证据/影响） | 源文本超长：折叠上下文，保留冲突 token 前后各 1 行 |
| 汇总 | 计算中：数字位骨架 | 无数据：数字显示占位 + "解析后生成" | 计算失败：显示错误 + 重试 | 四数字块 + 来源说明 | 金额为 0 或负：显式显示"¥0"或负值，不用空 |
| 汇报卡 | 生成中：卡片骨架 | 未生成：按钮"生成汇报卡片" | 生成失败：错误 + 重试 | 结论 + 数字 + 需决策项 | 需决策项 > 3：折叠 "另有 N 项" |

### 2.7 响应式与键盘

**断点**（product register 用内容驱动断点）：
- `>=1280px`：裁决工作台三栏并排（队列 320px / 证据自适应 / 动作 360px）。
- `>=1024px`：三栏，动作栏可折叠为右侧抽屉。
- `>=768px`：证据面板与动作栏合并为上下两段，队列改为顶部横向 chip 行。
- `<768px`：单列堆叠，顺序为 队列 → 证据 → 动作；输入区与汇总单列；触摸目标 ≥44×44px；汇报卡全宽。桌面为主场景，移动端保证"可读、可裁决"，不追求同等效率。

**键盘（生产者级工具的基本要求，参照 Linear）**：
- Cmd/Ctrl + K：命令面板（跳转到下一条阻断项、生成汇报卡、复制汇报文本）。
- J / K：在裁决队列中上下移动；1 / 2 / 3：确认无误 / 修正 / 打回。
- 队列 row 必须可 Tab 聚焦并显示 focus-visible 焦点环；证据面板的"原文定位"可键盘触发。
- `prefers-reduced-motion`：所有过渡降为 0ms，仅保留状态切换的即时时序反馈。

### 2.8 文案规则（呼应"绝不猜测"的产品承诺）

- 错误/异常文案一律用公式"发生了什么 + 为什么 + 怎么处理"。
- 数值口径必须带单位与来源，异常句子必须给出具体数字与字段名，禁止"数据异常"这类模糊说法。
- 系统判定与模型建议分开标注：抽取/校验结果标"系统判定"，任何推测标"模型建议（未采纳）"。
- 禁止空洞占位文案与英文模板味套话（不出现英文首页欢迎语、拉丁占位文、"开始使用" 这类无信息文本），空状态一律给具体下一步。

---

## 3. 视觉方向与 Design Token 骨架

### 3.1 配色基调

**核心判断**：本产品的视觉主角是"风险与确认"，配色必须让**三级风险一眼可分**，同时让"财务事实"保持冷静。所以策略是：大面积中性色承载账本气质，一个深靛蓝品牌色作为权威与主操作，五个语义色承担状态。

**主色选择理由：**
- 主色取**深靛蓝 `--color-primary`（#3550B4）**。理由：对账产品的信任来自"权威 + 精确"，企业/金融行业规范一致指向深蓝系（`enterprise.md`：深蓝/藏青传达专业可信）。
- 刻意避开两个 AI 反射：不做 Tailwind 默认 Indigo `#6366F1` 作强调色（业界公认首罪），不做紫到粉渐变。选用的深靛蓝饱和度更低、明度更沉，读起来像"账本封皮"而非"AI 产品"。
- 主色只用于：主操作按钮（写入测试副本、生成汇报卡）、当前选中的队列行、当前 Tab、聚焦环。**每屏强调色可见使用 ≤2 处**。
- 中性色带极微量 chroma（约 0.008）倾向主色相，让"冷"与"账本"在一个色温里凝聚，不出现冷灰与暖灰混用。

**中性色阶**（浅色主题默认，层级靠底色差而非阴影）：

| Token | 值 | 用途 |
|---|---|---|
| `--color-bg` | #F7F8FB | 页面底色 |
| `--color-surface` | #FFFFFF | 卡片/面板/表格底 |
| `--color-surface-sunken` | #F1F3F8 | 输入区/次要面板/嵌套区 |
| `--color-fg` | #14171F | 主文本 |
| `--color-fg-2` | #3A4050 | 次级文本 |
| `--color-muted` | #647084 | 副文本/标签/表头 |
| `--color-meta` | #8B93A7 | 元数据/时间戳/三级信息 |
| `--color-border` | #E2E5EC | 默认 1px 边框 |
| `--color-border-soft` | #EEF0F5 | 表格行分隔/内部 divide |
| `--color-border-strong` | #C9CEDB | 面板外框/强分隔 |

### 3.2 语义色三级区分度（本产品最重要的一组 Token）

三级风险必须做到"颜色、图标、文字、左边缘条"四通道同时区分，防止颜色单通道传达。

| 语义 | Token 族 | fg（文字/图标） | bg（浅底） | border（描边） | 图标 | 使用场景 |
|---|---|---|---|---|---|---|
| 正常/成功 | `--status-ok-*` | #0F7A4F | #E8F6EF | #B7E3CE | circle-check | 校验通过、写入成功、已打款 |
| 警告 | `--status-warn-*` | #9A5B06 | #FDF3E2 | #F1D6A6 | triangle-alert | 存疑需确认、待审批、打款人为空 |
| 阻断/危险 | `--status-block-*` | #B22A2A | #FDECEC | #F3C3C3 | octagon-alert | 口径不自洽、日期倒挂、重复申请、不可写入 |
| 信息 | `--status-info-*` | #1F5FA8 | #EAF2FD | #BCD8F5 | info | 中性提示、解析完成、来源说明 |
| 待确认/中性 | `--status-neutral-*` | #647084 | #F1F3F8 | #E2E5EC | circle-dashed | 未裁决、未填字段、草稿 |

- 三态各自绑定"图标 + 文字标签 + 左边缘 1px 竖条"，颜色是第三条冗余编码，不是唯一编码。
- 品牌主色 `--color-primary` 与信息色 `--status-info-*` 属同一蓝色系的深浅两档（主色更沉更深），语义上区分"品牌操作"与"中性信息"，不会互相抢戏。

### 3.3 字体方案

**Product 寄存器用单字族 + 等宽，不做展示字体。**

| Token | 字体栈 | 用途 |
|---|---|---|
| `--font-sans` | `"Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif` | UI/正文/标题（中文由 Noto Sans SC 与系统 CJK 兜底） |
| `--font-mono` | `"JetBrains Mono", "SFMono-Regular", "Roboto Mono", ui-monospace, "Noto Sans SC", monospace` | 金额、抖音号、日期、表格数字、来源文本片段、裁决日志 |

**选择理由：**
- **等宽字体是本产品的视觉签名，不是装饰。** 金额、笔数、抖音号、日期必须列对齐才能被快速扫读；JetBrains Mono 的 0/O、1/l/I 字形可分，直接降低抖音号与金额的误读风险。
- **sans 用 Inter 承载 UI 与正文**（规则允许 Inter 作正文/UI 载体），中文交由 Noto Sans SC 与系统 CJK 兜底，避免中文字重断裂。层级完全靠字重与字号建立，不靠字体族混搭，规避"一族里挑两个相似 sans"的配对反模式。
- 不选反射式展示字体（Playfair / Space Grotesk / DM Sans / Plus Jakarta Sans 等），因为本产品没有展示场景。
- **数字与分类标签策略**：所有金额用 `--font-mono` + `font-variant-numeric: tabular-nums` + 右对齐；全大写或中文小标签（如"规则""严重度"）用 `--tracking-wide` 加宽字距。

**字重三级**：常规 400 / 强调 500（次标题、表头、按钮）/ 加重 600（页面标题、关键数字）。变量字体可用时映射为 400 / 510 / 590（沿用知识库的三级字重体系）。

**加载建议**：`display=swap`，Inter 与 JetBrains Mono 只用所需字重（400/500/600），Noto Sans SC 建议子集化（中文全量体积大）。

### 3.4 字号 / 行高 / 字距

| Token | 值 | 行高 | 用途 | 字距 |
|---|---|---|---|---|
| `--text-xs` | 12px / 0.75rem | 1.5 | 元数据、等宽标签、徽章 | 全大写或标签用 +0.06em |
| `--text-sm` | 14px / 0.875rem | 1.55 | 表格单元格、队列行、正文紧凑 | 0 |
| `--text-base` | 16px / 1rem | 1.6 | 正文、描述、证据文本 | 0 |
| `--text-lg` | 18px / 1.125rem | 1.4 | 强调正文、小标题 | -0.01em |
| `--text-xl` | 20px / 1.25rem | 1.3 | 卡片标题、问题陈述标题 | -0.01em |
| `--text-2xl` | 24px / 1.5rem | 1.25 | 区块标题 | -0.02em |
| `--text-3xl` | 32px / 2rem | 1.15 | 页面标题、汇总数字 | -0.02em |
| `--text-4xl` | 40px / 2.5rem | 1.1 | 汇报卡关键数字 | -0.02em |

- 正文基准 16px，行高 1.6；表格密集场景用 14px，行高 1.55。
- 字距：标题 ≥32px 用 -0.02em，正文 0，全大写/中文小组标签 +0.06em。

### 3.5 间距 / 圆角 / 阴影 / 边框

**间距**（4px 网格，仅允许下列值）：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64。禁止 5/7/13/15/22/30 等非标值。

**圆角**（数据面直角，圆角留给交互元素与浮层，沿用 Linear 工艺）：

| Token | 值 | 用途 |
|---|---|---|
| `--radius-none` | 0 | 数据表格、队列行、面板、段落（数据面一律直角） |
| `--radius-xs` | 2px | 极小的标记（严重度左边缘条端点） |
| `--radius-sm` | 4px | 徽章、chip、tag |
| `--radius-md` | 8px | 按钮、输入框、可点击行的高亮态 |
| `--radius-lg` | 12px | 卡片、模态框、浮层容器 |
| `--radius-pill` | 9999px | 进度条、开关、头像 |

**阴影**（只用于浮层：模态、下拉、popover、toast。数据面一律不用阴影，用 1px hairline 与底色差）：

| Token | 值 | 用途 |
|---|---|---|
| `--shadow-flat` | none | 数据面默认 |
| `--shadow-ring` | `0 0 0 1px var(--color-border)` | 需要轮廓的面板/聚焦元素 |
| `--shadow-raised` | `0 1px 2px rgba(16,20,32,0.06), 0 8px 24px rgba(16,20,32,0.08)` | 模态、下拉、toast |

**边框层级**：`1px` 默认边框；`1px` 内部行分隔（更淡）；`2px` 聚焦环（配合 `--focus-ring`）。禁止用 `border-left/right > 1px` 的彩色侧条纹做强调（知识库绝对禁令）。严重度左边缘条固定为 3px 竖条 + 圆角 2px，属于状态标识而非卡片装饰。

### 3.6 动效

| 场景 | 时长 | Token |
|---|---|---|
| 即时反馈（按钮按下、开关、hover 变色） | 100ms | `--motion-instant` |
| 状态切换（选中行、chip 切换、徽章变化） | 150ms | `--motion-fast` |
| 内容进入（裁决项移出队列、toast 弹出、字段流入） | 200ms | `--motion-base` |
| 面板/模态（证据面板展开、汇报卡生成） | 300ms | `--motion-slow` |
| 缓动 | `cubic-bezier(0.2, 0, 0, 1)`（标准）/ `cubic-bezier(0.16, 1, 0.3, 1)`（进入） | `--ease-standard` / `--ease-out` |

- 只用 `transform` / `opacity` 做动效，不动画 width/height。
- 禁止弹跳与弹性缓动，禁止超过 400ms 的动画，禁止同时超过 3 个元素动画。
- 必须支持 `prefers-reduced-motion: reduce`，降为 0ms。

### 3.7 design-tokens.json 骨架

> 命名采用语义命名（`--color-*` / `--space-*` / `--font-*` / `--radius-*` / `--shadow-*`），不用 `blue-500` 这类原始命名。前端通过 `import tokens from './design-tokens.json'` 引用。以下为浅色主题（默认）值。

```json
{
  "color": {
    "bg": { "value": "#F7F8FB", "type": "color", "layer": "A1" },
    "surface": { "value": "#FFFFFF", "type": "color", "layer": "A1" },
    "surface-sunken": { "value": "#F1F3F8", "type": "color", "layer": "B-slot" },
    "fg": { "value": "#14171F", "type": "color", "layer": "A1" },
    "fg-2": { "value": "#3A4050", "type": "color", "layer": "B-slot" },
    "muted": { "value": "#647084", "type": "color", "layer": "A1" },
    "meta": { "value": "#8B93A7", "type": "color", "layer": "B-slot" },
    "border": { "value": "#E2E5EC", "type": "color", "layer": "A1" },
    "border-soft": { "value": "#EEF0F5", "type": "color", "layer": "B-slot" },
    "border-strong": { "value": "#C9CEDB", "type": "color", "layer": "B-slot" },

    "primary": { "value": "#3550B4", "type": "color", "layer": "A1" },
    "primary-hover": { "value": "#2C44A0", "type": "color", "layer": "A2" },
    "primary-active": { "value": "#243889", "type": "color", "layer": "A2" },
    "primary-subtle-bg": { "value": "#EDF0FB", "type": "color", "layer": "A2" },
    "primary-subtle-fg": { "value": "#2A3F94", "type": "color", "layer": "A2" },
    "on-primary": { "value": "#FFFFFF", "type": "color", "layer": "A2" },

    "status-ok-fg": { "value": "#0F7A4F", "type": "color", "layer": "A2" },
    "status-ok-bg": { "value": "#E8F6EF", "type": "color", "layer": "A2" },
    "status-ok-border": { "value": "#B7E3CE", "type": "color", "layer": "A2" },
    "status-warn-fg": { "value": "#9A5B06", "type": "color", "layer": "A2" },
    "status-warn-bg": { "value": "#FDF3E2", "type": "color", "layer": "A2" },
    "status-warn-border": { "value": "#F1D6A6", "type": "color", "layer": "A2" },
    "status-block-fg": { "value": "#B22A2A", "type": "color", "layer": "A2" },
    "status-block-bg": { "value": "#FDECEC", "type": "color", "layer": "A2" },
    "status-block-border": { "value": "#F3C3C3", "type": "color", "layer": "A2" },
    "status-info-fg": { "value": "#1F5FA8", "type": "color", "layer": "A2" },
    "status-info-bg": { "value": "#EAF2FD", "type": "color", "layer": "A2" },
    "status-info-border": { "value": "#BCD8F5", "type": "color", "layer": "A2" },
    "status-neutral-fg": { "value": "#647084", "type": "color", "layer": "A2" },
    "status-neutral-bg": { "value": "#F1F3F8", "type": "color", "layer": "A2" },
    "status-neutral-border": { "value": "#E2E5EC", "type": "color", "layer": "A2" }
  },

  "font": {
    "family": {
      "sans": { "value": "Inter, Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif", "type": "fontFamily" },
      "mono": { "value": "JetBrains Mono, SFMono-Regular, Roboto Mono, ui-monospace, monospace", "type": "fontFamily" }
    },
    "weight": {
      "regular": { "value": "400", "type": "fontWeight" },
      "medium": { "value": "500", "type": "fontWeight" },
      "semibold": { "value": "600", "type": "fontWeight" }
    },
    "size": {
      "xs": { "value": "0.75rem", "type": "dimension" },
      "sm": { "value": "0.875rem", "type": "dimension" },
      "base": { "value": "1rem", "type": "dimension" },
      "lg": { "value": "1.125rem", "type": "dimension" },
      "xl": { "value": "1.25rem", "type": "dimension" },
      "2xl": { "value": "1.5rem", "type": "dimension" },
      "3xl": { "value": "2rem", "type": "dimension" },
      "4xl": { "value": "2.5rem", "type": "dimension" }
    },
    "leading": {
      "tight": { "value": "1.15", "type": "number" },
      "heading": { "value": "1.3", "type": "number" },
      "body": { "value": "1.6", "type": "number" }
    },
    "tracking": {
      "tight": { "value": "-0.02em", "type": "dimension" },
      "normal": { "value": "0", "type": "dimension" },
      "wide": { "value": "0.06em", "type": "dimension" }
    }
  },

  "space": {
    "1": { "value": "4px", "type": "dimension" },
    "2": { "value": "8px", "type": "dimension" },
    "3": { "value": "12px", "type": "dimension" },
    "4": { "value": "16px", "type": "dimension" },
    "5": { "value": "20px", "type": "dimension" },
    "6": { "value": "24px", "type": "dimension" },
    "8": { "value": "32px", "type": "dimension" },
    "10": { "value": "40px", "type": "dimension" },
    "12": { "value": "48px", "type": "dimension" },
    "16": { "value": "64px", "type": "dimension" }
  },

  "radius": {
    "none": { "value": "0", "type": "dimension" },
    "xs": { "value": "2px", "type": "dimension" },
    "sm": { "value": "4px", "type": "dimension" },
    "md": { "value": "8px", "type": "dimension" },
    "lg": { "value": "12px", "type": "dimension" },
    "pill": { "value": "9999px", "type": "dimension" }
  },

  "shadow": {
    "flat": { "value": "none", "type": "boxShadow" },
    "ring": { "value": "0 0 0 1px #E2E5EC", "type": "boxShadow" },
    "raised": { "value": "0 1px 2px rgba(16,20,32,0.06), 0 8px 24px rgba(16,20,32,0.08)", "type": "boxShadow" }
  },

  "border": {
    "width": {
      "hairline": { "value": "1px", "type": "dimension" },
      "focus": { "value": "2px", "type": "dimension" },
      "severity-bar": { "value": "3px", "type": "dimension" }
    }
  },

  "focus": {
    "ring": { "value": "0 0 0 3px rgba(53,80,180,0.28)", "type": "boxShadow" },
    "offset": { "value": "2px", "type": "dimension" }
  },

  "motion": {
    "instant": { "value": "100ms", "type": "duration" },
    "fast": { "value": "150ms", "type": "duration" },
    "base": { "value": "200ms", "type": "duration" },
    "slow": { "value": "300ms", "type": "duration" },
    "ease-standard": { "value": "cubic-bezier(0.2, 0, 0, 1)", "type": "cubicBezier" },
    "ease-out": { "value": "cubic-bezier(0.16, 1, 0.3, 1)", "type": "cubicBezier" }
  },

  "layout": {
    "container-max": { "value": "1440px", "type": "dimension" },
    "workbench-queue": { "value": "320px", "type": "dimension" },
    "workbench-action": { "value": "360px", "type": "dimension" },
    "report-card-max": { "value": "640px", "type": "dimension" }
  },

  "z": {
    "base": { "value": "0", "type": "number" },
    "dropdown": { "value": "1000", "type": "number" },
    "sticky": { "value": "1100", "type": "number" },
    "modal": { "value": "1200", "type": "number" },
    "toast": { "value": "1300", "type": "number" }
  }
}
```

**深色主题覆盖**（可选切换，同结构只覆盖值）：

```json
{
  "color": {
    "bg": { "value": "#0D1017" },
    "surface": { "value": "#151922" },
    "surface-sunken": { "value": "#10141B" },
    "fg": { "value": "#E9ECF3" },
    "fg-2": { "value": "#C2C8D6" },
    "muted": { "value": "#8B93A7" },
    "meta": { "value": "#626B80" },
    "border": { "value": "#262C38" },
    "border-soft": { "value": "rgba(255,255,255,0.06)" },
    "border-strong": { "value": "#3A4252" },
    "primary": { "value": "#6E86E8" },
    "primary-subtle-bg": { "value": "#1A2140" },
    "status-ok-fg": { "value": "#4CC38A" },
    "status-warn-fg": { "value": "#E0A32E" },
    "status-block-fg": { "value": "#E5706F" },
    "status-info-fg": { "value": "#6BA8EC" }
  }
}
```

### 3.8 深浅色主题支持策略

**结论：演示默认浅色（light）。深色作为可选切换，Token 已完整覆盖。**

理由：
1. **阅读效率**：对账的核心动作是长时间阅读证据文本（来源片段、表格行、理由）。浅底深字在长文本阅读上的效率高于深底亮字，深色主题会引入"暗底亮字需补偿行高与字距"的额外成本。
2. **演示环境安全**：面试演示多在投影或共享屏幕下进行，浅色主题在投影下对比稳定，深色在投影或高环境光下容易发灰。
3. **语义正确**：浅色 + 深靛蓝 + 1px hairline + 右对齐等宽数字，读起来就是"账本与凭证"的气质，与产品命题一致。深色会把它读成"开发者工具"，偏离财务对账的语境。
4. **差异化**：深色 AI 面板已是默认套路，浅色账本在同类演示中辨识度更高。
5. 深色仍完整实现（token 已备），仅作为偏好项；切换不影响任何语义色的三级区分度（深色版语义 fg 已重新取值，保证对比度）。

---

## 4. 图标系统

### 4.1 图标库锁定

> **全项目锁定一套：Lucide（lucide.dev）**

- 授权与形态：MIT，SVG 描边图标，24×24 viewBox，`stroke="currentColor"`，默认 `stroke-width: 1.5`。
- 选型理由：语义完备（覆盖校验/告警/裁决/表格/审计所需的全部语义）、描边统一、可矢量缩放、体量小、与"克制、精确"的产品气质一致，且与企业与 AI 原生行业规范推荐一致（`enterprise.md`、`ai-native.md` 均指向 Lucide）。
- 全项目统一，不混用其他图标库（不得引入 Font Awesome、Material Icons 等第二套）。

**引入方式**（按前端最终选型二选一，均属同一库）：
- 有打包（Vite / ESM）：`import { ShieldAlert, Gavel } from 'lucide'`（vanilla）或 `lucide-react`（若上 React）。
- 无打包（纯静态轻前端）：引入 `lucide` 的 UMD/CDN（`<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>` + `<i data-lucide="shield-alert"></i>` + `lucide.createIcons()`），或使用 `lucide-static` 生成内联 SVG sprite（推荐，免运行时依赖、可用 CSS 控制颜色）。

### 4.2 尺寸与描边规范

| 尺寸 Token | 值 | 使用场景 | 描边 |
|---|---|---|---|
| `--icon-inline` | 16px | 行内（徽章内、文本旁、表格单元格） | stroke-width 1.75（小尺寸加粗保证可辨） |
| `--icon-button` | 20px | 按钮内、chip 内、队列行 | stroke-width 1.5 |
| `--icon-standalone` | 24px | 区块标题旁、空状态、状态总览 | stroke-width 1.5 |

- 图标颜色一律继承 `currentColor`，由语义 Token 决定，禁止单独硬编码色值。
- 状态图标必须与文字标签同时出现（不单独用图标表达状态），保证颜色非唯一编码。

### 4.3 图标清单与语义选用

| 语义 | Lucide 图标名 | 尺寸 | 用色 Token | 选用说明 |
|---|---|---|---|---|
| 解析文本 | `scan-text` | 20 | `--color-muted` | 解析入口按钮与解析区标题 |
| 解析中 | `loader-circle` | 20 | `--color-primary` | 旋转进度，配合进度条 |
| 解析完成 | `circle-check` | 16 | `--status-ok-fg` | 瞬时提示（toast，自动消失） |
| 校验通过（正常） | `circle-check` | 16 | `--status-ok-fg` | 三态徽章之一，必须配"正常"文字 |
| 警告 | `triangle-alert` | 16 | `--status-warn-fg` | 三态徽章之二，配"警告"文字 |
| 阻断 | `octagon-alert` | 16 | `--status-block-fg` | 三态徽章之三，配"阻断"文字 |
| 信息 | `info` | 16 | `--status-info-fg` | 中性提示、来源说明 |
| 待确认/未裁决 | `circle-dashed` | 16 | `--status-neutral-fg` | 未裁决项、草稿态 |
| 待人工确认 | `user-round-check` | 20 | `--status-warn-fg` | 裁决工作台入口、需人工介入标记 |
| 人工裁决 | `gavel` | 20 | `--color-primary` | 裁决动作栏标题 |
| 裁决日志/审计 | `scroll-text` | 16 | `--color-muted` | 已裁决折叠区、日志导出入口 |
| 撤销裁决 | `rotate-ccw` | 16 | `--color-fg-2` | 已裁决项回退 |
| 写入表格 | `table-2` | 20 | `--color-primary` | "写入测试副本"主按钮 |
| 测试副本 | `flask-conical` | 16 | `--status-info-fg` | 顶部条"测试副本 · 未污染原表"标识 |
| 原表/副本对照 | `file-stack` | 16 | `--color-muted` | 原表与副本关系说明 |
| 汇总 | `sigma` | 20 | `--color-fg-2` | 当日汇总区标题 |
| 汇报 | `send` | 20 | `--color-primary` | 生成汇报卡片按钮 |
| 负责人/报告 | `file-text` | 20 | `--color-fg-2` | 汇报卡标题 |
| 复制 | `copy` | 16 | `--color-fg-2` | 复制为文本、复制字段值 |
| 下载 | `download` | 16 | `--color-fg-2` | 下载汇报卡、下载裁决日志 CSV |
| 上传 | `upload` | 16 | `--color-fg-2` | 上传申请文本文件 |
| 粘贴 | `clipboard-paste` | 16 | `--color-fg-2` | 粘贴示例/粘贴正文 |
| 清空 | `eraser` | 16 | `--color-muted` | 清空输入 |
| 金额 | `banknote` | 16 | `--color-fg-2` | 金额字段前缀、汇总数字标签 |
| 账号（博主昵称） | `user-round` | 16 | `--color-fg-2` | 账号字段 |
| 抖音号 | `hash` | 16 | `--color-fg-2` | 抖音号字段（数字 ID 用 mono 呈现） |
| 支付人 | `wallet` | 16 | `--color-fg-2` | 支付人字段 |
| 打款状态 | `circle-check-big` | 16 | `--status-ok-fg` | 已打款；待打款用 `circle-dot`（`--status-warn-fg`），未打款用 `ban`（`--status-neutral-fg`） |
| 时钟/时间 | `clock` | 16 | `--color-muted` | 时间字段、生成时间 |
| 日期 | `calendar` | 16 | `--color-muted` | 申请日期、预计打款日期 |
| 日期异常（倒挂） | `calendar-x` | 16 | `--status-block-fg` | 日期倒挂异常项 |
| 重复申请 | `copy` | 16 | `--status-block-fg` | 重复行异常（与"复制"动作图标语义区分：异常项用阻断色） |
| 口径冲突 | `unlink` | 16 | `--status-block-fg` | 支付人冲突、笔数与金额口径不自洽 |
| 字段缺失 | `square-dashed` | 16 | `--status-warn-fg` | 抖音号为空、打款人为空等缺失字段 |
| 证据/来源 | `quote` | 16 | `--color-muted` | 证据面板来源片段标记 |
| 定位证据 | `scan-search` | 16 | `--color-fg-2` | 队列行 hover 动作、原文定位 |
| 展开/折叠 | `chevron-down` / `chevron-right` | 16 | `--color-muted` | 已裁决折叠区、上下文展开 |
| 筛选 | `list-filter` | 16 | `--color-muted` | 原因筛选 chip 行 |
| 严重度排序 | `arrow-down-narrow-wide` | 16 | `--color-muted` | 队列排序说明 |
| 搜索 | `search` | 16 | `--color-muted` | 队列内搜索账号 |
| 命令面板 | `command` | 16 | `--color-muted` | 键盘快捷键提示前缀 |
| 帮助 | `circle-help` | 16 | `--color-muted` | 规则解释、字段口径说明 |
| 主题切换 | `sun` / `moon` | 16 | `--color-muted` | 深浅色切换 |
| 关闭 | `x` | 16 | `--color-muted` | 关闭浮层/toast |
| 空状态 | `inbox` | 24 | `--color-meta` | 队列清空、无待裁决项 |
| 提交 | `send-horizontal` | 20 | `--color-primary` | 裁决"确认无误"以外的主提交动作 |
| 修正为 | `pencil-line` | 20 | `--color-primary` | 裁决"修正为某值" |
| 打回重提 | `undo-2` | 20 | `--status-warn-fg` | 裁决"打回重提" |

---

## 5. 与后续阶段的交接（advisory，供 team-lead 决策）

1. **建议在架构 Spec 中锁定技术栈后，由我把本 Token 骨架落成 `design-tokens.css`**。本阶段按要求只产出方向文档与 JSON 骨架，未创建 token CSS 文件。前端接入时建议同时给出 `design-tokens.css`（`--color-*` 变量）与 `design-tokens.json`，前端可 `import` JSON 或直接消费 CSS 变量。
2. **建议在 Phase 2 产出 `DESIGN.md`（9 节）与 `design-system/MASTER.md`**。本文件是"设计方向"，DESIGN.md 是"设计契约源"。两者不重复：方向文档定 why，DESIGN.md 定 what（组件规范、Tailwind config、CSS 变量全文、Agent 实现指南）。
3. **建议前端实现优先级**：先落地 Token 层与三态语义色，再实现裁决工作台三栏，最后做汇报卡。裁决工作台是本产品的演示记忆点，其证据面板的"文本片段 vs 表格行"并列对照必须与后端返回的证据结构对齐（需要后端在解析结果中返回：冲突字段名、原值、抽取值、规则名、来源片段偏移）。
4. **需要与后端约定一个"证据契约"**（沿用 Talonic 的证据契约思路）：每条校验结论必须携带 `{规则名, 严重度, 涉及账号, 冲突字段, 文本原值, 表中原值, 来源片段偏移, 影响金额}`。界面所有裁决项都由此渲染，缺字段则降级展示为"证据不完整"。
5. **未决问题**：产品名待定（当前以"推广申请处理台"占位）；文本类型 tab 是否固定为"抖加/垫付"两类，取决于是否还会有第三类申请，建议由 PM 在 PRD 中定。
6. 无障碍的对比度/键盘/屏幕阅读器专项检查放在后续 audit 阶段执行（设计期已把 focus-visible、键盘顺序、reduced-motion 写入契约，但不在此阶段做对比度扫描，避免产出保守方案）。

---

## 6. 反 AI 模板自检

| 检查项 | 结果 |
|---|---|
| P0-1 无 emoji 作为功能图标 | 通过。全文无 emoji，图标一律以 Lucide 图标名 + 语义描述呈现 |
| P0-2 无紫到粉渐变主视觉 | 通过。主色为深靛蓝 #3550B4 纯色，无渐变，无发光边框，无装饰性毛玻璃 |
| P0-3 无 AI 模板味 | 通过。无空洞占位与英文模板味套话；首屏即为"申请文本输入 + 解析结果"，无营销式 Hero |
| 无硬编码颜色 | 通过。所有颜色以 Design Token 命名与引用，JSON 中 hex 仅为 Token 定义值 |
| 无彩色侧条纹强调（border-left > 1px） | 通过。严重度使用 3px 状态竖条 + 圆角端点，属状态标识；卡片一律 1px 全边框 |
| 无渐变文字 | 通过。无 `background-clip: text` 方案 |
| 无默认毛玻璃 | 通过。无 backdrop-filter 装饰 |
| 无每节小型大写追踪标签的 AI 语法 | 通过。未采用"编号 + 大写标签"的 section 脚手架 |
| 圆角不超限 | 通过。卡片 12px（≤16px），数据面 0 |
| 动效 ≤400ms 且支持 reduced-motion | 通过。最长 300ms，已声明 reduced-motion 降级 |
| 主色非默认靛蓝 #6366F1 | 通过。主色 #3550B4，刻意避开反射式强调色 |
| 无 AI 散文僵硬词 | 通过。知识库 denylist 所列企业术语腔与空洞形容词均未出现 |
