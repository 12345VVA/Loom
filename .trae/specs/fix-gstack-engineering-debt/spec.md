# 工程债核实与修复 Spec

## Why

`deliverables/gstack/工程债.md` 列出了 10 项工程债（3 P0 / 3 P1 / 4 P2），文档标注为 2026-07-01 复核状态。在进入修复前，需要基于当前代码（2026-07-02）对每一项做最终核实，区分「已修复 / 描述过时 / 真实存在」三类，并评估风险、收益、影响，制定聚焦、低风险的修复方案，避免对已闭环问题做无谓改动，也避免一次性吞下大规模重构（如 580 处 any 收敛、全局 ARIA 改造）。

## 核实结果总表

| # | 工程债 | P级 | 文档原状态 | 2026-07-02 实际状态 | 处理方式 |
|---|--------|-----|------------|---------------------|----------|
| 1 | 类型安全不足（`: any`）| P0 | 528 处 127 文件 | **580 处 136 文件**（增 52），`noImplicitAny=false` 仍成立 | 本次不修复（量大，需分批收敛） |
| 2 | 测试覆盖率偏低 | P0 | 12 个前端单测，eval/annotation 零覆盖 | **22 个前端单测**（workflow 16+ai 1+base 3+dict 1+cool 1），eval/annotation 仍零覆盖 | 本次修复（补 eval/annotation 基础单测） |
| 3 | v-html 无 DOMPurify | P0 | base-node.vue:95,106 仍存在 | base-node.vue:105,116（行号偏移），仍 2 处，无 DOMPurify | 本次修复（引入 DOMPurify） |
| 4 | 国际化缺失 6/9 模块 | P1 | 缺 ai/media/notification/workflow/workflow_annotation/workflow_eval | **仍成立**，但模块已大量使用 `$t()`，仅缺 locale 文件 | 本次修复（创建 6 个空 zh-cn locale） |
| 5 | ESLint 规则过松 | P1 | 三条已收紧为 warn | 仍为 warn，未升 error | 文档订正（保留 warn，不升 error） |
| 6 | compiler 测试覆盖 ~11% | P1 | compile_graph/validate_graph 无直接单测 | **仍成立**，仅 node_runner 有 8 个测试（test_workflow_retry.py） | 本次修复（补 compile_graph/validate_graph 直接单测） |
| 7 | 可访问性几乎为零 | P2 | 右键菜单无 tabindex/方向键 | **部分已修复**：右键菜单 #23 已完整修复（tabindex + 方向键 + Enter/Space + Escape）；全局 ARIA 仍仅 6 文件含 aria- | 文档订正右键菜单部分；全局 ARIA 本次不修复 |
| 8 | 错误处理不一致 | P2 | loadStats 静默失败 | **loadStats 已修复**（catch 中有 ElMessage.error）；但仍约 20 处吞错 catch 无日志 | 本次修复（给 20 处吞错补 console.warn） |
| 9 | `datetime.utcnow()` 弃用 | P2 | 66 处 21 文件 | backend/app 下 **56 处 17 文件**（不含 tests） | 本次修复（批量迁移 datetime.now(timezone.utc)） |
| 10 | 类型注解遗漏 | P2 | workflow_tasks.py:185 `str = None` | workflow_tasks.py:224 仍存在 `resume_val_json: str = None` | 本次修复（改 `str | None`） |

## 评估：风险 / 收益 / 影响

### 本次修复项（低风险、高收益、改动聚焦）

**#3 v-html 引入 DOMPurify**
- 收益：消除 XSS 风险，安全收敛
- 风险：低。仅 base-node.vue 2 处，DOMPurify 是成熟库
- 影响：新增 `dompurify` 依赖；`highlightJson` 返回值经 `DOMPurify.sanitize()` 处理
- 验证：type-check + 现有 workflow 测试

**#4 i18n 创建 6 个空 locale**
- 收益：为 6 个模块的 i18n 键提供 fallback 文件，避免 `$t()` 显示 key 本身
- 风险：极低。仅新增空文件
- 影响：6 个模块各新增 `locales/zh-cn.ts`（含已用到的 key 的中文翻译）
- 验证：type-check + 启动时 locale 加载

**#6 compiler 补直接单测**
- 收益：compile_graph / validate_graph 核心路径有直接测试覆盖
- 风险：低。仅新增测试文件
- 影响：新增 `test_workflow_compiler.py`，覆盖图校验、编译、节点注册
- 验证：pytest 通过

