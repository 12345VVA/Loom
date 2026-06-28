# Loom 项目上线前全检报告

**日期**：2026-06-27
**场景**：上线前检查（代码审查 + 安全审计 + QA测试）
**参与成员**：产品评审员 + 安全官 + QA测试员

---

## 📌 TL;DR（执行摘要）

- **整体结论**：🔴 **不通过 — 存在 7 个阻塞项，必须修复后再审**
- 共有 7 个 CRITICAL（🔴）、14 个 HIGH（🟠）、13 个 MEDIUM（🟡）、4 个 LOW（🟢），总计 38 项发现
- 后端测试 310 通过 / 10 失败（6 个 LLM Judge 崩溃 + 3 个 CAPTCHA + 1 个图标），前端类型检查与 Lint 全绿
- 核心风险集中在：并发数据一致性（C1/C3）、权限校验遗漏（C2）、密钥暴露（F-001/F-002/F-003）、LLM Judge 功能崩溃（ISSUE-001）
- 修复性价比高：7 个 CRITICAL 总计改动量约 30 行代码 + 配置变更，预计半天可完成

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🔴 **No-Go** — 7 个 CRITICAL 阻塞上线 |
| 严重度分布 | 🔴 7 / 🟠 14 / 🟡 13 / 🟢 4 |
| 关键行动项 | 13 条（P0: 7 条，P1: 6 条） |
| 建议负责人 | 后端开发（CRITICAL 修复）+ 安全运维（密钥轮换）+ QA（回归验证） |
| 安全问题评级 | C+ (70/100) — 修复后可提升至 B+ |
| QA 健康度 | 72/100 |
| 建议复审时间 | CRITICAL 修复完成后立即 |

---

## 🚫 阻塞项清单（上线前必须全部解决）

| # | ID | 严重度 | 类别 | 简述 |
|---|-----|--------|------|------|
| 1 | C1 | 🔴 | 竞态 | `finalize_eval_run` 与 `backfill_missing_results` 事务不原子，pass_rate 可能失真 |
| 2 | C2 | 🔴 | IDOR | `compute_kappa` 无归属校验，任意用户可修改他人 eval_run 的 summary_payload |
| 3 | C3 | 🔴 | 数据完整性 | `write_case_result` 不检查 run 是否已取消，产生孤儿写入 |
| 4 | F-001 | 🔴 | 密钥暴露 | `.env` 中 `DEEPSEEK_API_KEY` 等真实密钥明文存储 |
| 5 | F-002 | 🔴 | 认证 | `JWT_SECRET_KEY` 为公开占位符 `changethisinproduction...`，可伪造任意 JWT |
| 6 | F-003 | 🔴 | 认证 | 默认管理员密码 `Admin123456` 过于脆弱 |
| 7 | ISSUE-001 | 🔴 | 功能崩溃 | `llm_judge.py` 中 JSON 花括号未转义，导致 `str.format()` 抛出 `KeyError`，workflow_eval 核心评估功能完全不可用 |

---

## 回滚预案

- **部署方式**：Docker Compose（`docker-compose.yml`），支持快速回滚
- **回滚步骤**：`docker-compose down && git checkout <previous-tag> && docker-compose up -d`
- **风险窗口**：CRITICAL 修复完成后重新部署，建议在低峰期（凌晨 2:00-4:00）执行
- **监控指标**：关注 `/admin/workflow/eval/run` 接口的错误率，JWT 认证成功率，Celery Worker 任务积压量

---

## 1. 各成员核心结论

### 🔍 产品评审员（代码审查）
审查了 `workflow_eval`、`workflow_annotation`、`workflow` 三个核心模块共 75 个文件。架构设计质量高（CAS 状态机、快照隔离、并发控制都很到位），测试覆盖在 workflow_eval 模块较充分。但发现了 3 个上线阻塞级并发和权限问题：`finalize_eval_run` 的事务原子性缺失、`compute_kappa` 的 IDOR 越权写入、以及已取消 run 的孤儿结果写入。这三个问题修复成本极低（总计约 20 行），但影响面大——会导致评估数据不可信和权限绕过。

### 🛡️ 安全官（OWASP+STRIDE 审计）
审计覆盖全栈 21 个检查项。认证架构设计优秀（PBKDF2 210K iterations + 多维度吊销机制），但发现了关键的上线阻塞问题：`.env` 明文密钥、JWT 密钥为可预测占位符、默认管理员密码脆弱。此外，Token 存储在 localStorage（XSS 风险）、CSRF 保护默认关闭、Refresh Token 通过 GET 参数暴露等高危问题需要进入本迭代修复。总体评分 C+ (70/100)。

