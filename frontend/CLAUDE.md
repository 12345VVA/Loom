# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Loom-vue 8.x - A modular Vue 3 + TypeScript + Vite admin framework with plugin-based architecture and rapid CRUD development.

## Commands

```bash
pnpm dev          # Start dev server (http://localhost:9000)
pnpm build        # Production build
pnpm build-static # Static mode build
pnpm build-demo   # Demo mode build
pnpm preview      # Preview build
pnpm type-check   # TypeScript check (vue-tsc)
pnpm lint         # ESLint with auto-fix
pnpm format       # Prettier format src/
```

## Path Aliases

```
/@  → ./src
/$  → ./src/modules
/#  → ./src/plugins
/~  → ./packages
```

## Architecture

### Directory Structure

```
src/
├── cool/           # Core: bootstrap, service, hooks, module, router
├── config/         # Environment configs (index, dev, prod, proxy)
├── modules/        # Business modules (base, dict, task, user...)
├── plugins/        # Plugins (crud, echarts, i18n, upload, element-ui)
├── App.vue
└── main.ts

packages/           # Source packages (@cool-vue/crud, @cool-vue/vite-plugin)
build/cool/         # EPS type definitions (eps.d.ts, eps.json)
```

### Module Structure

```
demo/
├── config.ts       # Required - module configuration
├── index.ts        # Module exports (useDemo pattern)
├── views/          # View routes (nested under /)
├── pages/          # Page routes (standalone)
├── components/     # Components
├── store/          # Pinia state
├── directives/     # Vue directives
└── hooks/          # Custom hooks
```

### Key Conventions

1. **File naming**: Use kebab-case (e.g., `student-info.vue`)
2. **Component cache name**: Use `defineOptions({ name: "demo" })` for route caching
3. **Export pattern**: `useModuleName` for module exports (e.g., `useDict`, `useBase`)
4. **Service types**: See `build/cool/eps.d.ts` for API type definitions

---

## CRUD Development (@cool-vue/crud)

### Basic CRUD Page

```vue
<template>
  <cl-crud ref="Crud">
    <cl-row>
      <cl-refresh-btn />
      <cl-add-btn />
      <cl-multi-delete-btn />
      <cl-flex1 />
      <cl-search ref="Search" />
    </cl-row>

    <cl-row>
      <cl-table ref="Table" />
    </cl-row>

    <cl-row>
      <cl-flex1 />
      <cl-pagination />
    </cl-row>

    <cl-upsert ref="Upsert" />
  </cl-crud>
</template>

<script setup lang="ts">
import { useCrud, useTable, useUpsert, useSearch } from "@cool-vue/crud";
import { useCool } from "/@/cool";

const { service } = useCool();

const Crud = useCrud(
  { service: service.base.sys.user },
  (app) => app.refresh()
);

const Table = useTable({
  columns: [
    { type: "selection" },
    { label: "Name", prop: "name", minWidth: 120 },
    { type: "op", buttons: ["edit", "delete"] }
  ]
});

const Upsert = useUpsert({
  items: [
    { label: "Name", prop: "name", component: { name: "el-input" } }
  ]
});

const Search = useSearch();
</script>
```

---

## cl-upsert (新增/编辑表单)

### Dynamic Form Items (Conditional Display)

Use function form for conditional rendering:

```ts
const Upsert = useUpsert({
  items: [
    // Static item
    { label: "Name", prop: "name", component: { name: "el-input" } },

    // Dynamic item - only show in edit mode, disabled when editing
    () => ({
      label: "Code",
      prop: "code",
      component: {
        name: "el-input",
        props: { disabled: Upsert.value?.mode === "update" }
      },
      hidden: Upsert.value?.mode !== "update"  // Only show in edit mode
    }),
  ]
});
```

Available modes: `"add"`, `"update"`, `"info"`

### Events Hook

```ts
const Upsert = useUpsert({
  items: [...],
  onOpen() {},                    // Dialog opens
  onInfo(data, { next, done }) {}, // Fetch detail (edit mode)
  onOpened(data) {},               // After data loaded
  onSubmit(data, { next, close, done }) {}, // Submit
  onClose(action, done) {},        // Close dialog
  onClosed() {},                   // After closed
});
```

### Form Validation

```ts
const Upsert = useUpsert({
  items: [
    {
      label: "Phone",
      prop: "phone",
      component: { name: "el-input" },
      rules: [{
        validator: (_rule, value, callback) => {
          if (!value) return callback(); // Optional
          if (/^1[3-9]\d{9}$/.test(value)) {
            callback();
          } else {
            callback(new Error("Invalid phone format"));
          }
        },
        trigger: "blur"
      }]
    }
  ]
});
```

### Group Display (Tabs)

```ts
const Upsert = useUpsert({
  items: [
    {
      type: "tabs",
      props: {
        type: "card",
        labels: [
          { label: "Basic Info", value: "base" },
          { label: "Other Info", value: "other" }
        ]
      }
    },
    { label: "Name", prop: "name", group: "base", component: { name: "el-input" } },
    { label: "Remark", prop: "remark", group: "other", component: { name: "el-input" } },
  ]
});
```

