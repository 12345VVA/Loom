# Changelog

本文件由提交史生成（分组规则见 cliff.toml，当前版本条目覆盖全部 211 次提交）。
后续发版：随 git tag 追加小节；工具可用后用 `git cliff -o CHANGELOG.md` 再生。
版本唯一源：backend/pyproject.toml [project] version（与 .env.example APP_VERSION、frontend/package.json 对齐）。

## v0.1.0 - 2026-10-04

首次发布基线：2026-04 至 2026-10 全部历史。含 2026-10 治理冲刺成果——CI 流水线建成、
架构守卫六道、SQLite 退场与 baseline squash、EPS 响应侧泛型化、DI 反向依赖清零、
巨石拆分三处、供应链门禁（G1）、治理收尾（G2）。

### 新增（43）

- G1 供应链与 CI 加固——dependabot 三生态周检 + 漏洞审计(报告模式) + job 超时 (H1)(M1)
- B3 EPS 响应侧泛型化——service 方法返回具体类型
- EPS 元数据导出仅开发环境可用
- AI 工作台双页面重构（chat/image 拆分 composable 与子组件）
- 重构 AI 对话与生图工作台交互体验
- 优化执行日志产物链接本地替换与生图节点尺寸配置
- 新增 ToAPIs 适配器与生图尺寸归一化强校验防线
- 增加图片尺寸二进制探测、失败重试与前端下载令牌全局单例
- 执行监控瘦身与产物生命周期治理（三期）
- 产物实体落地与产物视图，执行监控与产物解耦
- AI 治理专项存量改动——invocation 精确释放、T8 载荷分离、DeepSeek 思维链透传
- 百炼业务空间已授权模型自动拉取，接入 models/permissions
- 火山方舟已开通模型自动拉取，接入 ListModelActivations
- 响应格式编辑器组件化，配置标签中文化
- 补全 6 个业务模块 en/zh-tw 语言包，修复 workflow 重复 key
- 设备管理升级为设备级聚合（参考谷歌）
- 多设备会话管理 + 退出仅当前设备
- H1 图像缺口验证码，彻底隐藏答案
- 验证码按环境启用 + 修复 M5/M6
- token sessionStorage 化、路由权限校验、iframe 与 XSS 防护
- 媒体归属隔离、任务白名单与防重放、通知与标注归属校验
- 治理并发精确释放、AI 调用权限、SSRF 适配器、prompt 注入检测
- refresh token HttpOnly cookie、下载令牌、菜单环路校验、输入校验
- 生产 CSRF 强制、事务提交修复、Celery 持久化、/uploads 鉴权与归属校验
- SSRF 防护、上传 magic bytes、可信代理 IP、分页 clamp
- 编码自动生成与列表/版本展示优化
- 试运行改为跑草稿版（新增 /trial 接口）
- 实例列表展示运行 Token 用量与成本
- 节点级自动重试与失败节点追踪
- 评测系统对标升级（P0+P1+P2 全 12 项）
- 引入工作流版本管理与发布管理（P0+P1+P2）
- 评测系统与 AI 治理完善
- 执行引擎 Celery 异步化与编辑器健壮性
- 菜单提升与基础设施修复
- 安全修复 S1-S6 + PostgreSQL 适配 + 代码风格统一
- 编辑器画布 UX 与单节点测试
- add ai generation tasks and media assets
- add ai chat testing workflow
- add colorful menu svg icons
- add ai model management foundation
- add notification module and production hardening
- refresh Loom branding and captcha UI
- 优化任务管理配置

### 修复（46）

