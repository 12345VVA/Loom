# Checklist

## 阶段 1：文档订正
- [x] `工程债.md` 新增 2026-07-02 核实摘要表（保留 2026-07-01 表）
- [x] `工程债.md` #7 右键菜单 a11y 标注已修复（#23）
- [x] `工程债.md` #8 loadStats 标注已修复
- [x] `工程债.md` #1 any 数量更新为 580 处 136 文件
- [x] `工程债.md` #9 utcnow 更新为 56 处 17 文件
- [x] `工程债.md` #2 前端单测更新为 22 个
- [x] `工程债.md` 各条目标注本次修复 / 不修复

## 阶段 2：v-html 引入 DOMPurify（#3）
- [x] `dompurify` + `@types/dompurify` 依赖已安装
- [x] `base-node.vue` 的 `highlightJson` 返回值经 `DOMPurify.sanitize()` 处理（第 232 行）
- [x] 保留 JSON 语法高亮的 `<span>` 标签
- [x] `npm run type-check` 通过

## 阶段 3：i18n 创建 6 个空 locale（#4）
- [x] `frontend/src/modules/ai/locales/zh-cn.json` 已创建（184 key）
- [x] `frontend/src/modules/media/locales/zh-cn.json` 已创建（39 key）
- [x] `frontend/src/modules/notification/locales/zh-cn.json` 已创建（81 key）
- [x] `frontend/src/modules/workflow/locales/zh-cn.json` 已创建（210 key）
- [x] `frontend/src/modules/workflow_annotation/locales/zh-cn.json` 已创建（32 key）
- [x] `frontend/src/modules/workflow_eval/locales/zh-cn.json` 已创建（113 key）
- [x] 每个 locale 文件含模块内已使用的 `$t()` key 的中文翻译
- [x] locale 文件导出格式与 `base/locales/zh-cn.json` 一致（.json 非 .ts）
- [x] `npm run type-check` 通过

## 阶段 4：compiler 补直接单测（#6）
- [x] `backend/tests/test_workflow_compiler.py` 已创建
- [x] `validate_graph` 单测覆盖：合法图通过、含环报错、缺起始/多起始报错、缺字段报错、悬空边/重复边/孤立节点/LLM 配置缺失/结构异常报错（15 个测试）
- [x] `compile_graph` 单测覆盖：合法图返回 compilable builder、start 跳过、loop_body_group 跳过、拓扑序执行、节点注册（9 个测试）
- [x] `pytest tests/test_workflow_compiler.py -v` 通过（34/34）

## 阶段 5：给吞错 catch 补 console.warn（#8）
- [x] 4 处空 catch 已补 `console.warn`（image.vue、image-generator-config.vue×2、bmenu.tsx）
- [x] 5 处 `// ignore` 已补 `console.warn`（suite.vue、run.vue×3、case.vue、version.vue）
- [x] 10 处 `.catch(()=>null)` 已补日志（trend.vue、proxy.vue、account.vue、log.vue、user-move.vue、dept-list.vue、group.vue、topbar.vue、switch/index.tsx、upload.vue）
- [x] 现有兜底降级逻辑未破坏
- [x] `npm run type-check` 通过

## 阶段 6：批量迁移 datetime.utcnow()（#9）
- [x] `backend/app/` 下 17 文件 56 处 `datetime.utcnow()` 已替换为 `datetime.now(timezone.utc)`
- [x] 每个文件已导入 `timezone`（如未导入则补）
- [x] `pytest` workflow 相关测试通过（87/87）
- [x] grep 确认 `backend/app/` 下无残留 `datetime.utcnow()`（0 处）

## 阶段 7：修复类型注解遗漏（#10）
- [x] `workflow_tasks.py:224` `str = None` → `str | None = None`
- [x] `pytest tests/test_workflow_*.py` 通过

## 阶段 8：补 eval/annotation 基础单测（#2）
- [x] `frontend/src/modules/workflow_eval/utils/format.ts` 已创建（5 个纯函数）
- [x] `frontend/tests/unit/workflow_eval/format.test.ts` 已创建（12 个测试）
- [x] `frontend/src/modules/workflow_annotation/utils/format.ts` 已创建（2 个纯函数）
- [x] `frontend/tests/unit/workflow_annotation/format.test.ts` 已创建（10 个测试）
- [x] `npm run test:unit` 通过（174/174，含新增 22 个）

## 阶段 9：验证
- [x] `pytest tests/test_workflow_compiler.py` 通过（34/34）
- [x] `pytest tests/test_workflow_*.py` 通过（87/87 合计）
- [ ] `pytest tests/` 全量通过 — 16 失败均为 PG 连接环境问题（13）和预存 eval_judge_runtime 问题（3），与改动无关
- [x] `npm run type-check` 通过
- [x] `npm run test:unit` 通过（24 文件 / 174 测试）
- [x] grep 确认 `backend/app/` 无残留 `datetime.utcnow()`（0 处）
- [x] grep 确认 `frontend/src/modules/workflow/components/custom-nodes/base-node.vue` 的 v-html 经 DOMPurify 净化
