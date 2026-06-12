---
name: task-clarification
description: 任务启动流程——动手改代码之前必须先向用户提问澄清需求
---

# 任务启动流程

## 规则

**每次收到代码改动需求、新任务、或项目相关的第一次对话时，在动手改代码之前，必须先向用户提问。**

## 目的

通过提问划清任务边界，了解目标、范围、验收标准，避免理解偏差导致返工。

## 提问方向

根据任务类型，从以下维度选择相关的问题：

1. **范围边界** — 这个改动涉及哪些页面/模块？不涉及哪些？有没有容易混淆的相似功能需要区分？
2. **交互细节** — 按钮放哪里？弹窗还是页面内？默认值是什么？排序/筛选规则？
3. **数据来源** — 数据从哪个表/API 获取？字段名是什么？需要关联其他数据吗？
4. **异常处理** — 数据为空时显示什么？操作失败时怎么提示？边界情况怎么处理？
5. **验收标准** — 怎么判断任务完成？需要测哪些路径？
6. **优先级** — 有没有时间限制？依赖其他任务吗？
7. **补充资料** — 有没有参考页面？截图？原型？接口文档？

## 工作流程

1. 用户提出任务需求
2. Claude 分析需求，提出 2-5 个关键澄清问题
3. 用户回答问题
4. 如果有需要的外部资料（如第三方 API 文档、参考实现等），询问用户是否可以提供，如用户没有则主动搜索
5. 搜索到的资料整理后请用户确认，作为需求依据
6. 确认需求无误后，才开始改代码

## 注意

- 问题要具体，不要问"你希望怎么做"这种开放式问题
- 提供合理默认建议，用户可以直接确认
- 简单明确的任务（如"把这个按钮颜色改成红色"）可跳过，直接执行
- 但涉及新页面、新功能、交互变更时，必须走提问流程

## 回退版本前备份数据库

**当用户要求回退代码版本（git reset --hard、git checkout 旧版本、部署旧版本等）时，必须先提醒用户手动备份数据库文件。**

### 为什么

- `schedule.db` 不在 git 版本控制中（.gitignore），回退代码不会自动回退数据库
- 但新旧版本的数据库表结构可能不兼容，导致数据损坏或丢失
- 历史上曾因回退版本忘记备份，丢失了三天内的操作数据

### 执行流程

1. 收到回退指令时，先暂停，提醒用户：
   > ⚠️ 回退前请确认：是否需要先备份 `schedule.db`？上次回退忘记备份导致数据丢失。备份方式：复制 `schedule.db` 到安全位置。
2. 等待用户确认备份完成后，再执行回退操作

## 部署时 schedule.db 冲突处理

**当 ECS 上 `git pull` 因 `schedule.db` 本地修改而冲突时，stash pop 后只用 `git checkout --theirs`，禁止再执行任何 checkout 命令。**

### 部署前备份

**每次部署到 ECS 前，必须先备份云端数据库。**

1. 在项目根目录创建 `数据备份/` 文件夹（如不存在）
2. 从 ECS 下载 `schedule.db` 到 `数据备份/schedule_YYYY-MM-DD.db`
3. 备份完成后才继续部署流程

```bash
# 本地执行
scp root@115.29.235.170:/opt/schedule/schedule.db "数据备份/schedule_$(date +%Y-%m-%d).db"
```

### 部署执行顺序（重要！）

**必须在重启服务之前解决 schedule.db 冲突，否则服务会读到空/旧数据库。**

```bash
# 1. 拉代码（stash 会保存生产 DB）
cd /opt/schedule && git stash && git pull origin main && git stash pop

# 2. 先解决冲突，再重启！
if [ -f "schedule.db~Stashed changes" ]; then
    mv "schedule.db~Stashed changes" schedule.db
    git rm --cached schedule.db 2>/dev/null
    git reset HEAD schedule.db 2>/dev/null
    git stash drop 2>/dev/null
fi

# 3. 确认 DB 存在且非空，然后重启
ls -la schedule.db && systemctl restart schedule
```

**为什么**：2026-06-12 部署时 `systemctl restart` 在冲突解决前执行，服务启动时读取空 DB 后创建了空白数据库，用户写入的数据在后续 `mv` 恢复生产 DB 时被覆盖丢失。6/12 和 6/13 共 43 条工作安排数据丢失，从本地备份恢复。

### 为什么

- `schedule.db` 被错误提交到 git（2026-06-09 的 `f3951a7` 手工保存更改）
- ECS 上生产数据库与 git 中的旧快照不同，pull 时产生冲突
- `git checkout --theirs schedule.db` 取了 stash 中的生产版本 ✓
- 但紧接着 `git checkout schedule.db` 会用 git 中的旧快照覆盖生产数据 ✗
- 2026-06-11 部署时因此丢失了用户两天内新加的放休数据（已通过 stash 恢复）

### 正确做法

```bash
cd /opt/schedule/ && git stash && git pull && git stash pop
# 如果 stash pop 产生 schedule.db 冲突：
git checkout --theirs schedule.db   # 保留生产数据
git restore --staged schedule.db    # 取消暂存
# 到此为止，不要再执行 git checkout schedule.db
systemctl restart schedule
```
