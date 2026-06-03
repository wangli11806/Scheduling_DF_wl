---
name: sticky-header
description: 吸顶表头的正确实现方式——sticky 加在 th 上，不是 thead 上
---

# 吸顶表头正确做法

## 核心规则（两条）

### 1. 页面使用自然滚动

```css
/* 正确：body 自然滚动 */
body {
    min-height: 100vh;
    /* 不要设 height: 100vh; overflow: hidden; */
}

/* 正确：content-body 不要设 overflow */
.content-body {
    /* 不要设 overflow: auto; */
}
```

**错误做法**：`body { height: 100vh; overflow: hidden; }` + `content-body { overflow: auto; }`

### 2. Sticky 加在每个 th 上，不是 thead 上

```css
/* 正确 */
table thead th {
    position: sticky;
    top: 0;
    z-index: 10;
    background: #f9fbfd;
}

/* 错误——不要这样做 */
table thead {
    position: sticky;
    top: 0;
}
```

## 为什么

- `border-collapse: collapse` 会导致 sticky thead 背景透底（复合层问题）
- 每个 `th` 独立 sticky，各自拥有背景色和边框，彻底规避透底问题
- `border-collapse: collapse` 可以保留不用改

## 历史教训

这个问题修了5次才成功，试过的无效方案：
- 调整 overflow → 无效
- thead 加 background → 无效
- border-collapse: separate → 无效
- thead::before 伪元素遮罩 → 无效
- sticky 放 thead 上 → 无效

唯一有效的方案：**sticky 放每个 th 上 + body 自然滚动**。