**#8 给吞错 catch 补 console.warn**
- 收益：调试时可追踪，不再静默
- 风险：极低。仅在 catch 块加日志
- 影响：约 20 处 catch 块（4 空 catch + 5 `// ignore` + 10 `.catch(()=>null)` + 1 兜底）
- 验证：type-check

**#9 批量迁移 datetime.utcnow()**
- 收益：消除 Python 3.12+ 弃用警告，统一时区意识
- 风险：低。机械替换 `datetime.utcnow()` → `datetime.now(timezone.utc)`，语义等价
- 影响：backend/app 下 56 处 17 文件
- 验证：pytest 全量测试

**#10 修复类型注解遗漏**
- 收益：类型正确性
- 风险：极低。一行修复
- 影响：`workflow_tasks.py:224` `str = None` → `str | None`
- 验证：pytest

**#2 补 eval/annotation 基础单测**
- 收益：破零，建立测试基础
- 风险：低。仅新增测试文件
- 影响：新增 eval/annotation 基础工具函数单测
- 验证：vitest 通过

### 本次不修复项（高复杂度或影响面广）

**#1 类型安全 580 处 any（P0）**
- 不修复原因：580 处分布在 136 文件，分批收敛需逐文件审查类型；`noImplicitAny=true` 开启会一次性产生海量类型错误
- 风险评估：在本轮一并做会显著扩大 blast radius，且需对每个 any 推断正确类型
- 后续：建议单独立 spec，按模块分批收敛

**#7 全局 ARIA 缺失（P2）**
- 不修复原因：a11y 改造是独立工程，涉及表单 aria-required、模态 aria-modal、动态消息 live region、skip-link 等
- 风险评估：影响面广，需系统性设计
- 后续：建议单独立 spec

**#5 ESLint 升 error（P1）**
- 不修复原因：升 error 前需先清理 580 处 any 违规和 2 处 v-html 违规
- 风险评估：升 error 会导致 build 失败
- 后续：待 #1 any 收敛后升级

### 文档订正项（仅改 `工程债.md`）

- #5 ESLint：保留 warn，不升 error
- #7 右键菜单 a11y：已修复，文档过时
- #8 loadStats：已修复，文档过时

## What Changes

### 文档订正
- **MODIFIED** `deliverables/gstack/工程债.md`：更新核实摘要表，标注 #7 右键菜单已修复、#8 loadStats 已修复、本次修复项与不修复项分类

### v-html 引入 DOMPurify（#3）
- **ADDED** `dompurify` 依赖 + `@types/dompurify`
- **MODIFIED** `base-node.vue` `highlightJson` 返回值经 `DOMPurify.sanitize()` 处理

### i18n 创建 6 个空 locale（#4）
- **ADDED** 6 个模块 `locales/zh-cn.ts`（ai / media / notification / workflow / workflow_annotation / workflow_eval）
- 含已用到的 key 的中文翻译（从 vue 文件中提取 `$t('...')` 的 key）

### compiler 补直接单测（#6）
- **ADDED** `backend/tests/test_workflow_compiler.py`（compile_graph / validate_graph 直接单测）

### 给吞错 catch 补 console.warn（#8）
- **MODIFIED** 约 20 处 catch 块（4 空 catch + 5 `// ignore` + 10 `.catch(()=>null)` + 1 兜底）

### 批量迁移 datetime.utcnow()（#9）
- **MODIFIED** `backend/app/` 下 17 文件 56 处 `datetime.utcnow()` → `datetime.now(timezone.utc)`

### 修复类型注解遗漏（#10）
- **MODIFIED** `workflow_tasks.py:224` `str = None` → `str | None`

### 补 eval/annotation 基础单测（#2）
- **ADDED** `frontend/tests/unit/workflow_eval/` 基础单测
- **ADDED** `frontend/tests/unit/workflow_annotation/` 基础单测

## Impact

- **Affected specs**: 无
- **Affected code**:
  - 前端：`frontend/src/modules/workflow/components/custom-nodes/base-node.vue`、6 个模块的 `locales/zh-cn.ts`、约 20 处 catch 块、新增 eval/annotation 测试
  - 后端：`backend/app/` 17 文件（utcnow 迁移）、`backend/app/modules/workflow/tasks/workflow_tasks.py`（类型注解）、新增 `backend/tests/test_workflow_compiler.py`
  - 依赖：`frontend/package.json` 新增 `dompurify` + `@types/dompurify`
  - 文档：`deliverables/gstack/工程债.md`

