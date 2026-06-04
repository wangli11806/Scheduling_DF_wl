# 客服排班系统

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 首次部署需设置登录密码（已设置过可跳过）
python setup_password.py

# 3. 启动后端（数据库自动创建并初始化）
python app.py

# 4. 打开浏览器访问登录页
# 本地：http://127.0.0.1:5000
# 云服务器：http://115.29.235.170:5000
```

默认密码 `paiban2026`，可通过 `python setup_password.py` 修改。密码哈希存储在 `auth_config.json`（不入 git）。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（单页面应用） |
| 后端 | Python Flask |
| 数据库 | SQLite（单文件，零配置） |
| 服务器 | waitress（Windows）/ gunicorn（Linux） |
| Excel | openpyxl（导入导出） |

---

## 项目文件

```
排班系统/
├── app.py                  # Flask 后端（API + 数据库 + 鉴权）
├── login.html              # 登录页
├── setup_password.py       # 密码设置工具
├── requirements.txt        # Python 依赖
├── run_server.py           # 生产模式启动脚本
├── schedule.service        # Linux systemd 服务配置
├── schedule.db             # SQLite 数据库（自动生成，不入 git）
├── send_daily_notice.py    # 排班通知脚本
├── notify_config.json      # 钉钉通知配置
├── shared.css              # 公共样式（侧边栏、按钮、弹窗、表格等）
├── shared.js               # 公共脚本（API 封装、多选组件）
├── 总览.html               # 总览看板
├── 排班表.html             # 排班表（日/周/月视图）
├── 原始排班.html           # 原始排班表
├── 工作安排.html           # 工作安排
├── 加班换班.html           # 加班换班
├── 员工管理.html           # 员工管理（CRUD + 导入）
├── 班次设置.html           # 班次设置
├── 通知设置.html           # 钉钉通知设置
├── 月度时长统计.html       # 排班时长统计
├── 工作安排统计.html       # 工作安排统计
└── Readme.md               # 本文件
```

---

## 数据库设计

### employees（员工表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | EMP001（自增） |
| name | TEXT UNIQUE | 员工姓名 |
| team | TEXT | 在线组/热线组/售后组/综合组/VIP组/质检组/支持组 |
| position | TEXT | 客服/主管/其他 |
| supervisor | TEXT | 上级姓名（选填） |
| dongfu_id | TEXT | 东福工号（选填） |
| work_hour_system | TEXT | 标准工时制/综合计算工时制（选填） |
| entry_date | TEXT | 入职日期 YYYY-MM-DD |
| status | TEXT | active=正常 / inactive=失效 |

### shifts（班次表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | SHF001（自增） |
| name | TEXT UNIQUE | A班/B班/C班/D班/E班（可自行增删 T/F 等） |
| info | TEXT | 早1班/常规班/早2班/晚1班/通宵班 |
| start_time | TEXT | 上班时间 HH:MM |
| end_time | TEXT | 下班时间 HH:MM |
| lunch_start / lunch_end | TEXT | 午餐时段（可空） |
| dinner_start / dinner_end | TEXT | 晚餐时段（可空） |
| work_hours | REAL | 工作时长（自动计算） |

### schedules（排班表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| schedule_date | TEXT | 日期 YYYY-MM-DD |
| employee_name | TEXT | 员工姓名 |
| shift_name | TEXT | 班次名称 |
| UNIQUE(schedule_date, employee_name) | | 每人每天只能有一条排班 |

### raw_schedules（原始排班表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| schedule_date | TEXT | 日期 YYYY-MM-DD |
| employee_name | TEXT | 员工姓名 |
| shift_name | TEXT | 班次名称 |
| UNIQUE(schedule_date, employee_name) | | 每人每天只能有一条 |

> 原始排班支持独立管理，批量操作后**自动单向同步**到排班表。

### daily_assignments（工作安排表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| date | TEXT | 日期 YYYY-MM-DD |
| employee_name | TEXT | 员工姓名 |
| work_types | TEXT | 工作类型 JSON 数组 |
| lunch_slot | TEXT | 午餐时段（可空） |
| dinner_slot | TEXT | 晚餐时段（可空） |
| UNIQUE(date, employee_name) | | 每人每天只能有一条安排 |

### leave_records（加班记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| team | TEXT | 所属团队 |
| leave_date | TEXT | 加班日期 YYYY-MM-DD |
| dongfu_id | TEXT | 东福工号（自动查询填入） |
| employee_name | TEXT | 员工姓名 |
| start_time | TEXT | 加班开始时间 HH:MM |
| end_time | TEXT | 加班结束时间 HH:MM |
| hours | REAL | 加班时长（自动计算，支持跨天、扣除餐休） |
| remark | TEXT | 备注（最多200字） |
| submitter | TEXT | 提交人（从主管中选择） |
| deduction | REAL | 扣除餐休时长（0表示未扣除） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 最后修改时间 |

### swap_records（换班/换休记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| swap_type | TEXT | shift_swap=换班 / rest_swap=换休 |
| person_a | TEXT | 换班人（或被换班人） |
| team_a | TEXT | 换班人所属团队 |
| date_a | TEXT | 换班日期 YYYY-MM-DD |
| shift_a | TEXT | 换班人原班次 |
| person_b | TEXT | 交换人（或被交换人） |
| team_b | TEXT | 交换人所属团队 |
| date_b | TEXT | 交换日期 YYYY-MM-DD |
| shift_b | TEXT | 交换人原班次 |
| remark | TEXT | 备注（必填） |
| operator | TEXT | 操作人（主管） |
| created_at | TEXT | 创建时间 |

---

## API 文档

### 员工

```
GET    /api/employees?status=active      列表（支持状态筛选）
POST   /api/employees                    新增
PUT    /api/employees/<id>               编辑（支持部分更新）
DELETE /api/employees/<id>               删除（有下级时拒绝）
POST   /api/employees/import            批量导入（.xlsx）
GET    /api/employees/template           下载导入模板
```

### 班次

```
GET    /api/shifts                       列表
POST   /api/shifts                       新增
PUT    /api/shifts/<id>                  编辑
DELETE /api/shifts/<id>                  删除
```

### 排班

```
GET    /api/schedules?start=&end=        查询
POST   /api/schedules/batch              批量新增/更新 {entries: [{date, employee, shift}, ...]}
POST   /api/schedules/import             Excel 导入（列表格式：日期/员工/班次三列）
POST   /api/schedules/import-matrix      Excel 导入（矩阵格式：行为员工、列为日期）
GET    /api/schedules/export             Excel 导出
```

矩阵模板：第一列员工姓名，第一行日期（支持 YYYY-MM-DD、M/D、M月D日、D日 等格式），单元格填班次代码（A=A班, B=B班, …，休=休息, 假=请假, 空=休息）。

### 原始排班

```
GET    /api/raw-schedules?start=&end=    查询
POST   /api/raw-schedules/batch          批量新增/更新（自动同步到排班表）
POST   /api/raw-schedules/import         Excel 导入（列表格式）
POST   /api/raw-schedules/import-matrix  Excel 导入（矩阵格式）
GET    /api/raw-schedules/export         Excel 导出
```

### 工作安排

```
GET    /api/assignments?date=            查询某日安排
POST   /api/assignments                  批量保存 {date, assignments: [{employee_name, work_types, lunch_slot, dinner_slot}, ...]}
```

工作类型：热线、在线、工单、反向工单、自主售后、售后单、紧急、本地生活、卡密查询

### 加班换班

```
GET    /api/leave-records?team=&month=   加班列表（支持团队、月份筛选）
POST   /api/leave-records                新增加班记录（自动计算时长、支持扣除餐休）
PUT    /api/leave-records/<id>           编辑加班记录
DELETE /api/leave-records/<id>           删除加班记录
GET    /api/leave-records/export?team=&month=&employees=  Excel 导出
GET    /api/schedule/lookup?employee=&date=  查询某员工某日排班
GET    /api/swap-records?team=&month=    换班记录列表（受页面筛选器控制）
POST   /api/swap-records                 提交换班/换休（互换班次，换休自动创建加班记录）
```

**加班时长计算**：结束时间 - 开始时间 - 扣除餐休时长（若开启）

**换班逻辑**：交换两个日期上两人的排班班次。换休时额外自动为休息变上班的员工创建加班记录，工时取所换班次的 `work_hours`。

导出时开始/结束时间自动拼接加班日期（如 `2026-05-29 09:00`），跨天场景结束时间自动加一天。

### 月度时长统计

```
GET    /api/monthly-hours-stats?year=&month=&work_system=&teams=  统计查询
GET    /api/monthly-hours-stats/export                               Excel 导出
```

根据排班数据统计每位员工的月度排班时长，与工时制度时长对比计算差额。支持按工时制度和团队筛选。

### 工作安排统计

```
GET    /api/assignment-stats?year=&month=&team=  统计查询（默认售后组，支持逗号分隔多团队）
GET    /api/assignment-stats/export               Excel 导出
```

按自然月从 `daily_assignments` 表汇总员工被安排做各项工作的次数。统计维度：反向工单、自主售后、售后单、紧急、本地生活。

### 数据库管理

```
GET    /api/db/stats                     统计信息
GET    /api/db/download                  下载 schedule.db
```

### 通知设置

```
GET    /api/notify/config                读取配置
POST   /api/notify/config                保存配置并同步计划任务
POST   /api/notify/test                  发送 Webhook 测试消息
POST   /api/notify/send                  手动发送通知 {task_id, date?}
GET    /api/notify/preview?date=&prefix=&suffix=  预览消息内容
POST   /api/notify/task                  新增定时任务
PUT    /api/notify/task/<id>             编辑定时任务
DELETE /api/notify/task/<id>             删除定时任务
```

### 机器人排班查询（Token 鉴权）

独立于登录 session，适合机器人/定时任务调用。Token 存在 `auth_config.json` 的 `bot_token` 字段。

```
GET    /api/bot/schedules?token=<TOKEN>&date=YYYY-MM-DD
GET    /api/bot/schedules?token=<TOKEN>&date=YYYY-MM-DD&employee=张三
```

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| token | 是 | `auth_config.json` 中的 `bot_token` |
| date | 是 | 日期 YYYY-MM-DD |
| employee | 否 | 员工姓名，不填返回当天全部在班人员 |

返回示例：

```json
{
  "ok": true,
  "date": "2026-06-05",
  "count": 50,
  "schedules": [
    {"employee": "张三", "team": "在线组", "shift": "A班", "start_time": "09:00", "end_time": "18:00"}
  ]
}
```

仅返回在职员工（`status='active'`），已离职/失效的不会出现。

---

## 页面间跳转

| 来源 | 目标 | 方式 |
|------|------|------|
| 总览页月历 | 排班表 | `排班表.html?date=2026-05-15&view=day` |
| 排班表加班标记 | 加班换班 | `加班换班.html?employee=张三`（自动筛选该员工） |

---

## 钉钉群通知

### 配置步骤

1. 钉钉群 → 群设置 → 智能群助手 → 添加**自定义机器人**
2. 安全设置选择**自定义关键词**，填入 `排班`
3. 复制 Webhook 地址中 `access_token=` 后的内容
4. 打开系统「通知设置」页面，粘贴 Token 并保存
5. 点击「发送测试消息」验证

### 定时任务

| 配置项 | 说明 |
|--------|------|
| 任务名称 | 如「早间排班通知」 |
| 触发时间 | 每天 HH:MM |
| 日期偏移 | 当天/明天/后天 |
| 前缀 | 自定义开头语 |
| 后缀 | 自定义结束语 |
| 启用/停用 | 独立开关 |

### 消息格式

> **前缀**（自定义）
>
> #### 排班通知 2026-05-25 周一
>
> 上班人数：**26人**（含主管）
> 主管（4人）：赵月, 王鹏飞, 俞蕾, 胡玉婷
> 在线组（6人）：孙赟, 张颖, …
> …
>
> **后缀**（自定义）

### 命令行用法

```bash
python send_daily_notice.py --task-id morning       # 手动执行任务
python send_daily_notice.py --task-id evening --date 2026-05-26
python send_daily_notice.py --check-and-send        # 定时调度入口
```

---

## 部署

### 推荐：阿里云 ECS（Linux）

**最低配置：** 1 vCPU / 1 GiB / 40 GB 系统盘 / 1 Mbps 带宽（个人版免费试用 3 个月即可跑）

```bash
# 1. 创建实例（Ubuntu 22.04），开放安全组 TCP 5000 端口
# 2. 上传项目到服务器
scp -r ./* root@<公网IP>:/opt/schedule/

# 3. 安装依赖
ssh root@<公网IP>
apt update && apt install python3-pip -y
cd /opt/schedule && pip install -r requirements.txt gunicorn

# 4. 安装 systemd 服务（开机自启）
cp schedule.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now schedule

# 5. 访问 http://<公网IP>:5000
```

**日常更新部署（已配置 Git 仓库）：**

```bash
cd /opt/schedule && git pull origin main
# 如有新增 Python 依赖，执行：
pip install -r requirements.txt
systemctl restart schedule
```

**常用管理命令：**

```bash
systemctl status schedule      # 查看状态
systemctl restart schedule     # 重启应用
journalctl -u schedule -f      # 查看实时日志
```

**SQLite 数据库备份：**

```bash
# 建议加入 crontab 定时备份
cp /opt/schedule/schedule.db /opt/schedule/backup/schedule_$(date +%Y%m%d).db
```

### 方案 B：Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

### 方案 C：Windows 服务（本地运行）

将 `run_server.py` 注册为 Windows 服务（如通过 NSSM），可实现开机自启和后台运行。

---

## 注意事项

- **登录鉴权**：已启用密码登录，默认密码 `paiban2026`，通过 `python setup_password.py` 修改
- **auth_config.json**：不入 git，首次部署或迁移服务器后需运行 `python setup_password.py`
- **数据库备份**：`schedule.db` 需定期备份，建议 crontab 定时执行 `cp schedule.db backup/schedule_$(date +%Y%m%d).db`
- **文件迁移**：部署到新服务器后，`notify_config.json` 和 `schedule.db` 需从旧环境手动迁移
- SQLite 适合小团队，高并发建议切换 MySQL/PostgreSQL
