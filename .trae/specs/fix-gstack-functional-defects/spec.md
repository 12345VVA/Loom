# 功能缺陷核实与修复 Spec

## Why

`deliverables/gstack/功能缺陷.md` 列出了 12 项功能缺陷（4 P0 / 4 P1 / 4 P2），其中部分条目标注为 2026-07-01 复核结果。在进入修复前，需要基于当前代码对每一项做最终核实，区分「已修复 / 描述不准确 / 真实存在」三类，并评估风险、收益、影响，从而制定聚焦、低风险的修复方案，避免对已闭环的模块做无谓改动，也避免一次性吞下产品级重构。

## 核实结果总表

| # | 缺陷 | P级 | 文档原描述 | 实际状态 | 处理方式 |
|---|------|-----|------------|----------|----------|
| 1 | 标注模块：上下文缺失 | P0 | 标注表单看不到 Prompt / AI Output | **已修复** | 文档订正 |
| 2 | 标注模块：流程断裂 | P0 | 标注独立菜单 + 手填 caseResultId | **已修复** | 文档订正 |
| 3 | LLM 降级策略未实现 | P0 | 工作流层未串联 fallback | **描述不准确** | 文档订正（已串联） |
| 4 | 自定义节点 SDK 缺失 | P0 | 15 种节点硬编码 | **真实存在** | 本次不修复（产品级重构，独立 spec） |
| 5 | 标注模块效率差距 6-12 倍 | P1 | CRUD 弹窗 30-60s/条 | **部分存在** | 本次修复（沉浸式队列） |
| 6 | 无可视化调试 | P1 | 无法直观看到错误节点 | **部分实现** | 本次修复（透传 failed_node_id + 节点错误展示） |
| 7 | 无告警通知 | P1 | 失败无主动通知 | **真实存在** | 本次修复（接入 NotificationService） |
| 8 | 无 Prompt 版本管理 | P1 | 无历史版本 / A/B | **真实存在** | 本次不修复（产品级重构，独立 spec） |
| 9 | 节点种类不足 | P2 | 缺 HTTP / Loop / DB Query | **部分存在** | 本次不修复（中复杂度，优先级低） |
| 10 | 配置面板不可拖拽 | P2 | 固定 420px | **已修复** | 文档订正 |
| 11 | MiniMap 始终显示 | P2 | 无显隐开关 | **已修复** | 文档订正 |
| 12 | 无灰度发布 | P2 | 直接到生产 | **真实存在** | 本次不修复（影响核心发布流程，独立 spec） |

## 评估：风险 / 收益 / 影响

### 本次修复项（低风险、高收益、改动聚焦）

**#6 可视化调试补全**
- 收益：失败时前端可直接定位失败节点并看到错误原因，调试效率显著提升
- 风险：低。仅扩展 DTO 字段、SSE 事件 payload、前端节点浮层渲染
- 影响：`WorkflowInstanceRead` DTO 加 `failedNodeId`；SSE `failed` 事件加 `node_id`；`base-node.vue` 错误展示；`instance.vue` 行展示失败节点
- 验证：现有 SSE / 试运行 / 实例列表测试需通过；新增失败节点透传单测

**#7 告警通知接入**
- 收益：工作流失败/超时时主动发站内信，运维响应更快
- 风险：低。参考 `task/tasks/system_tasks.py:121` 已有的 `send_task` 接入方式
- 影响：`workflow_tasks.py` 失败分支调用 `NotificationService(session).send_business(...)`；新增通知模板 `workflow.failed`
- 验证：失败路径触发通知的单测；模板初始化幂等

**#5 标注沉浸式队列**
- 收益：标注 500 条从 4-8 小时降至 1-2 小时（键盘快捷键 + 流式导航）
- 风险：中。改的是 `annotation-drawer.vue` 单文件，但需要新增队列游标状态 + 全局 keydown 监听 + 抽屉不关闭连续标注
- 影响：`annotation-drawer.vue` 接收 `caseResults` 数组 + `initialIndex`，新增 prev/next 按钮 + 快捷键（J/K 切换、F=Fail、P=Pass、Enter 提交并下一条）；`run.vue` 透传筛选后的用例结果数组
- 验证：手动验证连续标注流程；现有 κ 算法测试通过

