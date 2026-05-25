# 客服排班系统

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动后端（数据库自动创建并初始化）
python app.py

# 3. 打开浏览器
# http://127.0.0.1:5000
```
公司ip的网址：http://10.55.43.44:5000

首次启动自动创建 `schedule.db` 并写入默认员工和班次数据。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（五个单页面） |
| 后端 | Python Flask |
| 数据库 | SQLite（单文件，零配置） |
| 服务器 | waitress（Windows）/ gunicorn（Linux） |
| Excel | openpyxl（导入导出） |

---

## 项目文件

```
排班系统/
├── app.py              # Flask 后端（所有 API）
├── requirements.txt    # Python 依赖
├── import_feb_schedule.py  # 排班导入工具脚本
├── schedule.db         # SQLite 数据库（自动生成）
├── 总览.html           # 总览看板（统计指标、团队详情、工作安排汇总）
├── 排班表.html         # 排班表页面（日/周/月视图、导入导出、点击班次快捷修改）
├── 工作安排.html       # 工作安排页面（每日工作分配、用餐安排）
├── 员工管理.html       # 员工管理页面（CRUD + 批量导入）
├── 班次设置.html       # 班次设置页面（CRUD）
├── 通知设置.html       # 通知设置页面（钉钉机器人 + 定时任务管理）
├── send_daily_notice.py  # 排班通知脚本（由 Windows 计划任务定时调用）
├── notify_config.json  # 通知配置文件（webhook token + 任务列表）
└── Readme.md           # 本文件
```

---

## 数据库设计

### employees（员工表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | EMP001（自增） |
| name | TEXT UNIQUE | 员工姓名 |
| team | TEXT | 在线组/热线组/售后组/综合组/VIP组/质检组/支持组 |
| position | TEXT | 客服/主管 |
| supervisor | TEXT | 上级姓名（选填） |
| dongfu_id | TEXT | 东福工号（选填） |
| entry_date | TEXT | 入职日期 YYYY-MM-DD |
| status | TEXT | active=正常 / inactive=失效 |

### shifts（班次表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | SHF001（自增） |
| name | TEXT UNIQUE | A班/B班/C班/D班/E班/休息/放休/请假（可自行增删 T/F 等班次） |
| info | TEXT | 早1班/常规班/早2班/晚1班/通宵班 等 |
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
| UNIQUE(schedule_date, employee_name) | | 每人每天只能有一个排班 |

### daily_assignments（工作安排表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| date | TEXT | 日期 YYYY-MM-DD |
| employee_name | TEXT | 员工姓名 |
| work_types | TEXT | 工作类型 JSON 数组 ["热线","在线","工单",...] |
| lunch_slot | TEXT | 午餐时段 12:00-12:30（可空） |
| dinner_slot | TEXT | 晚餐时段 18:00-18:30（可空） |
| UNIQUE(date, employee_name) | | 每人每天只能有一条安排 |

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

矩阵模板：第一列员工姓名，第一行日期（支持 YYYY-MM-DD、M/D、M月D日、D日、纯数字 1-31 等格式），单元格填班次代码（A=A班, B=B班, C=C班, D=D班, E=E班, T=T班, F=F班, 休=休息, 假=请假, 空=休息）。

### 工作安排

```
GET    /api/assignments?date=            查询某日安排
POST   /api/assignments                  批量保存 {date, assignments: [{employee_name, work_types, lunch_slot, dinner_slot}, ...]}
```

工作类型：热线、在线、工单、反向工单、自主售后、售后单、紧急、本地生活、卡密查询
午餐时段：11:30-12:00 / 12:00-12:30 / 12:30-13:00 / 13:00-13:30 / 13:30-14:00
晚餐时段：17:00-17:30 / 17:30-18:00 / 18:00-18:30 / 18:30-19:00 / 19:00-19:30 / 19:30-20:00

### 数据库管理

```
GET    /api/db/stats                     统计信息
GET    /api/db/download                  下载 schedule.db
```

### 通知设置

```
GET    /api/notify/config                读取配置（webhook_token + 任务列表 + 计划任务状态）
POST   /api/notify/config                保存配置并同步 Windows 计划任务
POST   /api/notify/test                  发送 Webhook 测试消息
POST   /api/notify/send                  手动发送通知 {task_id, date?}
GET    /api/notify/preview?date=&prefix=&suffix=  预览消息内容
POST   /api/notify/task                  新增定时任务
PUT    /api/notify/task/<id>             编辑定时任务
DELETE /api/notify/task/<id>             删除定时任务
```

通知消息格式：**前缀（自定义） + 排班模板（按团队统计） + 后缀（自定义）**

### 页面间跳转

总览页月历点击日期可跳转到排班表对应日视图，通过 URL 参数传递：

```
排班表.html?date=2026-05-15&view=day    # 指定日期和视图
排班表.html?date=2026-05-12&view=week   # 指定日期和周视图
```

---

## 钉钉群通知

系统内置钉钉群机器人通知功能，支持**多任务定时推送**排班信息到钉钉群。

### 配置步骤

1. 在钉钉群 → 群设置 → 智能群助手 → 添加**自定义机器人**
2. 安全设置选择**自定义关键词**，填入 `排班`
3. 复制 Webhook 地址中 `access_token=` 后的内容
4. 打开系统「通知设置」页面，粘贴 Token 并保存
5. 点击「发送测试消息」验证配置

### 定时任务

支持配置多个定时任务，每个任务包含：

| 配置项 | 说明 |
|--------|------|
| 任务名称 | 显示名称，如「早间排班通知」 |
| 触发时间 | 每天发送的时间点 HH:MM |
| 日期偏移 | 当天/明天/后天（预览和计算目标日期用） |
| 前缀 | 自定义开头语，如「早上好！☀️ 今日排班如下：」 |
| 后缀 | 自定义结束语，如「祝大家工作愉快！💪」 |
| 启用/停用 | 独立开关，不影响其他任务 |

### 消息模板

最终推送的消息由三部分组成：

> **前缀**（自定义开头语）
> 
> #### 排班通知 2026-05-25 周一
> 
> 上班人数：**26人**（含主管）
> 主管（4人）：赵月, 王鹏飞, 俞蕾, 胡玉婷
> 在线组（6人）：孙赟, 张颖, ...
> ...
> 
> **后缀**（自定义结束语）

### 调度机制

- 保存配置后自动创建 Windows 计划任务 `\排班系统\排班每日通知`
- 每分钟检查一次，匹配当前时间 HH:MM 的启用任务自动发送
- 所有任务停用后计划任务自动禁用
- 手动发送不受调度影响，可在页面上随时触发

### 命令行用法

```bash
# 手动执行指定任务
python send_daily_notice.py --task-id morning

# 指定日期执行
python send_daily_notice.py --task-id evening --date 2026-05-26

# 定时调度入口（由 Windows 计划任务调用）
python send_daily_notice.py --check-and-send
```

---

## 部署

### 方案 A：单机运行（内网/测试）

```bash
python app.py
# 访问 http://<服务器IP>:5000
# Windows 下自动使用 waitress（多线程），Linux 下需安装 gunicorn
```

### 方案 B：生产部署（Docker）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

```bash
docker build -t schedule-system .
docker run -d -p 5000:5000 -v ./data:/app schedule-system
```

---

## 注意事项

- SQLite 适合小团队使用，高并发场景建议切换为 MySQL/PostgreSQL
- 数据库文件 `schedule.db` 需定期备份
- 系统无登录鉴权，内网部署时建议搭配 nginx basic auth 或 VPN
- 班次颜色方案：A班(蓝)、B班(青)、C班(紫)、D班(靛)、E班(黄)、休息/放休(灰)、请假(橙)。T班/F班可在班次设置中自行添加，导入时支持对应代码。
- 团队颜色方案：在线组(绿)、热线组(蓝)、售后组(橙)、综合组(紫)、VIP组(粉)、质检组(黄)、支持组(青)

