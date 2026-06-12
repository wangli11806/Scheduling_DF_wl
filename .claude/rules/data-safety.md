# 数据安全保护规则

**优先级最高。违反此规则的后果是用户数据丢失，不可恢复。**

## 核心禁令

### 绝对禁止的操作

以下命令在本地和 ECS 上**绝对禁止执行**，无例外：

```bash
# 禁止恢复/覆盖数据库文件
git restore schedule.db
git checkout schedule.db
git checkout -- schedule.db
git checkout HEAD -- schedule.db

# 禁止回退涉及 schedule.db 的提交
git reset --hard HEAD~N   # 除非先确认不含数据库文件

# 禁止删除数据库
rm schedule.db
rm -f schedule.db

# 禁止 SQLite 破坏性操作（除非带精确 WHERE）
DROP TABLE ...            # 永远禁止
DELETE FROM ...           # 必须带 WHERE，且条件不能用变量拼接
```

### git 操作安全规则

1. **schedule.db 已从 git 追踪移除**（commit `95db905`），任何包含它的提交都会被 pre-commit hook 拦截
2. 执行任何 `git restore`、`git checkout`、`git reset` 前，必须先 `git status` 确认影响的文件列表
3. 如果看到 `schedule.db` 在列表中，**立即停止**，改用安全方式处理

## 数据库备份机制

### 部署前自动备份

每次部署到 ECS 前，强制执行：

```bash
# 本地备份 ECS 数据库
scp root@115.29.235.170:/opt/schedule/schedule.db "数据备份/schedule_$(date +%Y-%m-%d_%H%M).db"

# 本地备份本地数据库
cp schedule.db "数据备份/schedule_local_$(date +%Y-%m-%d_%H%M).db"
```

### 备份目录

`数据备份/` 目录存放所有数据库备份，不受 git 管理（已加入 .gitignore）。

## 为什么

- 2026-06-09：schedule.db 被错误提交到 git（`f3951a7`）
- 2026-06-12：执行 `git restore schedule.db` 将本地数据库恢复为 6/9 旧版本，丢失 3 天内所有操作数据
- 根因：文件被 git 追踪，.gitignore 无效，`restore` 直接覆盖

## 关联

- [[log-management]] — 日志文件同理，不进 git
- [[workflow]] — 部署流程包含自动备份步骤
- [[test-data-safety]] — 测试数据隔离规则
