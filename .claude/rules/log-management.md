---
name: log-management
description: 日志约束——日志文件不进入版本控制，推送前自动检查清理
---

# 日志管理规范

## 规则

**日志文件严禁进入版本控制。每次提交/推送代码到 Git 远程仓库前，必须检查并清理无效日志。**

## 日志文件约束

### 应被 .gitignore 排除的文件

- `service_error.log` / `service_error*.log`
- `service_output.log` / `service_output*.log`
- `logs/error/` 目录下所有文件
- `logs/output/` 目录下所有文件
- `schedule.db`（生产数据库文件）

### 日志轮转

- 服务日志（`service_error*.log`、`service_output*.log`）由 Python logging 模块自动轮转
- 轮转后的旧日志同样被 gitignore 覆盖，不进入版本控制
- 如发现日志文件超过 10MB，提醒用户清理

## 推送前检查（每次 git push 前自动执行）

### 检查清单

1. `git status` 中是否有日志文件出现在 unstaged/modified 区域
2. `.gitignore` 是否包含 `service_error*.log`、`service_output*.log`、`logs/`
3. 是否有已被 git tracked 的日志文件（`git ls-files | grep -E '\.log$'`）

### 自动清理

如果发现以上情况：

```bash
# 确认 .gitignore 包含日志规则
grep -q "service_error" .gitignore && grep -q "service_output" .gitignore && grep -q "logs/" .gitignore

# 从 git 跟踪中移除日志文件（不删除实际文件）
git rm --cached service_error*.log service_output*.log 2>/dev/null
git rm --cached logs/error/*.log logs/output/*.log 2>/dev/null

# 清空日志文件内容（释放磁盘空间）
echo "" > service_error.log
echo "" > service_output.log
echo "" > logs/error/service_error.log
echo "" > logs/output/service_output.log
```

### 与 deploy skill 的关系

deploy skill 的步骤4已包含部署后日志清理。本规则覆盖的是**推送前本地检查**，两者配合：
- **推送前**（本规则）→ 确保 log 不进 git
- **部署后**（deploy skill）→ 确保 ECS 上 log 不膨胀

## .gitignore 基准

项目 .gitignore 必须包含以下行：

```
__pycache__/
*.py[cod]
*.db
service_error*.log
service_output*.log
logs/
```