### 本次不修复项（高复杂度或低优先级）

**#4 自定义节点 SDK（P0，真实存在）**
- 不修复原因：产品级重构，需设计 BaseNode 接口、插件发现机制、前端动态加载、文档化 SDK；改动覆盖前后端核心架构
- 风险评估：在本轮一并做会显著扩大 blast radius，且需要独立的产品决策（支持 Python 插件？HTTP webhook？沙箱？）
- 后续：建议单独立 spec

**#8 Prompt 版本管理（P1，真实存在）**
- 不修复原因：需新建 Prompt 实体表 + 版本表 + A/B 实验表 + 前端 Prompt 工作室；涉及数据模型新增和 AI 模块重构
- 风险评估：影响面广，与现有 `AiModelProfile` / 工作流节点 config 的 prompt 字段关系需重新设计
- 后续：建议单独立 spec

**#12 灰度发布（P2，真实存在）**
- 不修复原因：需在 `WorkflowDefinition` 主表加 `canary_version_id` / `canary_percent`，在实例启动路由处按比例分流；改动核心发布流程
- 风险评估：发布是核心流程，灰度逻辑出错会影响所有新启动实例；现有版本管理 + 回滚机制已能覆盖大部分场景
- 后续：建议单独立 spec

**#9 HTTP / DB Query 节点（P2，部分存在）**
- 不修复原因：Loop 已齐全；HTTP / DB Query 节点是中复杂度新增功能，优先级低于本次修复项
- 风险评估：HTTP 节点涉及 SSRF/超时/认证等安全考量；DB Query 节点涉及连接池、SQL 注入、权限
- 后续：建议单独立 spec

### 文档订正项（仅改 `功能缺陷.md`）

- #1、#2：标注模块已闭环，需更新状态
- #3：LLM 降级已串联，需更新描述
- #10、#11：已修复，文档已标注 ✅，复核确认
- #4：节点数 15（与文档 2026-07-01 修订一致），但「自定义节点 SDK 缺失」结论保留
- 节点清单：Loop 已存在，HTTP / DB Query 缺失

## What Changes

### 文档订正
- **MODIFIED** `deliverables/gstack/功能缺陷.md`：更新核实摘要表，标注 #1/#2 已修复、#3 描述不准确（已串联）、本次修复项与不修复项的分类

### 可视化调试补全（#6）
- **ADDED** `WorkflowInstanceRead` DTO 透传 `failedNodeId`
- **MODIFIED** SSE `failed` 事件 payload 携带 `node_id`
- **MODIFIED** `base-node.vue` 节点浮层展示错误信息
- **MODIFIED** `instance.vue` 实例列表行展示失败节点标识
- **MODIFIED** `useWorkflowTest.ts` 处理失败事件时定位到失败节点

### 告警通知接入（#7）
- **ADDED** 通知模板 `workflow.failed` 初始化（幂等）
- **MODIFIED** `workflow_tasks.py` 失败分支调用 `NotificationService.send_business`
- **ADDED** 失败通知触发单测

### 标注沉浸式队列（#5）
- **MODIFIED** `annotation-drawer.vue` 接收队列数据，新增 prev/next 导航 + 键盘快捷键
- **MODIFIED** `run.vue` 透传筛选后的用例结果数组到抽屉
- **ADDED** 连续标注流程验证

## Impact

- **Affected specs**: 无（项目无既有 spec 文档）
- **Affected code**:
  - 后端：`backend/app/modules/workflow/model/workflow.py`、`backend/app/modules/workflow/tasks/workflow_tasks.py`、`backend/app/modules/notification/`（模板初始化）
  - 前端：`frontend/src/modules/workflow/views/instance.vue`、`components/custom-nodes/base-node.vue`、`composables/useWorkflowTest.ts`、`frontend/src/modules/workflow_annotation/views/annotation-drawer.vue`、`frontend/src/modules/workflow_eval/views/run.vue`
  - 文档：`deliverables/gstack/功能缺陷.md`

