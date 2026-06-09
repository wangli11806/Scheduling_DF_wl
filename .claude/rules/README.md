# 规则索引

| 规则 | 文件 | 说明 |
|------|------|------|
| 任务启动流程 | [workflow.md](workflow.md) | 改代码前先提问划清边界；回退版本前备份数据库 |
| 全局组件样式 | [component-styles.md](component-styles.md) | 按钮/多选下拉/弹窗/表格等必须复用 shared.css/js |
| 吸顶表头 | [sticky-header.md](sticky-header.md) | sticky 加在 th 上，不是 thead 上；body 自然滚动 |
| 自动学习 | [auto-learning.md](auto-learning.md) | 失败≥3次自动总结为规则 |
| 测试数据安全 | [test-data-safety.md](test-data-safety.md) | 测试数据带前缀，测完清理，绝不动生产数据 |
| 定期审查 | [periodic-review.md](periodic-review.md) | 每7天审查 .claude 文件 |
| 日志管理 | [log-management.md](log-management.md) | 日志不进 git，推送前检查清理 |
| 端口冲突排查 | [port-conflict-testing.md](port-conflict-testing.md) | 本地测试前检查端口，多进程冲突导致"改了代码没用" |
