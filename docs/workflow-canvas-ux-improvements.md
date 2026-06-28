# 工作流画布 UI/UX 优化建议（完整版）

> 基于对 `frontend/src/modules/workflow/` 全部组件、composable、样式文件的代码审查，结合现有 `ui-guidelines.mdc` 规范，按优先级和主题域整理。

---

## 一、高优先级（影响正确性 / 一致性 / 核心体验）

### 1.1 condition-node 脱离 base-node 导致功能不对等

**现状**：`condition-node.vue` 独立渲染，完整复制了 `.custom-flow-node` 的样式定义，且缺少 base-node 上的播放测试按钮和执行日志展示。

**问题**：
- 样式重复 = 维护成本翻倍（改一处忘另一处）
- 条件节点无法单节点测试，与其他节点体验断裂
- 高度 56px vs base-node 的 42px，视觉不统一

**建议**：
- 将 condition-node 改为基于 base-node 扩展（通过 slot 或 prop 控制额外 Handle 渲染）
- 双输出 Handle（T/F）作为 base-node 的可选模式，通过 props `handles` 配置传入
- 如必须独立渲染，将共享样式提取到 `workflow-shared.scss`，两处引用同一文件

---

### 1.2 配置面板直接修改 props（违反单向数据流）

**现状**：`llm-config.vue`、`condition-config.vue` 等直接修改 `props.modelValue` 的深层属性（如 `v-model="config.modelProfileCode"`），绕过了 Vue 的 `emit('update:modelValue')` 机制。

**问题**：
- 调试困难，数据变更无法追踪
- 未来迁移到 Pinia 或其他状态管理时会有兼容问题

**建议**：
- 统一使用 `emit('update:modelValue', { ...props.modelValue, key: newVal })` 模式
- 或引入一个轻量的 `useConfigPanelState` composable，内部维护可写状态并通过 `watch` 同步回父组件
- 在 `node-config-panel.vue` 层面提供统一的 `updateConfig(path, value)` 方法

---

### 1.3 表单校验缺失

**现状**：
- 条件节点表达式无语法校验或预览
- Start 节点变量名无唯一性校验、无格式校验（可输入中文/空格/特殊字符）
- 变量名可以重复添加

**问题**：用户只有提交到后端后才能发现错误，增加来回修正的成本。

**建议**：
- **变量名校验**：正则 `^[a-zA-Z_][a-zA-Z0-9_]*$`，提交前检查唯一性，即时红色边框 + 错误提示
- **表达式校验**：提供"预览结果"按钮，或至少做括号匹配、变量引用存在性检查
- 在 `node-inputs-editor.vue` 中添加 `el-form` 的 `rules` 验证规则

---

### 1.4 右键菜单无边界检测

**现状**：右键菜单使用 `position: fixed` + 鼠标坐标定位，靠近屏幕右/下边缘时菜单溢出可视区域。

**建议**：
```typescript
// 在 showContextMenu 中计算位置时
const menuWidth = 180  // 预估菜单宽度
const menuHeight = items.length * 36  // 预估菜单高度
const x = event.clientX + menuWidth > window.innerWidth
  ? event.clientX - menuWidth
  : event.clientX
const y = event.clientY + menuHeight > window.innerHeight
  ? event.clientY - menuHeight
  : event.clientY
```

---

### 1.5 画布连线（Edge）交互增强

**现状**：连线仅有默认的贝塞尔曲线，条件分支的标签不够显眼，hover 效果仅靠 `editor.vue` 的 `:deep()` 样式实现，效果单一。

**建议**：
- **Hover 增强**：连线 hover 时变粗（`stroke-width: 2 → 3.5`）+ 发光效果（`filter: drop-shadow`），在 `label-edge.vue` 组件内部实现而非依赖全局 `:deep`
- **条件标签更显眼**：Switch/Condition 分支的标签使用与分支语义对应的背景色（绿底白字 = True，红底白字 = False），而不是当前的半透明白底
- **选中态**：选中的边变为橙色 + 虚线动画流动效果，与普通 hover 态区分
- **连线类型视觉分层**：普通边用实线，条件边用虚线或带箭头装饰，一眼区分

---

## 二、中优先级（提升效率 / 减少摩擦）

### 2.1 撤销/重做（Undo / Redo）

**现状**：编辑器无撤销/重做功能，用户误操作（如误删节点/连线）只能手动恢复或放弃修改。

