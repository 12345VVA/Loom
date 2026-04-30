# 菜单 SVG 图标使用说明

## 结论

Loom 的菜单图标选择器来自 `virtual:svg-icons`，并且只展示名称以 `icon-` 开头的 SVG。

当前可选菜单图标共 **147 个**。这些图标主要来自三部分：

- 项目原有的后台基础图标
- Loom 新增的 AI、Agent、媒体生成、通用后台图标
- 从 `xw.manage-vue` 复用的未冲突图标

相关实现位置：

- [src/modules/base/components/menu/icon.vue](../src/modules/base/components/menu/icon.vue)
- [src/modules/base/components/icon/svg.vue](../src/modules/base/components/icon/svg.vue)
- [src/modules/base/static/svg](../src/modules/base/static/svg)
- [packages/vite-plugin/src/svg/index.ts](../packages/vite-plugin/src/svg/index.ts)
- [vite.config.ts](../vite.config.ts)

## 菜单图标筛选规则

菜单图标选择器使用下面的逻辑筛选图标：

```ts
const list = ref(svgIcons.filter(e => e.indexOf('icon-') === 0));
```

因此：

- `icon-user.svg` 会注册为 `icon-user`，并出现在菜单图标下拉中
- `search.svg`、`home.svg`、`delete.svg` 等普通 SVG 也会被注册，但默认不会出现在菜单图标下拉中
- 新增菜单图标时，文件名必须使用 `icon-xxx.svg`

## SVG 注册规则

项目会扫描 `src/modules` 和 `src/plugins` 下的 SVG 文件，并自动注册为 symbol。

注册规则由 `packages/vite-plugin/src/svg/index.ts` 和 `vite.config.ts` 决定：

- 默认会拼上模块名前缀，例如 `模块名-文件名`
- 如果文件名本身包含 `icon-`，就不会再拼模块名前缀
- 当前 `vite.config.ts` 配置了 `skipNames: ['base', 'theme']`
- `base` 模块下的 `icon-user.svg` 最终名称就是 `icon-user`

菜单组件中的 `<cl-svg :name="item.icon" />` 会进一步渲染为：

```html
<use xlink:href="#icon-icon-user" />
```

## 当前图标分组

下面列出当前项目中可作为菜单图标使用的主要 `icon-*` 图标。菜单配置里的 `icon` 字段直接填写这些名称即可。

### 基础后台类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-home` | 首页 |
| `icon-workbench` | 工作台 |
| `icon-dashboard` | 控制台 |
| `icon-overview` | 概览 |
| `icon-menu` | 菜单 |
| `icon-list` | 列表 |
| `icon-user` | 用户 |
| `icon-dept` | 部门 |
| `icon-organization` | 组织架构 |
| `icon-role` | 角色 |
| `icon-auth` | 认证、授权 |
| `icon-permission` | 权限点 |
| `icon-tenant` | 租户 |
| `icon-doc` | 文档 |
| `icon-file` | 文件 |
| `icon-folder` | 文件夹 |
| `icon-folder-file` | 文件归档 |
| `icon-tag` | 标签 |
| `icon-search` | 搜索 |
| `icon-info` | 信息、详情 |
| `icon-question` | 问答 |
| `icon-help` | 帮助中心 |

### AI、Agent 与媒体生成类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-ai` | AI 核心能力 |
| `icon-ai-chat` | AI 对话 |
| `icon-ai-model` | AI 模型 |
| `icon-agent` | 智能体 |
| `icon-agent-flow` | 智能体编排 |
| `icon-prompt` | 提示词 |
| `icon-knowledge` | 知识库 |
| `icon-knowledge-base` | 知识库扩展 |
| `icon-workflow` | 工作流 |
| `icon-comic` | 漫剧 |
| `icon-storyboard` | 分镜 |
| `icon-image-gen` | 生图 |
| `icon-image-edit` | 图像编辑 |
| `icon-video` | 视频 |
| `icon-video-gen` | 视频生成 |
| `icon-video-edit` | 视频剪辑 |
| `icon-media` | 媒体资产 |
| `icon-template` | 模板 |
| `icon-dashboard-ai` | AI 总览 |
| `icon-model` | 模型、模型配置 |

### 系统运维与配置类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-set` | 设置 |
| `icon-params` | 参数配置 |
| `icon-dict` | 字典 |
| `icon-db` | 数据库 |
| `icon-data` | 数据中心 |
| `icon-storage` | 存储 |
| `icon-backup` | 备份 |
| `icon-cache` | 缓存 |
| `icon-queue` | 队列 |
| `icon-schedule` | 定时任务 |
| `icon-monitor` | 监控 |
| `icon-log` | 日志 |
| `icon-audit` | 审计 |
| `icon-security` | 安全 |
| `icon-api` | 接口 |
| `icon-integration` | 集成 |
| `icon-webhook` | Webhook |
| `icon-maintenance` | 维护 |
| `icon-release` | 发布、版本 |
| `icon-system` | 系统管理 |
| `icon-theme` | 主题 |
| `icon-upload` | 上传 |
| `icon-download` | 下载 |
| `icon-unlock` | 解锁 |
| `icon-ban` | 禁用 |
| `icon-warn` | 告警、风险 |