### Nested Children (cl-form-card)

```ts
{
  component: {
    name: "cl-form-card",
    props: { label: "Contact Info", expand: true }
  },
  children: [
    { label: "Phone", prop: "phone", component: { name: "el-input" } },
    { label: "Email", prop: "email", component: { name: "el-input" } }
  ]
}
```

---

## cl-table (表格)

### Basic Columns

```ts
const Table = useTable({
  autoHeight: false,  // Set false in dialogs
  contextMenu: ["refresh"],
  columns: [
    { type: "selection" },
    { type: "index", label: "#" },
    { label: "Name", prop: "name", minWidth: 120 },
    { label: "Time", prop: "createTime", minWidth: 170, sortable: "desc" },
    { type: "op", buttons: ["edit", "delete"] }
  ]
});
```

### Dict Matching

```ts
{
  label: "Status",
  prop: "status",
  dict: [
    { label: "Enabled", value: 1, type: "success" },
    { label: "Disabled", value: 0, type: "danger" }
  ],
  dictColor: true,  // Use different colors
}
```

### Column Component

```ts
{
  label: "Avatar",
  prop: "avatar",
  component: { name: "cl-image", props: { size: 40 } }
},
{
  label: "Status",
  prop: "status",
  component: { name: "cl-switch" }
}
```

### Header Search

```ts
{
  label: "Name",
  prop: "name",
  search: {
    component: { name: "el-input", props: { placeholder: "Search name" } }
  }
}
```

### Custom Column Slot

```vue
<cl-table ref="Table">
  <template #column-name="{ scope }">
    <span>{{ scope.row.name }}</span>
  </template>
</cl-table>
```

### Operation Buttons

```ts
{
  type: "op",
  width: 200,
  buttons: [
    "edit",
    "delete",
    {
      label: "Custom",
      type: "primary",
      onClick({ scope }) {
        console.log(scope.row);
      }
    },
    {
      label: "More",
      children: [
        { label: "View", onClick({ scope }) {} },
        { label: "Disable", onClick({ scope }) {} }
      ]
    }
  ]
}
```

### Hidden/Show Column

```ts
{
  label: "ID",
  prop: "id",
  hidden: computed(() => active.value !== "company")
}
```

---

## cl-form (表单)

### Basic Form

```ts
const Form = useForm();

Form.value?.open({
  title: "Form Title",
  items: [
    {
      label: "Name",
      prop: "name",
      required: true,
      component: { name: "el-input" }
    }
  ],
  on: {
    submit(data, { close }) {
      close();
    }
  }
});
```

### Component Options

```ts
{
  label: "Type",
  prop: "type",
  component: {
    name: "el-select",
    props: { clearable: true },
    options: [
      { label: "Type A", value: 1 },
      { label: "Type B", value: 2 }
    ]
  }
}
```

### Custom Component (vm)

```ts
import CustomSelect from "./custom-select.vue";

{
  label: "Custom",
  prop: "custom",
  component: {
    vm: CustomSelect  // Use component instance
  }
}
```

### Hidden Field

```ts
{
  label: "Password",
  prop: "password",
  hidden: ({ scope }) => scope.status !== 1,
  component: { name: "el-input" }
}
```

---

## cl-search (搜索)

```ts
const Search = useSearch({
  items: [
    {
      label: "Name",
      prop: "name",
      component: {
        name: "el-input",
        props: {
          clearable: true,
          onChange(val) {
            refresh({ name: val, page: 1 });
          }
        }
      }
    }
  ]
});
```

---

## cl-adv-search (高级搜索)

```vue
<template>
  <cl-crud>
    <cl-adv-btn>Advanced Search</cl-adv-btn>
    <cl-adv-search ref="AdvSearch" />
  </cl-crud>
</template>

<script setup>
const AdvSearch = useAdvSearch({
  items: [
    { label: "Name", prop: "name", component: { name: "el-input" } }
  ]
});
</script>
```

---

## Hook System

### bind/submit Hook

```ts
{
  label: "Labels",
  prop: "labels",
  hook: {
    bind(value) {
      return value?.split(",") || [];  // String to array
    },
    submit(value, { form, prop }) {
      form[prop] = value?.join(",");   // Array to string
      form.labels = undefined;          // Remove temp prop
    }
  },
  component: { name: "el-select", props: { multiple: true } }
}
```

### Built-in Hook Methods

```ts
hook: {
  bind: ["split", "number"],  // Split string, convert to number
  submit: ["join"]            // Join array to string
}
```

---

## Module config.ts

```ts
import { ModuleConfig } from "/@/cool";

export default (): ModuleConfig => ({
  enable: true,
  order: 0,
  views: [],        // Nested routes under /
  pages: [],        // Standalone routes
  components: [],   // Global components
  onLoad() {},      // Async data loading
  install(app) {},  // Vue app installation
});
```

---

## Configuration Files

- `src/config/index.ts` - Default config
- `src/config/dev.ts` - Development environment
- `src/config/prod.ts` - Production environment
- `src/config/proxy.ts` - API proxy settings

---

## References

- Official docs: https://cool-js.com
- Demo: https://show.Loom.com (admin/123456)
