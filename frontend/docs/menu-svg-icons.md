# 目录/菜单 SVG 图标选项说明

## 结论

当前项目里，目录/菜单图标选择器实际可选的 SVG 图标，来自 `virtual:svg-icons`，并且只会显示名称以 `icon-` 开头的图标。

相关实现位置：

- [src/modules/base/components/menu/icon.vue](/d:/NodeFiles/Projects/auth-vue/src/modules/base/components/menu/icon.vue)
- [src/modules/base/components/icon/svg.vue](/d:/NodeFiles/Projects/auth-vue/src/modules/base/components/icon/svg.vue)
- [packages/vite-plugin/src/svg/index.ts](/d:/NodeFiles/Projects/auth-vue/packages/vite-plugin/src/svg/index.ts)
- [vite.config.ts](/d:/NodeFiles/Projects/auth-vue/vite.config.ts)

## 当前菜单可选 SVG 图标列表

下面这些名称，就是菜单配置里可直接使用的 `icon` 值：

| 图标名 | 建议语义 |
| --- | --- |
| `icon-activity` | 活动、动态 |
| `icon-amount` | 金额、财务 |
| `icon-app` | 应用、应用中心 |
| `icon-approve` | 审批、审核 |
| `icon-auth` | 认证、权限 |
| `icon-ban` | 禁用、封禁 |
| `icon-call` | 通话、联系 |
| `icon-camera` | 相机、拍照 |
| `icon-card` | 卡片、证件 |
| `icon-cart` | 购物车、订单 |
| `icon-common` | 通用、公共能力 |
| `icon-component` | 组件、模块 |
| `icon-count` | 统计、计数 |
| `icon-crown` | 会员、等级 |
| `icon-data` | 数据、数据中心 |
| `icon-db` | 数据库 |
| `icon-delete` | 删除 |
| `icon-dept` | 部门、组织 |
| `icon-design` | 设计、配置 |
| `icon-device` | 设备 |
| `icon-dict` | 字典 |
| `icon-discover` | 发现、探索 |
| `icon-doc` | 文档 |
| `icon-download` | 下载 |
| `icon-emoji` | 表情、互动 |
| `icon-favor` | 收藏、喜好 |
| `icon-file` | 文件 |
| `icon-folder` | 文件夹、目录 |
| `icon-goods` | 商品 |
| `icon-home` | 首页 |
| `icon-hot` | 热门 |
| `icon-info` | 信息、详情 |
| `icon-iot` | 物联网 |
| `icon-light` | 灯光、主题 |
| `icon-like` | 点赞 |
| `icon-list` | 列表 |
| `icon-local` | 本地、位置 |
| `icon-log` | 日志 |
| `icon-map` | 地图 |
| `icon-match` | 匹配、对接 |
| `icon-menu` | 菜单 |
| `icon-monitor` | 监控 |
| `icon-msg` | 消息 |
| `icon-news` | 新闻、公告 |
| `icon-notice` | 通知 |
| `icon-params` | 参数、配置项 |
| `icon-phone` | 手机、电话 |
| `icon-pic` | 图片 |
| `icon-question` | 帮助、问答 |
| `icon-quick` | 快捷、效率 |
| `icon-rank` | 排名 |
| `icon-reward` | 奖励、积分 |
| `icon-search` | 搜索 |
| `icon-set` | 设置 |
| `icon-tag` | 标签 |
| `icon-task` | 任务 |
| `icon-time` | 时间、排期 |
| `icon-tutorial` | 教程、指引 |
| `icon-unlock` | 解锁、权限开放 |
| `icon-user` | 用户 |
| `icon-video` | 视频 |
| `icon-vip` | VIP、会员 |
| `icon-warn` | 警告、风险 |
| `icon-work` | 工作、办公 |
| `icon-workbench` | 工作台 |

这些 SVG 文件主要位于：

- [src/modules/base/static/svg](/d:/NodeFiles/Projects/auth-vue/src/modules/base/static/svg)

## 为什么有些 SVG 存在，但菜单下拉里看不到

因为菜单图标选择器用了这段逻辑：

