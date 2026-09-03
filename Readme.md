# 客服排班系统

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 首次部署需设置登录密码（已设置过可跳过）
python scripts/setup_password.py

# 3. 启动后端（数据库自动创建并初始化）
python app.py

# 4. 打开浏览器访问登录页
# 本地：http://127.0.0.1:5000
# 云服务器：http://47.102.102.115:5000
```

默认用户名 `admin`、密码 `paiban2026`，可通过 `python scripts/setup_password.py` 修改。密码哈希存储在 `auth_config.json`（不入 git），机器人查询 token 也在此文件的 `bot_token` 字段。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（单页面应用） |
| 后端 | Python Flask |
| 数据库 | SQLite（单文件，零配置） |
| 服务器 | waitress（跨平台生产服务器） |
| Excel | openpyxl（导入导出） |

---

## 项目文件

```
排班系统/
├── app.py                  # Flask 后端（API + 数据库 + 鉴权 + 月度排班）
├── requirements.txt        # Python 依赖
├── schedule.service        # Linux systemd 服务配置
├── schedule.db             # SQLite 数据库（自动生成，不入 git）
├── auth_config.json        # 登录凭证 + 机器人 token（不入 git）
├── static/                 # 前端页面 + 公共组件
│   ├── login.html          # 登录页
│   ├── shared.css          # 公共样式（侧边栏、按钮、弹窗、表格、多选等）
│   ├── shared.js           # 公共脚本（API 封装、多选组件）
│   ├── 总览.html           # 总览看板（/overview）
│   ├── 排班表.html         # 排班表（日/周/月视图）（/schedule）
│   ├── 排班表_移动端.html  # 排班表移动端（/schedule-mobile）
│   ├── 月度排班.html       # 月度排班（/monthly-schedule）
│   ├── 原始排班.html       # 原始排班表（/raw-schedule）
│   ├── 工作安排.html       # 工作安排（/work-arrangement）
│   ├── 排班调整.html       # 排班调整（/schedule-adjustment）
│   ├── 员工管理.html       # 员工管理 CRUD + 导入（/employee）
│   ├── 班次设置.html       # 班次设置（/shift）
│   ├── 月度时长统计.html   # 排班时长统计（/monthly-hours）
│   └── 工作安排统计.html   # 工作安排统计（/work-stats）
├── scripts/                # 辅助脚本
│   ├── setup_password.py   # 登录用户名/密码设置工具
│   ├── run_server.py       # 启动脚本（NSSM 注册 Windows 服务用）
│   └── ...                 # 一次性导入/调试脚本
├── logs/                   # 运行日志（error/output，不入 git）
├── 数据备份/               # 数据库备份（不入 git）
└── Readme.md               # 本文件
```

> 页面通过英文路由访问（如 `/overview`、`/schedule`、`/employee`），登录后从 `/` 进入排班表。前端文件统一放在 `static/` 目录，由 Flask `send_static_file` 提供。

---

## 数据库设计

### employees（员工表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | EMP001（自增） |
| name | TEXT UNIQUE | 员工姓名 |
| team | TEXT | 在线组/热线组/售后组/综合组/VIP组/质检组/支持组 |
| position | TEXT | 客服/主管/新人/其他 |
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

### monthly_schedules（月度排班表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| schedule_date | TEXT | 日期 YYYY-MM-DD |
| employee_name | TEXT | 员工姓名 |
| shift_name | TEXT | 班次名称（仅 A班/B班/C班） |
| finalized | INTEGER | 是否已最终保存（0/1） |
| UNIQUE(schedule_date, employee_name) | | 每人每天只能有一条 |

> 月度排班按月编辑，最终保存（finalize）后锁定当月不可修改，并将数据导入 `raw_schedules` 和 `schedules` 两张表。

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

### leave_records（排班调整记录表：加班/休假/换班/换休）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| type | TEXT | overtime=加班 / leave=休假 / 换班 / 换休 |
| leave_type | TEXT | 休假类型：调休/病假/年假/奖励假期/其他（仅休假记录） |
| team | TEXT | 所属团队 |
| leave_date | TEXT | 加班/休假日期 YYYY-MM-DD |
| dongfu_id | TEXT | 东福工号（自动查询填入） |
| employee_name | TEXT | 员工姓名 |
| start_time | TEXT | 开始时间 HH:MM（全天休假为空） |
| end_time | TEXT | 结束时间 HH:MM（全天休假为空） |
| hours | REAL | 时长（自动计算，支持跨天、扣除餐休；全天休假为0） |
| remark | TEXT | 备注（最多200字） |
| submitter | TEXT | 提交人（从主管中选择） |
| deduction | REAL | 扣除餐休时长（0表示未扣除） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 最后修改时间 |

> 休假支持「全天」或「按小时」（按小时需填开始/结束时间并可选扣除餐休）。原「放休」已并入休假（请假类型=调休）。加班/换班和换休在排班表上以 tag 形式显示，仅影响当日上班状态判定。

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
GET    /api/employees/roster?token=<TOKEN>  有效员工名单（排除岗位「其他」，供外部系统调用）
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
GET    /api/schedules/external?token=<TOKEN>&start=&end=  对外排班查询（token 鉴权，供外部系统调用）
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

### 月度排班

```
GET    /api/monthly-schedules?year_month=YYYY-MM     查询某月全部月度排班（含 finalized 标记）
POST   /api/monthly-schedules                       保存/删除单个单元格班次 {schedule_date, employee_name, shift_name}
POST   /api/monthly-schedules/finalize              最终保存 {year_month}，导入 raw_schedules 并锁定
GET    /api/monthly-schedules/export?year_month=      Excel 导出（样式与页面一致）
```

- 班次仅支持 `A班`/`B班`/`C班`；`shift_name` 为空则删除该单元格记录
- 已 finalize 的月份不可再修改，需重新编辑时需先解除锁定
- finalize 会删除当月已有 `raw_schedules`/`schedules` 后重新导入，并标记 `finalized=1`

### 工作安排

```
GET    /api/assignments?date=            查询某日安排
POST   /api/assignments                  批量保存 {date, assignments: [{employee_name, work_types, lunch_slot, dinner_slot}, ...]}
```

工作类型：热线、在线、工单、反向工单、自主售后、售后单、紧急、本地生活

### 排班调整

```
GET    /api/leave-records?team=&month=&type=  列表（支持团队、月份、类型筛选）
POST   /api/leave-records                     新增（type=overtime/leave/rest/换班/换休）
PUT    /api/leave-records/<id>                编辑
DELETE /api/leave-records/<id>                删除（leave 类型同步清除排班）
GET    /api/leave-records/export?team=&month=&employees=  Excel 导出
GET    /api/schedule/lookup?employee=&date=   查询某员工某日排班
GET    /api/swap-records?team=&month=         换班记录列表
POST   /api/swap-records                      提交换班/换休
```

**五种记录类型**：

| type | 说明 | 时间字段 | 排班影响 |
|------|------|----------|----------|
| overtime | 加班 | 必填 | 不修改排班，排班表显示红色"加班"tag |
| leave | 休假 | 全天可不填/按小时必填 | 不修改排班，排班表显示"休假"tag（全天/按小时） |
| 换班 | 换班 | 必填 | 同加班，工时附加到当日在班时长 |
| 换休 | 换休 | 必填 | 同休假，校验总休息时长不超过班次工时 |

**时长计算**（除全天休假外）：结束时间 - 开始时间 - 扣除餐休时长（若开启），支持跨天。全天休假时长为 0，按小时休假按上述公式计算。

**休假类型（leave_type）**：调休/病假/年假/奖励假期/其他，仅休假记录填写。原「放休（rest）」已合并为休假+调休。

**换班/换休逻辑**：换班不直接修改排班表，而是拆分为记录——替班日期为替班人创建「换班」记录（附加工时），原班次日期为原班人创建「换休」记录（记为休息），工时取所换班次的 `work_hours`。同时写入 `swap_records` 表留痕。

导出时开始/结束时间自动拼接日期（如 `2026-05-29 09:00`），跨天场景结束时间自动加一天。

### 月度时长统计

```
GET    /api/monthly-hours-stats?year=&month=&work_system=&teams=  统计查询
GET    /api/monthly-hours-stats/export                               Excel 导出
```

基于原始排班表（`raw_schedules`）统计每位员工的月度排班时长，与工时制度时长对比计算差额。支持按工时制度（`work_system`）和团队（`teams`，逗号分隔）筛选。

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

### 通知设置（已废弃）

> ⚠️ 钉钉群通知功能已移除。`/api/notify/*` 路由、`send_daily_notice.py`、`notify_config.json`、`通知设置.html` 均已删除，仅保留机器人排班查询的 `bot_token`（见下文）。以下接口不再可用：

```
GET    /api/notify/config                读取配置（已移除）
POST   /api/notify/config                保存配置并同步计划任务（已移除）
POST   /api/notify/test                  发送 Webhook 测试消息（已移除）
POST   /api/notify/send                  手动发送通知 {task_id, date?}（已移除）
GET    /api/notify/preview?date=&prefix=&suffix=  预览消息内容（已移除）
POST   /api/notify/task                  新增定时任务（已移除）
PUT    /api/notify/task/<id>             编辑定时任务（已移除）
DELETE /api/notify/task/<id>             删除定时任务（已移除）
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
    {"employee": "张三", "team": "在线组", "shift": "A班", "start_time": "09:00", "end_time": "18:00",
     "working": true, "rest_hours": 0.0},
    {"employee": "李四", "team": "热线组", "shift": "B班", "start_time": "09:00", "end_time": "18:00",
     "working": false, "rest_hours": 8.0}
  ]
}
```

仅返回在职员工（`status='active'`），已离职/失效的不会出现。

返回字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| working | bool | 有效上班状态。全天休假/换休为 false；否则 `(班次工时 + 加班/换班工时) - (换休工时) - (按小时休假工时) > 0` 为 true |
| rest_hours | float | 当日换休总小时数，用于了解不上班的原因 |

### 对外排班查询（Token 鉴权）

按排班日期范围返回排班记录及员工信息，供外部系统调用。Token 存在 `auth_config.json` 的 `schedules_token` 字段（独立于 `bot_token`、`roster_token`）。

```
GET    /api/schedules/external?token=<TOKEN>&start=YYYY-MM-DD&end=YYYY-MM-DD
```

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| token | 是 | `auth_config.json` 中的 `schedules_token` |
| start | 是 | 排班开始日期 YYYY-MM-DD |
| end | 是 | 排班结束日期 YYYY-MM-DD |

返回示例：

```json
{
  "ok": true,
  "count": 55,
  "data": [
    {"日期": "2026-05-01", "东福工号": "SH-1744", "姓名": "徐文妍", "团队": "VIP组", "子团队": "", "班次": "E班"},
    {"日期": "2026-05-01", "东福工号": "SH-3803", "姓名": "朱灿灿", "团队": "VIP组", "子团队": "", "班次": "休息"}
  ]
}
```

返回全部员工（含离职）的排班记录；员工已删除或不在花名册时，工号/团队/子团队为空字符串。

### 用餐安排查询（Token 鉴权）

按日期返回员工当天的用餐安排（午餐/晚餐时段及时长），供外部机器人调用。Token 存在 `auth_config.json` 的 `meal_token` 字段（独立于 `bot_token`、`roster_token`、`schedules_token`）。

```
GET    /api/bot/meals?token=<TOKEN>&date=YYYY-MM-DD
```

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| token | 是 | `auth_config.json` 中的 `meal_token` |
| date | 是 | 日期 YYYY-MM-DD |

返回示例：

```json
{
  "ok": true,
  "date": "2026-09-02",
  "count": 20,
  "meals": [
    {"date": "2026-09-02", "employee_id": "SH-3095", "employee_name": "唐俊", "team": "售后组",
     "lunch": {"start_time": "12:00", "end_time": "13:00", "duration_minutes": 60},
     "dinner": null},
    {"date": "2026-09-02", "employee_id": "SH-5028", "employee_name": "张文俊", "team": "售后组",
     "lunch": {"start_time": "13:30", "end_time": "14:00", "duration_minutes": 30},
     "dinner": {"start_time": "19:30", "end_time": "20:00", "duration_minutes": 30}}
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| employee_id | string | 员工东福工号（`dongfu_id`），无则为空字符串 |
| lunch / dinner | object | 午餐/晚餐时段，`{start_time, end_time, duration_minutes}`；当天未安排该餐则为 `null` |

仅返回在职员工（`status='active'`）且当天至少安排了一餐的记录。

### 工作安排查询（Token 鉴权）

按日期返回员工当天的工作安排（工作类型），供外部机器人调用。Token 存在 `auth_config.json` 的 `work_token` 字段（独立于 `bot_token`、`roster_token`、`schedules_token`、`meal_token`）。

```
GET    /api/bot/work-arrangements?token=<TOKEN>&date=YYYY-MM-DD
```

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| token | 是 | `auth_config.json` 中的 `work_token` |
| date | 是 | 日期 YYYY-MM-DD |

返回示例：

```json
{
  "ok": true,
  "date": "2026-09-07",
  "count": 6,
  "works": [
    {"date": "2026-09-07", "employee_id": "SH-3595", "employee_name": "李娜", "team": "热线组",
     "work_types": ["热线"]}
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| employee_id | string | 员工东福工号（`dongfu_id`），无则为空字符串 |
| work_types | array | 工作类型数组，如 `["热线"]`、`["工单", "反向工单"]` |

仅返回在职员工（`status='active'`）且当天有工作类型的记录。

### 实际工作时长查询（Token 鉴权）

按月（可选东福工号）返回员工当月实际工作时长，供外部系统调用。口径：排班班次工时 + 按小时加班 - 请假/调休/放休扣减。Token 存在 `auth_config.json` 的 `work_hours_token` 字段（独立于 `bot_token`、`roster_token`、`schedules_token`、`meal_token`、`work_token`）。

```
GET    /api/actual-work-hours?token=<TOKEN>&month=YYYY-MM[&dongfu_id=SH-XXXX]
```

参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| token | 是 | `auth_config.json` 中的 `work_hours_token` |
| month | 是 | 年月 YYYY-MM |
| dongfu_id | 否 | 东福工号，如 `SH-4909`；传了只返回该员工，不传返回全部在职员工 |

返回示例：

```json
{
  "ok": true,
  "count": 1,
  "data": [
    {"年月": "2026-07", "东福工号": "SH-4584", "员工姓名": "刘平安", "团队": "在线组", "实际工作时长": 176.0}
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| 实际工作时长 | float | 当月实际上班小时数，单位 h，保留 1 位小数 |

返回当月有排班/调整记录的员工（含已离职、失效员工；已彻底删除的员工只返回姓名与实际时长，工号/团队为空）。

---

## 页面间跳转

| 来源 | 目标 | 方式 |
|------|------|------|
| 总览页月历 | 排班表 | `/schedule?date=2026-05-15&view=day` |
| 排班表加班标记 | 排班调整 | `/schedule-adjustment?employee=张三`（自动筛选该员工） |

---

## 钉钉群通知（已废弃）

> ⚠️ 此功能已移除，以下内容仅为历史记录，当前系统不再支持钉钉群通知。机器人排班查询（`/api/bot/schedules`）仍可用。

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

# 3. 安装依赖（创建 venv 虚拟环境）
ssh root@<公网IP>
apt update && apt install python3-pip python3-venv -y
cd /opt/schedule && python3 -m venv venv
./venv/bin/pip install -r requirements.txt

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
./venv/bin/pip install -r requirements.txt
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

将 `scripts/run_server.py` 注册为 Windows 服务（如通过 NSSM），可实现开机自启和后台运行。

---

## 注意事项

- **员工是否上班的判断逻辑**（`wh` = 排班班次工时 + 加班/换班工时，`rh` = 换休工时，`lh` = 按小时休假工时）：

  | 场景 | 排班 | 标签 | 结果 |
  |------|------|------|------|
  | 正常上班 | wh>0 | 无 | 上班 |
  | 全天休假/换休 | wh>0 | 全天休假 或 换休 | 不上班（优先级最高，全天不上） |
  | 按小时休假 | wh>0 | 按小时休假 | wh−rh−lh>0 则上班，否则不上 |
  | 加班/换班 | wh≥0 | 加班/换班 | 上班 |
  | 休息日 | wh=0 | 无 | 不上班 |
  | 休息日替班 | wh=0 | 加班/换班 | 上班 |

  该逻辑应用于：总览页上班人数统计、工作安排页员工列表、排班表视图筛选、机器人排班查询。换休时长提交时校验不超过当日班次工作时长。
  
- **登录鉴权**：已启用用户名+密码登录，默认 `admin` / `paiban2026`，通过 `python scripts/setup_password.py` 修改
- **auth_config.json**：不入 git，首次部署或迁移服务器后需运行 `python scripts/setup_password.py`
- **数据库备份**：`schedule.db` 需定期备份，建议 crontab 定时执行 `cp schedule.db backup/schedule_$(date +%Y%m%d).db`
- **文件迁移**：部署到新服务器后，`schedule.db` 和 `auth_config.json` 需从旧环境手动迁移
- SQLite 适合小团队，高并发建议切换 MySQL/PostgreSQL