## ADDED Requirements

### Requirement: v-html XSS 防护

The system SHALL 在使用 `v-html` 渲染前，通过 `DOMPurify.sanitize()` 对 HTML 内容进行净化，防止 XSS 攻击。

#### Scenario: v-html 渲染前净化
- **WHEN** `base-node.vue` 的 `highlightJson()` 返回 HTML 字符串
- **THEN** 该字符串经 `DOMPurify.sanitize()` 处理后才绑定到 `v-html`
- **AND** 保留 JSON 语法高亮的 `<span>` 标签，剥离 `<script>` / `<iframe>` 等危险标签

### Requirement: 工作流模块 i18n locale

The system SHALL 为 ai / media / notification / workflow / workflow_annotation / workflow_eval 6 个模块提供 `zh-cn` locale 文件，包含模块内已使用的所有 `$t()` key 的中文翻译。

#### Scenario: 缺失模块 locale 加载
- **WHEN** 应用启动加载模块 locale
- **THEN** 6 个模块的 `locales/zh-cn.ts` 被加载
- **AND** 模块内 `$t('key')` 调用返回中文翻译而非 key 本身

### Requirement: compiler 直接单测覆盖

The system SHALL 为 `WorkflowCompiler.compile_graph` 和 `validate_graph` 提供直接单元测试，覆盖图校验、编译、节点注册等核心路径。

#### Scenario: compile_graph 单测
- **GIVEN** 合法的 graph_json
- **WHEN** 调用 `compile_graph`
- **THEN** 返回可执行的 node_runner
- **AND** 节点按拓扑序排列

#### Scenario: validate_graph 单测
- **GIVEN** 含环 / 缺起始节点 / 缺字段等非法 graph_json
- **WHEN** 调用 `validate_graph`
- **THEN** 抛出明确的校验错误

### Requirement: 错误处理可追踪

The system SHALL 在前端 catch 块中至少记录 `console.warn` 日志，避免静默吞错导致调试困难。

#### Scenario: catch 块记录日志
- **WHEN** 任何 catch 块捕获异常
- **THEN** 至少调用 `console.warn(error)` 记录异常
- **AND** 不破坏现有兜底降级逻辑

### Requirement: datetime 时区意识

The system SHALL 使用 `datetime.now(timezone.utc)` 替代已弃用的 `datetime.utcnow()`，统一时区意识 datetime。

#### Scenario: utcnow 迁移
- **WHEN** 后端代码需要获取当前 UTC 时间
- **THEN** 使用 `datetime.now(timezone.utc)`
- **AND** 不再出现 `datetime.utcnow()` 调用

### Requirement: 类型注解正确

The system SHALL 在函数签名中为可空参数使用 `T | None` 而非 `T = None`。

#### Scenario: 可空参数类型
- **WHEN** 函数参数可为 None
- **THEN** 类型注解为 `str | None`（或其他类型）
- **AND** 默认值为 `None`

### Requirement: eval/annotation 基础单测

The system SHALL 为 workflow_eval 和 workflow_annotation 模块的基础工具函数提供单元测试，破除零覆盖。

#### Scenario: eval 基础单测
- **GIVEN** workflow_eval 模块的纯函数工具
- **WHEN** 运行 vitest
- **THEN** 基础工具函数被测试覆盖

## MODIFIED Requirements

### Requirement: 工程债文档核实状态

`deliverables/gstack/工程债.md` 的核实摘要表 SHALL 反映 2026-07-02 的最终核实结果：
- #1 类型安全 580 处 any → 真实存在，本次不修复（量大，独立 spec）
- #2 测试覆盖率 → 前端单测 22 个（增 10），eval/annotation 仍零覆盖，本次修复（破零）
- #3 v-html 无 DOMPurify → 仍存在，本次修复（引入 DOMPurify）
- #4 i18n 缺失 6 模块 → 仍存在，本次修复（创建空 locale）
- #5 ESLint 规则 → 保留 warn，不升 error
- #6 compiler 覆盖 ~11% → compile_graph/validate_graph 无直接单测，本次修复
- #7 可访问性 → 右键菜单已修复（#23），全局 ARIA 仍缺，本次不修复全局 ARIA
- #8 错误处理 → loadStats 已修复，约 20 处吞错仍存，本次修复（补 console.warn）
- #9 datetime.utcnow() → 56 处 17 文件（backend/app），本次修复（批量迁移）
- #10 类型注解遗漏 → workflow_tasks.py:224 仍存，本次修复
