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

首次启动自动创建 `schedule.db` 并写入 5 名默认员工和 5 个默认班次。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML/CSS/JS（三个单页面） |
| 后端 | Python Flask |
| 数据库 | SQLite（单文件，零配置） |
| Excel | openpyxl（导入导出） |

---

## 项目文件

```
排班系统/
├── app.py              # Flask 后端（所有 API）
├── requirements.txt    # Python 依赖
├── schedule.db         # SQLite 数据库（自动生成）
├── 排班表.html         # 排班表页面（查看/编辑/导入导出排班）
├── 员工管理.html       # 员工管理页面（CRUD）
├── 班次设置.html       # 班次设置页面（CRUD）
└── Readme.md           # 本文件
```

---

## 数据库设计

### employees（员工表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(10) PK | EMP001 |
| name | VARCHAR(50) UNIQUE | 员工姓名 |
| team | VARCHAR(20) | 在线组/热线组/售后组/主管/综合组 |
| position | VARCHAR(10) | 客服/主管 |
| supervisor | VARCHAR(50) | 上级姓名 |
| entry_date | TEXT | 入职时间 YYYY-MM-DD |

### shifts（班次表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(10) PK | SHF001 |
| name | VARCHAR(20) UNIQUE | A班/B班/... |
| info | VARCHAR(50) | 早1班/常规班/... |
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
| employee_name | VARCHAR(50) | 员工姓名 |
| shift_name | VARCHAR(20) | 班次名称 |
| UNIQUE(schedule_date, employee_name) | | 每人每天只能有一个排班 |

---

## API 文档

### 员工

```
GET    /api/employees          列表
POST   /api/employees          新增  {name, team, position, supervisor, entryDate}
PUT    /api/employees/<id>     编辑  {name, team, position, supervisor, entryDate}
DELETE /api/employees/<id>     删除（有下级时拒绝）
```

### 班次

```
GET    /api/shifts             列表
POST   /api/shifts             新增  {name, info, startTime, endTime, lunchStart, lunchEnd, dinnerStart, dinnerEnd}
PUT    /api/shifts/<id>        编辑  （同上）
DELETE /api/shifts/<id>        删除（同步更新排班记录中的班次名）
```

### 排班

```
GET    /api/schedules?start=&end=      查询
POST   /api/schedules/batch            批量新增/更新  {entries: [{date, employee, shift}, ...]}
POST   /api/schedules/import            Excel 导入（multipart form, field: file）
GET    /api/schedules/export            Excel 导出（?start=&end=）
```

---

## 部署到服务器

### 方案 A：单机运行（内网/测试）

```bash
python app.py
# 访问 http://<服务器IP>:5000
```

### 方案 B：生产部署（gunicorn + nginx）

```bash
# 安装
pip install gunicorn

# 启动（4 个 worker）
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# nginx 反向代理配置
# location / {
#     proxy_pass http://127.0.0.1:5000;
#     proxy_set_header Host $host;
#     proxy_set_header X-Real-IP $remote_addr;
# }
```

### 方案 C：Docker

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

- SQLite 适合小团队（<100 人）使用，高并发场景建议切换为 MySQL/PostgreSQL
- 数据库文件 `schedule.db` 需定期备份
- 系统无登录鉴权，内网部署时建议搭配 nginx basic auth 或 VPN