**建议**：
- 使用 VueFlow 的 `useHistory` composable（如已内置）或自行实现命令模式：
  ```typescript
  // useUndoRedo.ts
  const history = ref<Snapshot[]>([])
  const pointer = ref(-1)

  function pushSnapshot(nodes, edges) {
    history.value = history.value.slice(0, pointer.value + 1)
    history.value.push({ nodes: cloneDeep(nodes), edges: cloneDeep(edges) })
    pointer.value++
  }
  ```
- 在底部工具栏或编辑器右上角提供 Undo/Redo 按钮 + 快捷键 `Ctrl+Z` / `Ctrl+Shift+Z`
- 快捷键需在输入框聚焦时跳过（与现有的 Delete 快捷键逻辑一致）

---

### 2.2 连线吸附与自动对齐（Snap to Grid / Alignment Guides）

**现状**：节点拖动无任何对齐辅助，在构建整齐的工作流时完全依赖手动调整。

**建议**：
- **网格吸附**：VueFlow 支持 `snap-to-grid` 属性，开启后节点自动对齐到网格交叉点
  ```vue
  <VueFlow :snap-to-grid="true" :snap-grid="[16, 16]">
  ```
- **辅助对齐线**：拖动节点时，检测与其他节点的水平/垂直对齐关系，绘制半透明参考线
  - 可参考 `vue-flow` 社区插件或自行实现（监听 `onNodeDrag` 事件，计算位置关系）
- **分布对齐**：右键菜单增加"水平等距分布"/"垂直等距分布"选项

---

### 2.3 空状态引导优化

**现状**：画布节点数 ≤ 2 时显示静态引导文案"从下方工具栏拖拽节点到画布开始构建工作流"。

**建议**：
- **动效引导**：引导区域增加一个脉动箭头动画（CSS `@keyframes bounce`），指向底部工具栏的"添加节点"按钮
  ```css
  @keyframes bounce-arrow {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(8px); }
  }
  ```
- **分步引导**：首次使用时展示简短的交互式教程（3-4 步气泡提示）
  1. "点击 + 添加一个开始节点"
  2. "从开始节点右侧拖出连线"
  3. "选择一个 LLM 节点连接"
  4. "点击节点配置参数"
- **引导文案优化**：根据已有节点数动态调整，如已有 start 节点时显示"添加一个 LLM 节点来处理用户请求"
- 引导消失后提供"帮助"按钮可重新触发

---

### 2.4 配置面板折叠状态持久化

**现状**：切换选中节点时，所有 `node-config-section` 都重置为默认展开，用户的折叠偏好丢失。

**建议**：
- 使用 `Map<string, Set<string>>` 按节点 ID + section 标题存储折叠状态
- 切换节点时恢复该节点上次的折叠状态
- 可持久化到 `sessionStorage`，页面刷新后保持

---

### 2.5 Edge 标签宽度计算不准确

**现状**：`label-edge.vue` 使用 `text.length * 7 + 4` 估算标签背景宽度，对中文/特殊字符不准确。

**建议**：
- 使用 SVG `<text>` 的 `getComputedTextLength()` 方法获取精确宽度
- 或使用 `CanvasRenderingContext2D.measureText()` 预计算
  ```typescript
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  ctx.font = '11px sans-serif'
  const width = ctx.measureText(text).width + 12  // padding
  ```

---

### 2.6 性能优化：深度监听与递归遍历

**现状**：
- `watch(elements, { deep: true })` 在节点/边数量多时性能开销大
- `getUpstreamVariablesForNode` 每次重算都全量递归遍历

**建议**：
- 用 `watchEffect` + 手动标记 `dirty` 字段替代 deep watch，仅监听需要触发保存的字段（位置、连线、配置）
- 上游变量计算使用 memoization，以节点 ID + 输入版本号为缓存键
- 考虑引入 `useDebounceFn` 对高频事件（拖拽、输入）做防抖

---

## 三、低优先级 / 体验增强

### 3.1 节点图标 props 冗余（死代码）

**现状**：各节点组件（如 `llm-node.vue`）通过 props 传入 `icon`，但 `base-node.vue` 实际使用 `getNodeMeta(node.type)` 从注册表获取图标，props 中的 icon 被忽略。

**建议**：移除各节点组件中无用的 `icon` props 声明，统一从 `node-type-registry.ts` 获取元数据。

---

### 3.2 无障碍访问（Accessibility）

**现状**：全局缺少 ARIA 角色标注和键盘导航支持。

