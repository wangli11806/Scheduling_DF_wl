---
name: deploy
description: 提交代码 → 推送 Gitee → SSH 部署到阿里云 ECS → 自动检查清单
---

# 部署到阿里云 ECS

将本地代码推送 Gitee 并部署到阿里云 ECS 服务器。

## 执行步骤

### 步骤 1: 检查本地状态

运行 `git status`。如果有未提交的变更：

- 运行 `git diff` 和 `git diff --cached` 查看具体改动
- 生成一个中文 commit message，格式为 `v版本号: 简述变更内容`
- 版本号参考 `git tag --sort=-v:refname | head -5` 的最新版本递增；若无 tag 则从 `v1.0` 开始
- 提交前展示 commit message 给用户确认（如果用户已提供 message 则直接使用）

如果工作区干净，检查 `git log @{u}..HEAD` 是否有未推送的提交。

### 步骤 2: 推送到 Gitee

```bash
git push 排班系统gitee main
```

### 步骤 3: SSH 部署到 ECS

使用 ASKPASS 方式 SSH 连接 ECS（Windows Git Bash 环境）：

```python
import subprocess, os

env = os.environ.copy()
env['SSH_ASKPASS'] = '/d/askpass.sh'
env['SSH_ASKPASS_REQUIRE'] = 'force'

cmd = "cd /opt/schedule && git pull origin main && venv/bin/pip install -r requirements.txt && systemctl restart schedule && sleep 2 && systemctl status schedule --no-pager -l | head -5"

result = subprocess.run(
    ['ssh', '-o', 'StrictHostKeyChecking=no',
     '-o', 'PubkeyAuthentication=no',
     '-o', 'PreferredAuthentications=password',
     'root@47.102.102.115', cmd],
    env=env, capture_output=True, timeout=60, start_new_session=True
)
print(result.stdout.decode('utf-8', errors='replace'))
if result.stderr:
    print(result.stderr.decode('utf-8', errors='replace'))
```

### 步骤 4: 部署后检查

部署成功后，自动执行：

1. **检查 README.md**：如果新增了页面/API/功能，更新 README.md 相应章节
2. **清理日志**：清空 `logs/error/service_error.log` 和 `logs/output/service_output.log`

```bash
# 清空日志文件
echo "" > logs/error/service_error.log
echo "" > logs/output/service_output.log
```

如果 README 需要更新，一并提交推送到 Gitee。

### 步骤 5: 汇总报告

向用户报告：
- 推送的 commit 和变更摘要
- ECS 部署状态（成功/失败）
- service 运行状态
- README 是否更新、日志是否清理