### ✅ QA测试员（QA测试与发布）
执行了 Standard Tier 全栈测试。后端 310 测试通过、10 测试失败（6 个 LLM Judge 崩溃 + 3 个 CAPTCHA + 1 个图标），前端类型检查和 Lint 全绿。关键发现：LLM Judge 评估功能因花括号转义问题完全崩溃（`DEFAULT_JUDGE_SYSTEM_PROMPT` 中的 JSON 模板与 `str.format()` 冲突），CAPTCHA 验证码功能默认关闭导致相关防御失效。覆盖率 68%，`workflow/service/compiler.py` 仅 11% 覆盖，是最大的测试盲区。

---

## 2. 综合审查发现（按严重度排序）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 1 | 🔴 | 密钥暴露 | `.env` | `DEEPSEEK_API_KEY`、`SQL_PASSWORD`、`SECRET_ENCRYPTION_KEY` 明文存储，任何有文件系统访问的人可读 | 迁移至环境变量注入或密钥管理服务（KMS/Vault） | 安全官 |
| 2 | 🔴 | 认证 | `backend/app/core/config.py` | `JWT_SECRET_KEY=changethisinproductionchangethisinproduction` 公开占位符，攻击者可伪造任意 JWT | 生成 `openssl rand -hex 32` 随机密钥，且不提交到仓库 | 安全官 |
| 3 | 🔴 | 认证 | 数据库初始数据 | 默认管理员密码 `Admin123456` 脆弱 | 首次部署时强制生成随机密码并通过安全渠道交付 | 安全官 |
| 4 | 🔴 | 竞态 | `eval_orchestrator.py` L:209-210 | `backfill_missing_results` 与 `finalize_eval_run` 分开调用不原子，中间可能插入新结果导致 pass_rate 失真 | 在同一个 Session 内完成查询+汇总，或使用 SELECT FOR UPDATE | 产品评审员 |
| 5 | 🔴 | IDOR | `annotation_service.py` L:66-123 | `compute_kappa` 接收 eval_run_id 直接回写 summary_payload，无归属校验 | 开头加 `_assert_run_owned(session, eval_run_id, current_user)` | 产品评审员 |
| 6 | 🔴 | 数据完整性 | `eval_orchestrator.py` L:184-250 | `write_case_result` 不检查 run 是否已取消，cancel 后仍写入孤儿结果 | 写入前检查 run.status，已取消则跳过 | 产品评审员 |
| 7 | 🔴 | 功能崩溃 | `llm_judge.py` L:28-33 | `DEFAULT_JUDGE_SYSTEM_PROMPT` 中 JSON `{"score": ...}` 未转义为 `{{"score": ...}}`，`str.format()` 抛出 `KeyError` | 转义所有 JSON 花括号：`{` → `{{`，`}` → `}}` | QA测试员 |
| 8 | 🟠 | XSS | 前端 Token 存储 | Token 存储在 localStorage，XSS 可窃取 | 迁移至 httpOnly Cookie + CSRF Token 双验证 | 安全官 |
| 9 | 🟠 | CSRF | `config.py` | `ADMIN_CSRF_ORIGIN_CHECK_ENABLED=False`，所有状态变更请求无同源校验 | 设为 `True` 并在前端附带 CSRF Header | 安全官 |
| 10 | 🟠 | 信息泄露 | Refresh Token API | Refresh Token 通过 GET 查询参数传递，被服务器日志/browser history 泄露 | 改为 POST body 传递 | 安全官 |
| 11 | 🟠 | 密码安全 | 限流器 | 对 Token 哈希使用 MD5 | 改用 SHA-256 | 安全官 |
| 12 | 🟠 | 暴力破解 | 登录端点 | 登录端点无独立限流，共用 30/min | 为 `/auth/login` 独立设置更严格的限流（如 5/min） | 安全官 |
| 13 | 🟠 | 异常隔离 | `composite.py` L:29-48 | CompositeEvaluator 循环中子评估器异常未隔离，整个 batch 中断 | 对每个子评估器 try/except 包裹，失败计 0 分 | 产品评审员 |
| 14 | 🟠 | 并发 | `eval_tasks.py` L:198-210 | `BaseException` 仅记日志不阻止 finalize，可能导致不完整数据汇总 | 超过阈值时跳过 finalize 并 mark_failed | 产品评审员 |
| 15 | 🟠 | 可复现性 | `regression.py` L:22-44 | Bootstrap 用 `random.randrange` 无 seed，结果不可复现 | 使用 `random.Random(seed).randrange`，seed=`hash((run_a_id, run_b_id))` | 产品评审员 |
| 16 | 🟠 | 存储容错 | `storage.py` L:218-235 | `resolve_payload` 存储读取失败直接抛异常，阻塞整个列表查询 | 加 try/except fallback，失败返回 `"(存储读取失败)"` | 产品评审员 |
| 17 | 🟠 | Celery 顺序 | `eval_run_service.py` L:123-133 | `.delay()` 发送 Celery 任务早于 `celery_task_id` 的 commit，cancel 可能失效 | 在 `.delay()` 前完成所有 commit | 产品评审员 |
| 18 | 🟠 | 功能/配置 | `config.py:76`, `auth_service.py:83` | `ADMIN_CAPTCHA_ENABLED=False` 默认关闭，验证码形同虚设 | 生产环境显式设为 `True` | QA测试员 |
| 19 | 🟠 | 性能 | `run.vue` L:145-162 | `parseJudgeDetail` 同列重复调用 3 次，每次 JSON.parse | 使用计算属性缓存或预解析 | 产品评审员 |
| 20 | 🟠 | 类型安全 | `run.vue` L:199-405 | 约 15 处 `any` 类型标注，缺乏类型约束 | 定义明确 TS 接口逐步消除 `any` | 产品评审员 |
| 21 | 🟠 | 事务 | `test_set_service.py` L:32-82 | `import_cases` 中 UPDATE 依赖隐式 flush 顺序 | 执行 UPDATE 前加 `self.session.flush()` 显式化 | 产品评审员 |
| 22 | 🟡 | 提示注入 | AI Prompt 构建 | 提示词注入防御仅正则，可被 Unicode 变体绕过 | 增加语义检测层和输入长度限制 | 安全官 |
| 23 | 🟡 | 文件上传 | 上传端点 | 文件上传仅校验扩展名，无 magic byte 检查 | 增加 `python-magic` 校验真实 MIME 类型 | 安全官 |
| 24 | 🟡 | 信息泄露 | EPS 端点 | EPS 元数据端点匿名可访问，暴露完整 API 结构 | 限制为已认证用户访问 | 安全官 |
| 25 | 🟡 | HTTP 安全 | 响应头 | 无 Content-Security-Policy 头 | 添加合理 CSP 头 | 安全官 |
| 26 | 🟡 | 会话管理 | 认证系统 | 并发会话数无限制（0） | 设置合理的同账号并发会话上限 | 安全官 |
| 27 | 🟡 | 软删除 | `annotation.py` L:27-54 | `workflow_annotation` 模块缺少 `soft_delete=True` | 添加软删除配置 | 产品评审员 |
| 28 | 🟡 | 图表容错 | `trend.vue` L:90 | 动态属性访问无 fallback，metric 缺失时 `NaN` | 加 `?? 0` fallback | 产品评审员 |
| 29 | 🟡 | UI 缺失 | `annotation.vue` | 标注页面缺少 κ 触发入口 | 添加「计算校准 κ」按钮和结果展示区 | 产品评审员 |
| 30 | 🟡 | 测试覆盖 | workflow_annotation | `compute_kappa` 缺少边界测试 | 补充：无标注、单标注、完全一致/不一致、gold 优先级 | 产品评审员 |
| 31 | 🟡 | 强制改密 | 认证系统 | 首次登录改密无服务端强制 | 增加 `must_change_password` 字段并在 API 层校验 | 安全官 |
| 32 | 🟡 | UI 资源 | `menu.json` | `workflow_annotation` 菜单图标 `icon-edit.svg` 不存在 | 创建 SVG 或使用已有图标替代 | QA测试员 |
| 33 | 🟡 | 首次改密 | 认证系统 | 首次登录强制改密无服务端强制 | 增加 `must_change_password` 标志位和 API 拦截 | 安全官 |
| 34 | 🟡 | 测试缺口 | `compiler.py` | 仅 11% 覆盖 | 补充工作流编译核心逻辑测试 | QA测试员 |
| 35 | 🟢 | 弃用 API | 后端多处 | `datetime.utcnow()` 已弃用 | 改用 `datetime.now(timezone.utc)` | 安全官 |
| 36 | 🟢 | 日志 | 全局 | 安全日志未结构化 | 采用 JSON 格式结构化安全事件日志 | 安全官 |
| 37 | 🟢 | SSRF | Gemini 适配器 | 缺少 SSRF 防护 | 增加请求 URL 白名单/IP 黑名单 | 安全官 |
| 38 | 🟢 | 密码强度 | `config.py` | 密码强度策略可增强 | 增加最小长度 12、必需特殊字符、禁止常见密码 | 安全官 |

