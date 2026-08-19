# 排班系统

客服排班管理系统。Python Flask + SQLite + 纯 HTML/CSS/JS。阿里云 ECS 部署。

## 行为规则（入口）

具体规则见 `.claude/rules/`，收到任务时遵循：
- **[workflow](.claude/rules/workflow.md)** — 改代码前先提问划清边界
- **[component-styles](.claude/rules/component-styles.md)** — 全局组件必须复用 shared.css/js
- **[sticky-header](.claude/rules/sticky-header.md)** — 吸顶表头 sticky 加 th 上
- **[auto-learning](.claude/rules/auto-learning.md)** — 失败≥3次自动总结规则
- **[test-data-safety](.claude/rules/test-data-safety.md)** — 测试数据带前缀、测完清理、绝不动生产数据
- **[periodic-review](.claude/rules/periodic-review.md)** — 每7天审查 .claude 文件是否有过时/冗余/冲突
- **[log-management](.claude/rules/log-management.md)** — 日志不进 git，推送前自动检查清理
- **[data-safety](.claude/rules/data-safety.md)** — 数据安全最高优先级，禁止 git restore schedule.db，部署前自动备份

## 常用命令

```bash
python app.py           # 本地开发 http://127.0.0.1:5000
/deploy                 # 提交→推送Gitee→SSH部署ECS
```

## 项目结构

```
排班系统/
├── app.py                # 后端（Flask路由、SQLite、导入导出、通知）
├── requirements.txt       # flask, openpyxl, waitress, chinesecalendar
├── schedule.service       # systemd 服务配置
├── static/                # 前端页面 + 公共组件
│   ├── *.html             # 各页面（每页独立 <style> + <script>）
│   └── shared.css / shared.js  # 公共样式和脚本（组件库）
├── scripts/               # 辅助脚本（密码设置、一次性导入/调试）
├── logs/                  # 运行日志
└── 数据备份/              # 数据库备份（不入 git）
```

## 架构要点

- **DB**: SQLite，新增字段用 `try/except ALTER TABLE ADD COLUMN`
- **前端**: 无框架，API 调用用 shared.js 的 `apiGet()`/`apiPost()`，路由前缀 `/api/`
- **Excel**: openpyxl，中国工作日: chinesecalendar
- **部署**: 使用 `/deploy` 命令