**建议**：
- 右键菜单：添加 `role="menu"` / `role="menuitem"`
- 配置面板：添加 `role="complementary"` + `aria-label="节点配置"`
- 折叠区：添加 `aria-expanded` 状态
- 节点：添加 `tabindex="0"` + `@keydown.enter` 支持键盘选中
- SVG 边：添加 `<title>` 元素描述连线含义
- 拖拽调整条：添加键盘操作支持（方向键调整宽度）

---

### 3.3 tool 与 tool_executor 类型重叠

**现状**：注册表中 `tool` 标注为"旧版工具节点"，与 `tool_executor` 功能重叠。

**建议**：
- 如后端仍需兼容，在前端注册表中将 `tool` 标记为 `deprecated: true`，在节点选择器中隐藏
- 新建工作流时不再提供 tool 类型选项
- 已有工作流中的 tool 节点保留显示，但添加"此节点类型已弃用"提示

---

### 3.4 localStorage 键名无命名空间

**现状**：面板宽度持久化键名为 `loom_editor_panel_width`，多编辑器实例可能冲突。

**建议**：改为 `loom_editor_panel_width_${workflowId}` 或 `loom_editor_panel_width_${Date.now()}`。

---

### 3.5 底部工具栏偏移量硬编码

**现状**：配置面板打开时工具栏左移 `translateX(calc(-50% - 180px))`，其中 `180px` 是硬编码。

**建议**：读取配置面板实际宽度的一半作为偏移量：
```typescript
const panelHalfWidth = computed(() => panelWidth.value / 2)
// 模板中：:style="{ transform: `translateX(calc(-50% - ${panelHalfWidth}px))` }"
```

---

### 3.6 循环体容器 dragOver 状态分散

**现状**：`loop-body-group-node.vue` 声明了 `dragOver` ref，但实际由 `editor.vue` 通过 DOM class 控制，逻辑不内聚。

**建议**：
- 将 dragOver 状态管理移入 `loop-body-group-node.vue` 内部，通过 VueFlow 的 `onNodeDragOver` 事件配合节点 ID 判断
- 或在 `editor.vue` 中通过 `provide/inject` 传递拖拽状态

---

## 四、跨域建议（涉及多处改动）

### 4.1 建立画布组件共享样式文件

| 现状 | 建议 |
|------|------|
| 节点样式在 base-node 和 condition-node 中重复 | 提取 `workflow-shared.scss`，包含 `.custom-flow-node` 及所有变体 |
| 颜色硬编码 `#409eff`、`#67c23a` 等 | 统一为 CSS 变量 `--wf-color-start`、`--wf-color-llm` 等，与 `node-type-registry.ts` 对应 |
| 动画关键帧分散在各组件 | 统一到 `workflow-animations.scss` |

### 4.2 类型安全加固

- `selectedNode` 当前为 `any`，应定义 `WorkflowNodeData` 接口
- 事件参数（如拖拽、右键菜单）使用具体类型替代 `Event`
- 边标签属性定义 TypeScript interface，避免 `props` 隐式传递

---

## 五、优先级矩阵

```
高影响  │ 1.1 condition-node 统一  │ 1.5 连线交互增强
       │ 1.2 props 单向数据流      │ 2.1 撤销/重做
       │ 1.3 表单校验              │ 2.2 吸附对齐
───────┼───────────────────────────┼───────────────────────
低影响 │ 3.1 图标死代码            │ 3.2 无障碍访问
       │ 3.3 tool 类型重叠         │ 3.4 localStorage 命名
       │ 3.5 工具栏偏移硬编码      │ 3.6 dragOver 状态分散
       │                           │ 2.4 折叠状态持久化
                    高紧迫                          低紧迫
```

---

## 六、建议实施顺序

1. **第一阶段 — 修复与统一**（1-2 天）
   - 1.1 condition-node 基于 base-node 重构
   - 1.2 配置面板 emit 规范化
   - 1.4 右键菜单边界检测
   - 3.1 移除图标死代码

2. **第二阶段 — 校验与反馈**（2-3 天）
   - 1.3 表单即时校验
   - 2.4 折叠状态持久化
   - 2.5 Edge 标签宽度修正

3. **第三阶段 — 交互增强**（3-5 天）
   - 1.5 连线交互增强（hover/选中/条件标签）
   - 2.1 撤销/重做
   - 2.2 吸附对齐
   - 2.3 空状态引导优化

4. **第四阶段 — 打磨**（按需）
   - 3.2 无障碍访问
   - 3.3 遗留类型清理
   - 4.1 共享样式提取
   - 4.2 类型安全加固
   - 2.6 性能优化