---

## ✅ 行动清单

### P0 — 阻塞上线（7 项，预计半天）

| # | 行动 | 负责方 | 紧急度 | 修复位置 |
|---|------|--------|--------|---------|
| 1 | **JWT 密钥轮换**：`openssl rand -hex 32` 生成新密钥替换占位符，确保不提交仓库 | 安全运维 | P0 | `.env` + 部署配置 |
| 2 | **API 密钥保护**：将 `.env` 中 `DEEPSEEK_API_KEY`、`SQL_PASSWORD` 等迁移至 Secret 管理 | 安全运维 | P0 | 部署平台 Secret 管理 |
| 3 | **默认密码策略**：首次部署脚本生成随机管理员密码并通过安全渠道交付 | 安全运维 | P0 | 部署脚本 |
| 4 | **LLM Judge 花括号转义**：`llm_judge.py:28-33` JSON `{` → `{{`、`}` → `}}` | 后端开发 | P0 | `backend/app/modules/workflow_eval/service/evaluator/llm_judge.py` |
| 5 | **compute_kappa 归属校验**：`annotation_service.py:66` 开头加 `_assert_run_owned()` | 后端开发 | P0 | `backend/app/modules/workflow_annotation/service/annotation_service.py` |
| 6 | **finalize 事务原子化**：`eval_orchestrator.py:209` backfill 内化到 finalize 同一 Session | 后端开发 | P0 | `backend/app/modules/workflow_eval/service/eval_orchestrator.py` |
| 7 | **孤儿写入检查**：`eval_orchestrator.py:184` write_case_result 写入前检查 run.status | 后端开发 | P0 | `backend/app/modules/workflow_eval/service/eval_orchestrator.py` |

