---
name: component-styles
description: 全局组件样式规范——按钮、多选下拉、弹窗、表格、标签等，任何页面必须复用 shared.css 中的组件
---

# 全局组件样式规范

项目中所有页面共享 `shared.css` 和 `shared.js`，以下组件已有统一样式，**不得在各页面中重复定义或自创变体**。

## 按钮 (Buttons)

所有按钮使用 `.btn` 基类，配合语义变体：

```html
<button class="btn">默认按钮</button>
<button class="btn btn-primary">主操作</button>
<button class="btn btn-success">确认/保存</button>
<button class="btn btn-warning">警告</button>
<button class="btn btn-danger">删除/危险操作</button>
<button class="btn btn-sm">小按钮</button>
```

- 基础样式：白色背景、圆角 40px（胶囊形）、1px #cbd5e1 边框
- hover 时背景变为 #f8fafc、边框加深
- **不要**自定义按钮颜色/圆角/尺寸，统一用这些 class

## 多选下拉 (Multi-Select)

当用户提到"复选框"、"多选框"、"下拉多选"、"选择多个"等，指的就是这个组件。

**CSS 类名前缀** `.ms-*`（`shared.css` §多选下拉，第92-140行）：
- `.multi-select` — 容器
- `.multi-select-trigger` — 触发器（显示已选标签）
- `.ms-dropdown` — 下拉面板（`position: fixed; z-index: 999`）
- `.ms-search` — 搜索过滤区
- `.ms-options` — 选项列表（最大高度 180px 可滚动）
- `.ms-option` — 单个选项行（内置 checkbox）
- `.ms-actions` — 底部按钮区（清除/确定）
- `.ms-tag` — 已选标签样式（蓝紫底 #eef2ff，圆角 6px）

**JS 初始化** 使用 `shared.js` 中的 `initMultiSelect()` 函数（第44-154行）：

```js
const ms = initMultiSelect({
    containerId: 'teamMs',        // .multi-select 容器的 id
    triggerId: 'teamMsTrigger',   // 触发器元素 id
    searchId: 'teamMsSearch',     // 搜索输入框 id
    selectAllId: 'teamMsAll',     // 全选按钮 id
    optionsId: 'teamMsOptions',   // 选项容器 id
    clearId: 'teamMsClear',       // 清除按钮 id
    okId: 'teamMsOk',             // 确定按钮 id
    getOptions: () => allTeams,   // 返回所有可选项数组
    getSelected: () => selectedTeams, // 返回已选项数组
    setSelected: (arr) => { selectedTeams = arr; }, // 设置已选项
    placeholder: '选择团队',       // 未选时的占位文字
    onChange: () => { /* 选中变化回调 */ }
});
```

**HTML 模板**（每个多选实例都需要这个结构）：

```html
<div class="multi-select" id="teamMs">
  <div class="multi-select-trigger" id="teamMsTrigger"></div>
  <div class="ms-dropdown">
    <div class="ms-search">
      <input type="text" id="teamMsSearch" placeholder="搜索...">
      <div class="ms-select-all" id="teamMsAll">全选</div>
    </div>
    <div class="ms-options" id="teamMsOptions"></div>
    <div class="ms-actions">
      <button class="btn btn-sm" id="teamMsClear">清除</button>
      <button class="btn btn-sm btn-primary" id="teamMsOk">确定</button>
    </div>
  </div>
</div>
```

**选项行为**：
- 点击触发器弹出下拉（自动关闭其他已打开的多选）
- 搜索框实时过滤选项
- 全选/取消全选切换
- 点击外部区域自动关闭
- 已选值以顿号分隔显示在触发器上

## 弹窗 (Modal)

```html
<div class="modal-overlay" id="myModal">
  <div class="modal-dialog">
    <div class="modal-title">标题</div>
    <div class="modal-row"><label>字段名</label><input/></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="save()">保存</button>
    </div>
  </div>
</div>
```

- 打开：`document.getElementById('myModal').classList.add('active')`
- 关闭：`document.getElementById('myModal').classList.remove('active')`
- 宽度 520px，最大 92vw

## 表格 (Table)

- 用 `.table-wrapper` 包裹表格，提供圆角卡片外观
- 吸顶表头规则详见 sticky-header.md

## Toast 消息

- 每个页面需有一个 `<div id="toastMsg" class="toast-msg" style="display:none;"></div>`
- 调用：`showToast('消息内容')`（`shared.js` 第36-41行）

## 状态单选组 (Status Radio Group)

用于排班表中"全部/上班/休息"切换：

```html
<div class="status-radio-group">
  <label class="status-radio"><input type="radio" name="status" value=""> 全部</label>
  <label class="status-radio"><input type="radio" name="status" value="上班"> 上班</label>
  <label class="status-radio"><input type="radio" name="status" value="休息"> 休息</label>
</div>
```

## 团队样式

- 团队背景色用 `td.team-bg-{团队名}`（7个团队各有专属色，见 shared.css 第198-204行）
- 团队标签用 `.team-badge`

## 侧边栏 (Sidebar)

- 固定左侧 190px，`.nav-item` 为导航项，`.nav-item.active` 高亮
- 二级菜单用 `.nav-group` + `.nav-submenu` 结构

---

**核心原则**：新增页面时，先检查 shared.css / shared.js 是否已有现成组件，直接复用，不要重写。