## ADDED Requirements

### Requirement: 工作流失败节点透传

The system SHALL 在工作流实例失败时，将 `failed_node_id` 通过 `WorkflowInstanceRead` DTO 和 SSE `failed` 事件透传到前端，使前端能直接定位失败节点。

#### Scenario: 工作流执行失败
- **WHEN** 工作流节点执行抛出 `NodeExecutionError`，实例被 CAS 为 failed
- **THEN** `WorkflowInstanceRead` DTO 包含 `failedNodeId` 字段
- **AND** SSE `failed` 事件 payload 包含 `node_id` 字段
- **AND** 前端 `instance.vue` 列表行展示失败节点 ID
- **AND** 试运行画布上失败节点高亮且浮层显示错误原因

### Requirement: 工作流失败通知

The system SHALL 在工作流实例失败（含超时）时，通过 `NotificationService` 发送站内信给工作流所有者，通知模板 code 为 `workflow.failed`。

#### Scenario: 工作流执行失败触发通知
- **WHEN** 工作流实例 status CAS 为 failed
- **THEN** 系统调用 `NotificationService(session).send_business(...)` 发送站内信
- **AND** 通知接收人为 `WorkflowInstance.created_by`
- **AND** 通知内容包含工作流名称、实例 ID、失败节点、错误摘要
- **AND** 通知模板 `workflow.failed` 通过模块初始化幂等创建

#### Scenario: 通知服务异常不阻断主流程
- **WHEN** 通知发送本身抛异常
- **THEN** 仅记录 warning 日志，不影响实例终态写入和 SSE 推送

### Requirement: 标注沉浸式队列

The system SHALL 在评测运行详情页的标注抽屉中，支持连续标注多条用例结果，提供上一条/下一条导航和键盘快捷键。

#### Scenario: 连续标注
- **GIVEN** 评测运行详情页用例结果表格已筛选
- **WHEN** 用户点击某行「标注」打开抽屉
- **THEN** 抽屉接收当前筛选后的用例结果数组与初始索引
- **AND** 抽屉底部展示「上一条 / 下一条 (索引/总数)」按钮
- **AND** 键盘快捷键：`P`=Pass、`F`=Fail、`J`/`→`=下一条、`K`/`←`=上一条、`Enter`=提交并下一条
- **AND** 提交后自动跳到下一条；已是最后一条则提示并关闭

#### Scenario: 快捷键不与输入框冲突
- **WHEN** 焦点在分数 / 理由输入框内
- **THEN** 单字母快捷键不触发，仅 Enter 提交生效

## MODIFIED Requirements

### Requirement: 功能缺陷文档核实状态

`deliverables/gstack/功能缺陷.md` 的核实摘要表 SHALL 反映 2026-07-02 的最终核实结果：
- #1 标注上下文缺失 → ✅ 已修复（annotation-drawer 完整展示上下文）
- #2 标注流程断裂 → ✅ 已修复（run.vue 自动注入 caseResultId）
- #3 LLM 降级未串联 → 🟡 描述不准确（已串联：所有 LLM 节点通过 `run_ai_chat` / `run_ai_image` 桥接，自动继承降级链）
- #4 自定义节点 SDK 缺失 → 真实存在，本次不修复
- #5 标注效率差距 → 部分存在，本次修复
- #6 无可视化调试 → 部分实现，本次修复
- #7 无告警通知 → 真实存在，本次修复
- #8 无 Prompt 版本管理 → 真实存在，本次不修复
- #9 节点种类不足 → 部分存在（Loop 齐全，缺 HTTP/DB Query），本次不修复
- #10/#11 → ✅ 已修复（保留）
- #12 无灰度发布 → 真实存在，本次不修复