### P1 — 首周内修复（6 项）

| # | 行动 | 负责方 | 紧急度 |
|---|------|--------|--------|
| 8 | Token 从 localStorage 迁移至 httpOnly Cookie + CSRF 双验证 | 前端 + 后端 | P1 |
| 9 | 启用 `ADMIN_CSRF_ORIGIN_CHECK_ENABLED=True` + `ADMIN_CAPTCHA_ENABLED=True` | 安全运维 | P1 |
| 10 | Refresh Token 从 GET 查询参数改为 POST body | 后端 | P1 |
| 11 | CompositeEvaluator 子评估器异常隔离（try/except） | 后端 | P1 |
| 12 | Celery task `.delay()` 前完成所有 commit 确保 cancel 有效性 | 后端 | P1 |
| 13 | `resolve_payload` 存储不可用时的 fallback 机制 | 后端 | P1 |

### P2 — 首月内改进（剩余 Medium/Low 项）

详见完整报告中的 #22-#38 项，主要包括：提示注入防御升级、文件上传 magic byte 校验、CSP 头、bootstrap seed 固定、TypeScript 类型完善、测试覆盖率提升等。

---

## ⚠️ 待完善 / 已知局限

- 前端 E2E 测试（Playwright）未运行，完整端到端流程验证缺失
- `workflow/service/compiler.py` 覆盖率仅 11%，工作流编译核心逻辑缺少充分测试
- AI 提示词注入防御仅基于正则，对 Unicode 变体、编码混淆等绕过手段防护不足
- Gemini 适配器缺少 SSRF 防护（请求 URL 无白名单校验）
- `datetime.utcnow()` 已弃用，需全局迁移至 timezone-aware API
- 安全日志未结构化，不利于 SIEM 集成和安全事件回溯

---

## 📚 成员产出索引

- **gstack-product-reviewer（产品评审员）** 原始产出：3 CRITICAL（竞态/IDOR/孤儿写入）+ 8 WARNING + 6 INFO，覆盖 75 个文件
- **gstack-security-officer（安全官）** 原始产出：安全审计报告（`E:\project\Loom\.gstack\security-audit-history\audit-2025-01-20-comprehensive.md`），21 项发现，评分 C+ (70/100)
- **gstack-qa-lead（QA测试员）** 原始产出：Standard Tier 全栈测试，310 passed / 10 failed / 健康度 72/100

---

> 本报告由软件工坊 AI 协作生成，关键决策请由工程负责人复核。