### 数据、运营与业务类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-analytics` | 数据分析 |
| `icon-report` | 报表 |
| `icon-chart` | 图表 |
| `icon-count` | 统计 |
| `icon-rank` | 排名 |
| `icon-amount` | 金额 |
| `icon-card` | 卡片、证件 |
| `icon-cart` | 购物车、订单 |
| `icon-goods` | 商品 |
| `icon-reward` | 奖励 |
| `icon-vip` | 会员 |
| `icon-crown` | 等级 |
| `icon-favor` | 收藏 |
| `icon-like` | 点赞 |
| `icon-hot` | 热门 |
| `icon-new` | 新增、上新 |
| `icon-activity` | 活动 |
| `icon-approve` | 审批 |
| `icon-pending` | 待处理 |
| `icon-progress` | 进度 |
| `icon-project-plan` | 项目计划 |
| `icon-task` | 任务 |
| `icon-track` | 跟踪 |

### 内容、学习与扩展业务类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-news` | 新闻 |
| `icon-notice` | 公告 |
| `icon-notification` | 消息通知 |
| `icon-msg` | 消息 |
| `icon-message` | 留言、会话 |
| `icon-mail` | 邮件 |
| `icon-feedback` | 反馈 |
| `icon-forum` | 论坛 |
| `icon-course` | 课程 |
| `icon-learning` | 学习 |
| `icon-study-plan` | 学习计划 |
| `icon-exam` | 考试 |
| `icon-paper` | 试卷 |
| `icon-question-bank` | 题库 |
| `icon-certificate` | 证书 |
| `icon-weekly` | 周报 |
| `icon-solution` | 方案 |
| `icon-tutorial` | 教程 |
| `icon-command` | 指令、命令 |

### 设备、位置与行业扩展类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-device` | 设备 |
| `icon-iot` | 物联网 |
| `icon-camera` | 相机、拍摄 |
| `icon-phone` | 手机 |
| `icon-call` | 通话 |
| `icon-map` | 地图 |
| `icon-local` | 本地、位置 |
| `icon-position` | 岗位、位置 |
| `icon-earth` | 全球、地球 |
| `icon-vehicle` | 车辆 |
| `icon-travel` | 出行 |
| `icon-attendance` | 考勤 |
| `icon-employee` | 员工 |
| `icon-salary` | 薪资 |
| `icon-performance` | 绩效 |
| `icon-kpi` | KPI |
| `icon-subsidy` | 补贴 |
| `icon-inspection` | 巡检 |
| `icon-construction` | 施工 |
| `icon-living` | 直播、生活 |
| `icon-scan` | 扫描 |

### 其他通用类

| 图标名 | 建议语义 |
| --- | --- |
| `icon-app` | 应用 |
| `icon-common` | 通用 |
| `icon-component` | 组件 |
| `icon-design` | 设计 |
| `icon-discover` | 发现 |
| `icon-emoji` | 表情 |
| `icon-light` | 灵感、灯光 |
| `icon-match` | 匹配 |
| `icon-pic` | 图片 |
| `icon-quick` | 快捷 |
| `icon-toolbox` | 工具箱 |
| `icon-work` | 工作 |
| `icon-fx` | 分析、函数 |
| `icon-kanban` | 看板 |
| `icon-paper` | 纸张、资料 |

## 新增菜单 SVG 的推荐做法

1. 将 SVG 文件放到：

   `frontend/src/modules/base/static/svg`

2. 文件名使用：

   `icon-你的名字.svg`

3. 菜单配置中的 `icon` 值填写：

   `icon-你的名字`

4. 启动或刷新前端开发环境后，菜单图标下拉会自动出现该图标。

## SVG 资产规范

新增或复用 SVG 时，建议遵循下面的规则：

- 文件名使用小写英文和短横线，例如 `icon-user-group.svg`
- 菜单图标统一使用 `icon-` 前缀
- 优先使用单色 SVG，让图标跟随 `currentColor` 或当前主题色
- 必须保留合理的 `viewBox`
- 避免外链、脚本、`foreignObject`、图片引用和复杂编辑器元数据
- 从设计平台导出的 SVG 建议先精简，再放入项目

## 为什么有些 SVG 不在菜单下拉中

`src/modules/base/static/svg` 下还有一些非 `icon-` 前缀的 SVG，例如：

- `search`
- `set`
- `home`
- `delete`
- `success`
- `team`
- `trend`

它们可以通过代码直接使用：

```vue
<cl-svg name="search" />
```

但因为菜单图标选择器只筛选 `icon-` 前缀，所以不会出现在菜单管理的图标下拉中。

## 一句话总结

菜单可选图标就是当前项目所有注册 SVG 中，名称以 `icon-` 开头的那一批；新增菜单图标时，把 SVG 放到 `frontend/src/modules/base/static/svg` 并命名为 `icon-xxx.svg` 即可。