- 0019 补版本表复合索引的新建库路径（CI check add_index 修复）
- 真库 drift 修正迁移 0019 + 排除 langgraph 自管表 + 版本表补回复合索引定义
- HEALTHCHECK 适配 /health 的响应包装结构
- baseline 重编为全量 metadata（38 表）+ env.py 模型注册去重
- reflect 驱动清库 + CI 双通道分 schema
- original_url 改 TEXT + 测试引擎 PG 隔离（Step 3）
- 时间字段全面 timezone-aware + timestamptz 迁移（sqlmodel 解禁）
- 修复 4 个环境敏感测试的 CI 翻红（captcha 开关与允许列表漂移）
- 钉住 sqlmodel==0.0.38（CI 测试因依赖版本漂移大面积红）
- 10 个复合索引声明进模型 __table_args__
- BaseAdminCrudService 事务一致性修复（评审 P1-b）
- 修复去重删除后实例复用与五处过时测试断言
- 节点模块审计修复与人工输入节点支持
- 媒体代理与产物链路安全加固（三角度审查修复九项）
- 工作流转存资产补归属，修复普通用户不可见与图片 403
- 执行失败错误信息透出节点与原因，失败节点补写执行日志
- 系统代理下媒体转存证书校验失败，safe_stream 回退 hostname 请求
- 底部工具条长标题被压缩成竖排，限宽截断显示
- aiRuntime 单例移至模块根，规避 service/** 默认导出扫描
- 对话流式输出实时渲染与滚动优化
- 收敛登录链路低危漏洞 L1-L3
- 修复图像滑块验证码滑块空白与坐标对不齐
- 修复 P0 鉴权漏洞 M1-M4
- 修复退出登录——menu/process store 实现 $reset
- 退出走 open.logout 清 cookie，后端日志失败不阻塞登出
- 退出登录用 finally 兜底，后端登出接口失败也清理前端登录态
- refreshToken cookie path 改为 /，修复代理前缀致续期 401
- 刷新页面时用 refresh token 静默续期，不再误踢已登录用户
- token 过期清理残留，修复失效后误显 404
- 移除路由级权限校验，修复大面积误判 403
- 核实并修复功能缺陷与工程债
- 示例工作流对齐当前设计规范
- 图像数据解析、对话交互与仪表盘健壮性
- 节点样式补全与颜色变量化
- 任务调度参数与工作流发布前校验
- 三处运行期回归修复（流式防环 / 用户审计 / 限流响应头）
- 运行期降级防环、任务执行防重与计数 fail-open
- update DTO 放开必填字段以支持部分更新
- 修复编辑器与工作台 SSE 流及 keep-alive 缓存副作用
- 修复编辑器 keep-alive 缓存导致切换工作流画布不更新等问题
- 修复菜单行内切换 keepAlive 报 name Field required
- 修复试运行画布卡住、终态无日志及坏图未拦截
- 修复 SSE 流主动取消时的 AbortError 未捕获
- 启动去重保护、执行容错与资源清理
- 修复 watch 未导入导致的运行时错误，preview 改为双向绑定
- harden frontend upload and security handling

### 性能（2）

- bootstrap_defaults 批量 upsert——O(N) commit 收敛为单事务
- 优化模型与调用日志批量查询性能并记录请求参数

### 重构（27）

- B4 巨石拆分——editor.vue 编排逻辑 composable 化
- B4 巨石拆分——compiler 按域分文件
- B4 巨石拆分——admin_service 按资源域分文件
- 层 3——core/security 延迟导入改经 runtime 注册表，全量清零
- 层 2——中间件/query_builder/compat 拆除 modules 依赖，framework 清零
- 层 1——runtime 注册表 + 定义下沉 framework + controller_meta 拆除 modules 依赖
- log-drawer 抽离图片/格式化/筛选/展开 composable 与 utils
- 节点执行域拆分——llm_io 纯函数群与 node_executors 独立成模块
- 删除零引用框架模块/调试脚本/demo 示例模块
- 删 BaseAdminCrudService 重复钩子段（零行为）
- 移除产品层 SQLite 支持（数据已全量迁移 PostgreSQL）
- 规范化菜单权限结构并优化下载令牌与资源访问校验
- 生图工作台拆分 utils/composables/厂商参数组件
- 任务提交改 useForm 弹窗
- 平铺提示收敛为 tooltip
- 统计条抽 stat-chips 组件
- 枚举列接 dict 渲染
- 插槽命名对齐 prop 并补 upsert 空值初始化
- runtime 服务类型化并清理冗余 as any
- 任务接口回归 EPS，删除 runtime 私建方法
- 图片响应解析抽入 utils 并统一三处重复实现
- 统一编辑器共享类型 + 合并删除路径 + 提取 validateGraph/duplicateNode
- 重构 editor.vue 及工作流模块
- 节点配置校验与日志抽屉组件抽取
- 编辑器画布逻辑重构与核心修复
- 重组导航结构并迁移评估标注入口
- 节点执行逻辑拆分与工具节点告警

### 测试（9）

- cool+config+base 复合单元 noImplicitAny 试点——28 处标注全清
- 守卫扩展——framework 函数内 import 冻结 + core 延迟导入冻结
- framework 反向依赖白名单守卫——补齐核实报告 P2 最后一道防线
- conftest 关闭全局限流（测试提速后登录挤进限流窗口）
- TestClient 用例 lifespan 提升到 class 级（5 文件 6 类 setUpClass 化）
- make_test_engine 收编 55 处测试引擎（Step 2 参数化）
- 修复 permission 与 log-drawer 存量测试（CI 首跑 test:unit 红点）
- 覆盖安全加固、并发治理、归属校验与数据一致性
- enhance automated coverage

### 文档（8）

- 工程治理方案——G1-G7 批次设计与决策点
- 架构与治理重审报告（2026-10-04）——三路深查，问题编号 H/M/L 追踪机制
- 沉淀 B3 EPS 泛型化经验为前后端开发规则
- 技术债清单四阶段全部清偿归档
- CI 落地排障实录（九跑全记录与方法论沉淀）
- 移除遗留的 pre-launch r1 审查文档
- 补充前后端 Cursor 开发规范
- update menu svg icon guide

### CI（5）

- 主 job 测试全量切 PG（Step 3 完成）
- 校验前显式加载 include 任务模块（worker 启动同款）
- 引入 requirements.lock 约束文件，终结依赖版本漂移
- alembic 验证改为 create_all+stamp+check（匹配部署模式）
- 建立 GitHub Actions 双 job 流水线与测试库防护（评审 P0/P1-c）

### 样式（6）

- hardening 测试函数内 import 排序（ruff I001）
- test_arch_guard 白名单守卫补 ruff format 合规
- ruff 基线修复（database.py import 排序、helpers 未用 import、arch_guard f-string）
- 格式化 admin_service 超长行（CI 首跑 format 检查）
- 修复事务测试导入排序（CI 首跑 I001）
- ruff/eslint 基线清理（CI 前置）

### 杂项（18）

- G2 治理收尾——诊断脚本转正(全量AST+真实退出码) + 指南修正 + 10-02评审回填 + 卫生清理 (M4)(M5)(L3)(L4)
- no-explicit-any 升 error + suppressions 豁免存量
- 补 frontend/Dockerfile.dev + backend 镜像加固（lock/非 root/HEALTHCHECK）
- 解禁 .dockerignore 入库 + 补后端构建上下文遮拦
- 移除被 baseline squash 取代的旧迁移链
- baseline squash——全量建表 DDL 取代空壳迁移链
- compose 反转 PG 默认与 SQLite 依赖清理
- distpicker 数据源入库与 data 目录忽略策略修正
- 添加生图工作流示例及尺寸修复与测试脚本
- 清理不应入库的 AI 工具产物
- .gitignore 显式忽略 .pytest_cache
- 移除 .trae 缓存的 git 跟踪并补全忽略规则
- gitignore 忽略 .trae/specs/ AI 工具目录
- 质量门禁起步 - ESLint warn 先行与 bundle 分析
- 精准过滤 pydantic 第三方库的 UnsupportedFieldAttributeWarning
- 忽略 .workbuddy/.gstack、补充 AGENTS 终端规范、存档对标分析与上线检查
- finalize test setup updates
- 完成框架整改与文档同步

### 其他（51）

- 更新README;
- Merge branch 'main' of github.com:12345VVA/Loom
- 框架线程池卸载与异步收敛 + 架构文档
- LLM 节点支持 System Prompt，工作流服务适配双提示词架构
- 工作流新增测试运行 composable 与节点类型注册表
- 工作流编辑器 UI 重构：组件拆分、配置面板浮层化、交互增强
- AI 模块新增安全防护：提示词注入检测与输出 PII 脱敏
- 工作流编辑器新增测试运行与执行日志可视化
- 新增 3 个示例工作流及生成脚本扩展
- 前端：修复孤立节点检测，排除组内子节点
- 前端：Markdown 编辑器集成变量插入功能
- 前端：节点配置组件统一接入 cl-variable-input
- 前端：重构工作流变量系统，抽取独立变量输入组件
- 后端：优化模型调用超时逻辑，优先使用请求级 timeout
- 工作流编辑器增强：导出功能、变量节点支持、连线验证
- 前端配置组件和 JSON 树编辑器 ESLint/TS 修复
- 新增变量赋值和变量转换节点配置组件
- 前端节点/边组件 ESLint + TypeScript 合规修复
- 新增 7 个示例工作流 JSON 及生成脚本
- 工作流服务新增节点执行器：变量赋值、变量转换、条件分支
- 工作流编译器增强：条件路由健壮性、边推导 fallback、变量花括号剥离
- 工作流编辑器 UX 增强：连线验证、右键菜单、节点搜索、容器拖入
- 工作流配置组件简化：移除路由下拉，改用端口直连
- 工作流节点组件 UX 增强：多 Handle 直连、子节点标识、未配置红点
- 工作流编译器支持多 Handle 路由推导与 group 容器穿透
- 前端通用组件优化：表格选择器回显、CodeMirror 复制、AI 视图显示名
- 工作流前端配置面板与节点配置重构
- 新增 JSON 树编辑器组件，替代 LLM/结束节点的扁平字段列表
- 工作流 for_each/batch 子图执行模型重构（后端）
- AI 适配器兼容性增强：修复各厂商 response_format 差异
- 新增 Markdown 编辑器插件并替换全项目文本编辑字段
- 新增 CodeMirror JSON 编辑器插件并替换全项目 JSON 编辑字段
- 添加工作流实例调试检查脚本
- 添加 Antigravity 运行环境规则配置
- AI 图生图：模型默认参数自动加载与火山方舟引导增强
- 新增前端工作流模块：可视化设计器与实例管理
- 新增工作流模块：可视化工作流定义、编译与执行引擎
- 后端基础设施：添加工作流引擎运行支持
- AI 模块：修复模型查询字段映射与 Profile 输出增强
- 完善多厂商图生图适配与日志系统健壮性
- 修复日志系统多项问题
- 更新项目说明；
- 忽略本地 .claude 配置目录
- 修复生图链路与资源库展示问题
- 完善多厂商 AI 生图适配
- refactor ai services and logging
- 清理task_ai模块并完善框架规范与安全功能
- 统一命名转换层与框架文档整理
- 更新README；
- 修复一些通用的crud问题；
- 初始化项目；