```ts
const list = ref(svgIcons.filter(e => e.indexOf('icon-') === 0));
```

也就是：

- 项目里注册过的 SVG，不一定都会出现在菜单图标下拉中
- 只有名字以 `icon-` 开头的 SVG，才会进入菜单可选列表

例如这些 SVG 虽然也被注册了，但默认不属于菜单选择器可选项：

- `search`
- `set`
- `home`
- `delete`
- `success`
- `team`
- `trend`

它们可以在代码里通过 `<cl-svg name="xxx" />` 直接使用，但不会自动出现在菜单图标下拉中。

## SVG 注册规则

项目会扫描 `src` 下 `modules` 和 `plugins` 里的 SVG 文件，并自动注册成 symbol。

命名规则由 [packages/vite-plugin/src/svg/index.ts](/d:/NodeFiles/Projects/auth-vue/packages/vite-plugin/src/svg/index.ts) 和 [vite.config.ts](/d:/NodeFiles/Projects/auth-vue/vite.config.ts) 决定：

- 默认会拼上模块名前缀，格式类似 `模块名-文件名`
- 但如果文件名本身包含 `icon-`，就不会再拼模块名前缀
- 当前 `vite.config.ts` 里还配置了 `skipNames: ['base', 'theme']`
- 所以 `base`、`theme` 模块下的普通 SVG，也不会强制加模块名前缀

结合当前项目，可理解为：

- `src/modules/base/static/svg/search.svg` 注册后名称是 `search`
- `src/modules/base/static/svg/icon-user.svg` 注册后名称是 `icon-user`
- 菜单选择器最终只会收集 `icon-user` 这种名称

## 如果需要新增可选 SVG 图标，应该怎么做

### 推荐做法

1. 把新的 SVG 文件放到：

   [src/modules/base/static/svg](/d:/NodeFiles/Projects/auth-vue/src/modules/base/static/svg)

2. 文件名直接使用 `icon-你的名字.svg`

   例如：

   - `icon-report.svg`
   - `icon-dashboard.svg`
   - `icon-customer.svg`

3. 启动或刷新前端开发环境后，这个图标会自动注册

4. 菜单图标下拉中会直接出现：

   - `icon-report`
   - `icon-dashboard`
   - `icon-customer`

### 关键原因

因为当前选择器只筛选 `icon-` 前缀，所以你新增菜单图标时，文件名必须满足这个前缀规则，否则不会出现在下拉中。

## 新增 SVG 的最小操作步骤

### 方式一：只新增一个菜单图标

1. 准备一个 SVG 文件
2. 放到 [src/modules/base/static/svg](/d:/NodeFiles/Projects/auth-vue/src/modules/base/static/svg)
3. 命名成 `icon-xxx.svg`
4. 运行项目或等待 Vite 热更新
5. 在菜单管理里直接选择 `icon-xxx`

### 方式二：想让“非 `icon-` 前缀”的 SVG 也能出现在菜单下拉

需要修改 [src/modules/base/components/menu/icon.vue](/d:/NodeFiles/Projects/auth-vue/src/modules/base/components/menu/icon.vue) 里的筛选逻辑。

例如现在是：

```ts
const list = ref(svgIcons.filter(e => e.indexOf('icon-') === 0));
```

如果你想让全部 SVG 都能选，可以改成：

```ts
const list = ref(svgIcons);
```

或者你想保留部分规则，也可以按自己的命名分组筛选。

## 对新增 SVG 的建议

- 文件名保持小写，单词之间用 `-`
- 菜单图标统一使用 `icon-` 前缀，便于和普通业务 SVG 区分
- 尽量使用单色 SVG，配合 `fill: currentColor` 更容易跟随主题色
- 优先确保 SVG 带有合理的 `viewBox`
- 如果图标来自设计平台，建议先做一次精简，避免无用元数据太多

## 一句话总结

当前“目录/菜单”可选图标，本质上就是项目里所有注册 SVG 中，名称以 `icon-` 开头的那一批；要新增可选项，最稳妥的做法是在 `src/modules/base/static/svg` 下新增一个 `icon-xxx.svg` 文件。
