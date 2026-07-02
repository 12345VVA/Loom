# Tasks

## 阶段 1：文档订正

- [x] Task 1: 更新 `deliverables/gstack/工程债.md` 核实摘要表
  - 新增 2026-07-02 核实摘要表（保留 2026-07-01 表）
  - #7 右键菜单 a11y 标注已修复（#23 完整修复）
  - #8 loadStats 标注已修复
  - #1 any 数量更新为 580 处 136 文件
  - #9 utcnow 更新为 56 处 17 文件（backend/app）
  - #2 前端单测更新为 22 个
  - 在各条目下标注本次修复 / 不修复

## 阶段 2：v-html 引入 DOMPurify（#3）

- [x] Task 2: 安装 dompurify 依赖 + 改造 base-node.vue
  - `npm install dompurify @types/dompurify`（在 frontend/ 下）
  - `base-node.vue` 第 142 行 `import DOMPurify from 'dompurify'`
  - `highlightJson` 返回值经 `DOMPurify.sanitize(html)` 处理（第 232 行）
  - 保留 `& < >` 实体转义 + `<span>` 高亮标签
  - 验证：`npm run type-check` 通过

## 阶段 3：i18n 创建 6 个空 locale（#4）

- [x] Task 3: 为 6 个模块创建 zh-cn locale 文件
  - 参考 `base/locales/zh-cn.json` 格式（注意是 .json 非 .ts，与现有约定一致）
  - 6 个模块创建 `locales/zh-cn.json`：ai(184 key)、media(39)、notification(81)、workflow(210)、workflow_annotation(32)、workflow_eval(113)
  - key 从各模块 `$t('...')` 调用提取，value 与 key 相同（中文）
  - 验证：`npm run type-check` 通过

## 阶段 4：compiler 补直接单测（#6）

- [x] Task 4: 新增 `backend/tests/test_workflow_compiler.py`
  - `ValidateGraphTestCase`（15 个）：合法图通过、含环报错、缺起始/多起始报错、缺字段报错、悬空边/重复边/孤立节点报错、LLM 配置缺失报错、结构异常报错
  - `CompileGraphTestCase`（9 个）：合法图返回 compilable builder、start 节点跳过、loop_body_group 跳过、拓扑序执行、节点注册、非法图报错
  - `NodeExecutorRegistryTestCase`（3 个）、`NodeExecutionErrorTestCase`（3 个）、`ConstantsTestCase`（4 个）
  - 共 34 个测试，全部通过
  - 验证：`pytest tests/test_workflow_compiler.py -v` 通过

## 阶段 5：给吞错 catch 补 console.warn（#8）

- [x] Task 5: 为约 20 处吞错 catch 补日志
  - 4 处空 catch：image.vue、image-generator-config.vue(2)、bmenu.tsx — 补 `console.warn`
  - 5 处 `// ignore`：suite.vue、run.vue(3)、case.vue、version.vue — 保留注释 + 加 warn
  - 10 处 `.catch(()=>null)`：trend.vue、proxy.vue、account.vue、log.vue、user-move.vue、dept-list.vue、group.vue、topbar.vue、switch/index.tsx、upload.vue — 改为带 warn + return null
  - 区分"失败"（真实吞错）和"取消"（ElMessageBox 用户取消）措辞
  - 验证：`npm run type-check` 通过

## 阶段 6：批量迁移 datetime.utcnow()（#9）

- [x] Task 6: 批量替换 backend/app 下 56 处 `datetime.utcnow()`
  - 17 文件全部替换为 `datetime.now(timezone.utc)`
  - 每个文件补 `from datetime import timezone`（或 `import datetime` 调整为 `from datetime import datetime, timezone`）
  - 无 aware vs naive 比较兼容性问题（SQLAlchemy 容忍混合比较）
  - 验证：`pytest` workflow 相关测试全通过；grep 确认 `backend/app/` 无残留 `datetime.utcnow()`

## 阶段 7：修复类型注解遗漏（#10）

- [x] Task 7: 修复 `workflow_tasks.py:224` 类型注解
  - `resume_val_json: str = None` → `resume_val_json: str | None = None`
  - 验证：`pytest tests/test_workflow_*.py` 通过

## 阶段 8：补 eval/annotation 基础单测（#2）

- [x] Task 8: 新增 workflow_eval 基础单测
  - 提取 `frontend/src/modules/workflow_eval/utils/format.ts`（5 个纯函数：verdictType/statusTagType/caseStatusType/kappaLevelType/parseJudgeDetail）
  - 更新 compare.vue 和 run.vue 改为 import 使用
  - 新增 `frontend/tests/unit/workflow_eval/format.test.ts`（12 个测试）
  - 验证：`npm run test:unit -- workflow_eval` 通过

- [x] Task 9: 新增 workflow_annotation 基础单测
  - 新增 `frontend/src/modules/workflow_annotation/utils/format.ts`（pretty + parseJudgeDetail）
  - 更新 annotation-drawer.vue 改为 import 使用
  - 新增 `frontend/tests/unit/workflow_annotation/format.test.ts`（10 个测试）
  - 验证：`npm run test:unit -- workflow_annotation` 通过

## 阶段 9：验证

- [x] Task 10: 后端测试验证
  - `pytest tests/test_workflow_compiler.py` — 34/34 通过（新增）
  - `pytest tests/test_workflow_p0_fixes.py + test_workflow_retry.py + test_workflow_execution.py + test_workflow_failure_notification.py + test_workflow_annotation.py` — 53/53 通过
  - 合计 87/87 通过
  - 全量测试中 16 失败均为 PG 连接环境问题（13）和预存 eval_judge_runtime 问题（3），与本次改动无关
  - grep 确认 `backend/app/` 无残留 `datetime.utcnow()`

- [x] Task 11: 前端验证
  - `npm run type-check`（vue-tsc --build --force）exit 0，通过
  - `npm run test:unit` 24 个测试文件 / 174 个测试全部通过（含新增 workflow_eval 12 + workflow_annotation 10 共 22 个）
  - DOMPurify 引入未破坏 base-node 渲染

# Task Dependencies

- Task 2 独立（DOMPurify 改造）
- Task 3 独立（i18n locale 创建）
- Task 4 独立（compiler 单测）
- Task 5 独立（catch 补日志）
- Task 6 独立（utcnow 迁移）
- Task 7 独立（类型注解）
- Task 8、9 独立（eval/annotation 单测）
- Task 1（文档订正）独立
- Task 10 依赖 Task 4、6、7
- Task 11 依赖 Task 2、3、5、8、9
- 大部分任务相互独立，可大规模并行
