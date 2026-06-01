"""
客服排班系统 - 后端服务
Flask + SQLite，单文件部署
启动: pip install flask openpyxl && python app.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages'))

import sqlite3, json
from datetime import datetime, date
from flask import Flask, request, jsonify, g, send_file
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import calendar

try:
    from chinese_calendar import is_workday
except ImportError:
    is_workday = None

app = Flask(__name__, static_folder=".", static_url_path="")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 开发阶段禁用静态文件缓存
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def count_working_days(year, month):
    """返回指定月份的中国法定工作日天数（考虑节假日和调休）"""
    days_in_month = calendar.monthrange(year, month)[1]
    if is_workday is None:
        # 降级方案：按周一至周五计算（不含中国节假日）
        return sum(1 for d in range(1, days_in_month + 1)
                   if date(year, month, d).weekday() < 5)
    return sum(1 for d in range(1, days_in_month + 1)
               if is_workday(date(year, month, d)))


# ==================== 日志管理 ====================

class _Tee:
    """同时写入文件和原始流"""
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self._streams:
            s.flush()


def _rotate_log(path):
    """启动时清除旧日志内容"""
    try:
        open(path, "w").close()
    except OSError:
        pass


def setup_logging():
    """将 stdout/stderr 重定向到 logs/ 子目录，同时保留控制台输出"""
    log_dir = os.path.join(BASE_DIR, "logs")
    out_dir = os.path.join(log_dir, "output")
    err_dir = os.path.join(log_dir, "error")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(err_dir, exist_ok=True)

    out_path = os.path.join(out_dir, "service_output.log")
    err_path = os.path.join(err_dir, "service_error.log")

    _rotate_log(out_path)
    _rotate_log(err_path)

    sys.stdout = _Tee(sys.__stdout__, open(out_path, "a", encoding="utf-8"))
    sys.stderr = _Tee(sys.__stderr__, open(err_path, "a", encoding="utf-8"))


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            team        TEXT NOT NULL,
            position    TEXT NOT NULL DEFAULT '客服',
            supervisor     TEXT DEFAULT '',
            dongfu_id      TEXT DEFAULT '',
            work_hour_system TEXT DEFAULT '',
            entry_date     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            updated_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS shifts (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            info        TEXT DEFAULT '',
            start_time  TEXT DEFAULT '',
            end_time    TEXT DEFAULT '',
            lunch_start TEXT DEFAULT '',
            lunch_end   TEXT DEFAULT '',
            dinner_start TEXT DEFAULT '',
            dinner_end  TEXT DEFAULT '',
            work_hours  REAL DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            updated_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS schedules (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_date  TEXT NOT NULL,
            employee_name  TEXT NOT NULL,
            shift_name     TEXT NOT NULL,
            created_at     TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(schedule_date, employee_name)
        );
        CREATE INDEX IF NOT EXISTS idx_schedules_date ON schedules(schedule_date);
        CREATE INDEX IF NOT EXISTS idx_schedules_emp  ON schedules(employee_name);

        CREATE TABLE IF NOT EXISTS raw_schedules (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_date  TEXT NOT NULL,
            employee_name  TEXT NOT NULL,
            shift_name     TEXT NOT NULL,
            created_at     TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(schedule_date, employee_name)
        );
        CREATE INDEX IF NOT EXISTS idx_raw_schedules_date ON raw_schedules(schedule_date);
        CREATE INDEX IF NOT EXISTS idx_raw_schedules_emp  ON raw_schedules(employee_name);

        CREATE TABLE IF NOT EXISTS daily_assignments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT NOT NULL,
            employee_name  TEXT NOT NULL,
            work_types     TEXT NOT NULL DEFAULT '[]',
            lunch_slot     TEXT DEFAULT '',
            dinner_slot    TEXT DEFAULT '',
            created_at     TEXT DEFAULT (datetime('now','localtime')),
            updated_at     TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(date, employee_name)
        );
        CREATE INDEX IF NOT EXISTS idx_assignments_date ON daily_assignments(date);

        CREATE TABLE IF NOT EXISTS leave_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            team           TEXT NOT NULL,
            leave_date     TEXT NOT NULL,
            dongfu_id      TEXT DEFAULT '',
            employee_name  TEXT NOT NULL,
            start_time     TEXT NOT NULL,
            end_time       TEXT NOT NULL,
            hours          REAL DEFAULT 0,
            remark         TEXT DEFAULT '',
            submitter      TEXT DEFAULT '',
            deduction      REAL DEFAULT 0,
            created_at     TEXT DEFAULT (datetime('now','localtime')),
            updated_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_leave_records_date ON leave_records(leave_date);
    """)
    # 兼容旧表：新增 deduction 列
    try:
        db.execute("ALTER TABLE leave_records ADD COLUMN deduction REAL DEFAULT 0")
    except:
        pass
    db.executescript("""
        CREATE TABLE IF NOT EXISTS swap_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            swap_type      TEXT NOT NULL,
            person_a       TEXT NOT NULL,
            team_a         TEXT DEFAULT '',
            date_a         TEXT NOT NULL,
            shift_a        TEXT DEFAULT '',
            person_b       TEXT NOT NULL,
            team_b         TEXT DEFAULT '',
            date_b         TEXT NOT NULL,
            shift_b        TEXT DEFAULT '',
            remark         TEXT DEFAULT '',
            operator       TEXT DEFAULT '',
            created_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_swap_records_date_a ON swap_records(date_a);
        CREATE INDEX IF NOT EXISTS idx_swap_records_date_b ON swap_records(date_b);
        CREATE INDEX IF NOT EXISTS idx_leave_records_team ON leave_records(team);
    """)
    db.commit()

    # 迁移：为已有数据库添加 dongfu_id 列
    try:
        db.execute("ALTER TABLE employees ADD COLUMN dongfu_id TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass

    # 迁移：为已有数据库添加 work_hour_system 列
    try:
        db.execute("ALTER TABLE employees ADD COLUMN work_hour_system TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass

    # 写入默认数据
    cur = db.execute("SELECT COUNT(*) FROM employees")
    if cur.fetchone()[0] == 0:
        db.executescript("""
            INSERT INTO employees(id, name, team, position, supervisor, entry_date) VALUES
                ('EMP001','张三','在线组','客服','陈敏','2024-03-15'),
                ('EMP002','李四','热线组','客服','陈敏','2024-06-01'),
                ('EMP003','王芳','售后组','客服','陈敏','2024-08-20'),
                ('EMP004','赵磊','在线组','客服','陈敏','2025-01-10'),
                ('EMP005','陈敏','主管',  '主管','',    '2023-05-08');
        """)
    cur = db.execute("SELECT COUNT(*) FROM shifts")
    if cur.fetchone()[0] == 0:
        db.executescript("""
            INSERT INTO shifts(id, name, info, start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end, work_hours) VALUES
                ('SHF001','A班','早1班',  '08:00','17:00','12:00','12:30','','',8.0),
                ('SHF002','B班','常规班','09:00','18:00','12:00','12:30','','',8.5),
                ('SHF003','C班','早2班',  '07:00','16:00','12:00','12:30','','',8.5),
                ('SHF004','D班','晚1班',  '14:00','23:00','','','18:00','18:30',8.5),
                ('SHF005','E班','通宵班','22:00','08:00','','','02:00','02:30',9.5);
        """)
    db.commit()
    db.close()


# 导入时自动初始化数据库（兼容所有启动方式）
init_db()


# ==================== 员工 API ====================

@app.route("/api/employees", methods=["GET"])
def api_employees_list():
    db = get_db()
    status = request.args.get("status", "").strip()
    if status in ("active", "inactive"):
        rows = db.execute("SELECT * FROM employees WHERE status=? ORDER BY id", (status,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM employees ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/employees", methods=["POST"])
def api_employees_create():
    data = request.json
    name = (data.get("name") or "").strip()
    team = (data.get("team") or "").strip()
    position = (data.get("position") or "").strip()
    supervisor = (data.get("supervisor") or "").strip()
    entry_date = (data.get("entryDate") or "").strip()
    dongfu_id = (data.get("dongfuId") or "").strip()
    work_hour_system = (data.get("workHourSystem") or "").strip()
    status = (data.get("status") or "active").strip()

    if not name:
        return jsonify({"error": "请输入员工姓名"}), 400
    if not team:
        return jsonify({"error": "请选择所属团队"}), 400
    if not position:
        return jsonify({"error": "请选择岗位"}), 400

    db = get_db()
    exist = db.execute("SELECT id FROM employees WHERE name=?", (name,)).fetchone()
    if exist:
        return jsonify({"error": f"员工\"{name}\"已存在"}), 400

    row = db.execute("SELECT MAX(CAST(SUBSTR(id,4) AS INTEGER)) FROM employees").fetchone()
    next_id = (row[0] or 0) + 1
    emp_id = f"EMP{next_id:03d}"

    db.execute(
        "INSERT INTO employees(id, name, team, position, supervisor, entry_date, dongfu_id, work_hour_system, status) VALUES(?,?,?,?,?,?,?,?,?)",
        (emp_id, name, team, position, supervisor, entry_date, dongfu_id, work_hour_system, status)
    )
    db.commit()
    row = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/employees/<emp_id>", methods=["PUT"])
def api_employees_update(emp_id):
    data = request.json
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        return jsonify({"error": "员工不存在"}), 404

    name = (data.get("name") or "").strip() or emp["name"]
    team = (data.get("team") or "").strip() or emp["team"]
    position = (data.get("position") or "").strip() or emp["position"]
    supervisor = data.get("supervisor") if "supervisor" in data else emp["supervisor"]
    if supervisor: supervisor = supervisor.strip()
    entry_date = data.get("entryDate") if "entryDate" in data else emp["entry_date"]
    if entry_date: entry_date = entry_date.strip()
    dongfu_id = data.get("dongfuId") if "dongfuId" in data else emp["dongfu_id"]
    if dongfu_id: dongfu_id = dongfu_id.strip()
    work_hour_system = data.get("workHourSystem") if "workHourSystem" in data else emp.get("work_hour_system", "")
    if work_hour_system: work_hour_system = work_hour_system.strip()
    else: work_hour_system = ""
    status = (data.get("status") or "").strip() or emp.get("status", "active")

    if not name:
        return jsonify({"error": "请输入员工姓名"}), 400

    exist = db.execute("SELECT id FROM employees WHERE name=? AND id!=?", (name, emp_id)).fetchone()
    if exist:
        return jsonify({"error": f"员工\"{name}\"已存在"}), 400

    old_name = emp["name"]
    db.execute(
        "UPDATE employees SET name=?, team=?, position=?, supervisor=?, entry_date=?, dongfu_id=?, work_hour_system=?, status=?, updated_at=datetime('now','localtime') WHERE id=?",
        (name, team, position, supervisor or "", entry_date or "", dongfu_id or "", work_hour_system, status, emp_id)
    )
    # 如果改了名字，同步更新上下级引用和排班记录
    if old_name != name:
        db.execute("UPDATE employees SET supervisor=? WHERE supervisor=?", (name, old_name))
        db.execute("UPDATE schedules SET employee_name=? WHERE employee_name=?", (name, old_name))
    db.commit()
    row = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/employees/import", methods=["POST"])
def api_employees_import():
    """Excel 批量导入员工"""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "请上传文件"}), 400

    from openpyxl import load_workbook
    try:
        wb = load_workbook(file, read_only=True)
    except Exception:
        return jsonify({"error": "无法解析该文件，请上传 .xlsx 格式的 Excel（不支持旧版 .xls 格式）"}), 400
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return jsonify({"error": "Excel至少包含两行数据（表头+数据）"}), 400

    header = [str(c or "").strip() for c in rows[0]]
    name_idx = next((i for i, h in enumerate(header) if "姓名" in h), -1)
    team_idx = next((i for i, h in enumerate(header) if "团队" in h), -1)
    pos_idx = next((i for i, h in enumerate(header) if "岗位" in h), -1)
    sup_idx = next((i for i, h in enumerate(header) if "上级" in h), -1)
    date_idx = next((i for i, h in enumerate(header) if "入职" in h or "日期" in h), -1)
    dongfu_idx = next((i for i, h in enumerate(header) if "东福" in h or "工号" in h), -1)
    whs_idx = next((i for i, h in enumerate(header) if "工时" in h or "工时制度" in h), -1)
    status_idx = next((i for i, h in enumerate(header) if "状态" in h), -1)

    db = get_db()
    success = 0
    errors = []
    for rn, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        try:
            name = str(row[name_idx] or "").strip()
            team = str(row[team_idx] or "").strip()
            position = str(row[pos_idx] or "").strip()
        except IndexError:
            continue
        if not name or not team or not position:
            if name:
                errors.append(f"第{rn}行: 信息不完整")
            continue

        supervisor = ""
        entry_date = ""
        dongfu_id = ""
        work_hour_system = ""
        status = "active"
        if sup_idx >= 0:
            try:
                supervisor = str(row[sup_idx] or "").strip()
            except IndexError:
                pass
        if date_idx >= 0:
            try:
                raw_date = str(row[date_idx] or "").strip()
                entry_date = _parse_date(raw_date) or raw_date
            except IndexError:
                pass
        if dongfu_idx >= 0:
            try:
                dongfu_id = str(row[dongfu_idx] or "").strip()
            except IndexError:
                pass
        if whs_idx >= 0:
            try:
                work_hour_system = str(row[whs_idx] or "").strip()
            except IndexError:
                pass
        if status_idx >= 0:
            try:
                raw_status = str(row[status_idx] or "").strip()
                if raw_status in ("失效", "inactive", "0", "false", "否"):
                    status = "inactive"
            except IndexError:
                pass

        exist = db.execute("SELECT id FROM employees WHERE name=?", (name,)).fetchone()
        if exist:
            errors.append(f"第{rn}行: 员工\"{name}\"已存在，跳过")
            continue

        num_row = db.execute("SELECT MAX(CAST(SUBSTR(id,4) AS INTEGER)) FROM employees").fetchone()
        next_id = (num_row[0] or 0) + 1
        emp_id = f"EMP{next_id:03d}"

        db.execute(
            "INSERT INTO employees(id, name, team, position, supervisor, entry_date, dongfu_id, work_hour_system, status) VALUES(?,?,?,?,?,?,?,?,?)",
            (emp_id, name, team, position, supervisor, entry_date, dongfu_id, work_hour_system, status)
        )
        success += 1

    db.commit()
    wb.close()
    return jsonify({"ok": True, "success": success, "errors": errors})


@app.route("/api/employees/template", methods=["GET"])
def api_employees_template():
    """下载员工导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "员工导入模板"
    ws.append(["姓名", "东福工号", "团队", "岗位", "工时制度", "上级", "入职日期", "状态"])
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 10

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True, download_name="员工导入模板.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/employees/<emp_id>", methods=["DELETE"])
def api_employees_delete(emp_id):
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        return jsonify({"error": "员工不存在"}), 404

    subordinates = db.execute("SELECT name FROM employees WHERE supervisor=?", (emp["name"],)).fetchall()
    if subordinates:
        names = "、".join(r["name"] for r in subordinates)
        return jsonify({"error": f"无法删除：{names} 的上级为 {emp['name']}，请先调整"}), 400

    db.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    db.commit()
    return jsonify({"ok": True})


# ==================== 班次 API ====================

@app.route("/api/shifts", methods=["GET"])
def api_shifts_list():
    db = get_db()
    rows = db.execute("SELECT * FROM shifts ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/shifts", methods=["POST"])
def api_shifts_create():
    data = request.json
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请输入班次名称"}), 400

    db = get_db()
    exist = db.execute("SELECT id FROM shifts WHERE name=?", (name,)).fetchone()
    if exist:
        return jsonify({"error": f"班次\"{name}\"已存在"}), 400

    row = db.execute("SELECT MAX(CAST(SUBSTR(id,4) AS INTEGER)) FROM shifts").fetchone()
    next_id = (row[0] or 0) + 1
    shift_id = f"SHF{next_id:03d}"

    info = (data.get("info") or "").strip()
    start_time = (data.get("startTime") or "").strip()
    end_time = (data.get("endTime") or "").strip()
    lunch_start = (data.get("lunchStart") or "").strip()
    lunch_end = (data.get("lunchEnd") or "").strip()
    dinner_start = (data.get("dinnerStart") or "").strip()
    dinner_end = (data.get("dinnerEnd") or "").strip()
    work_hours = _calc_work_hours(start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end)

    db.execute(
        "INSERT INTO shifts(id, name, info, start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end, work_hours) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (shift_id, name, info, start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end, work_hours)
    )
    db.commit()
    row = db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/shifts/<shift_id>", methods=["PUT"])
def api_shifts_update(shift_id):
    data = request.json
    db = get_db()
    shift = db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
    if not shift:
        return jsonify({"error": "班次不存在"}), 404

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请输入班次名称"}), 400

    exist = db.execute("SELECT id FROM shifts WHERE name=? AND id!=?", (name, shift_id)).fetchone()
    if exist:
        return jsonify({"error": f"班次\"{name}\"已存在"}), 400

    old_name = shift["name"]
    info = (data.get("info") or "").strip()
    start_time = (data.get("startTime") or "").strip()
    end_time = (data.get("endTime") or "").strip()
    lunch_start = (data.get("lunchStart") or "").strip()
    lunch_end = (data.get("lunchEnd") or "").strip()
    dinner_start = (data.get("dinnerStart") or "").strip()
    dinner_end = (data.get("dinnerEnd") or "").strip()
    work_hours = _calc_work_hours(start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end)

    db.execute(
        "UPDATE shifts SET name=?, info=?, start_time=?, end_time=?, lunch_start=?, lunch_end=?, dinner_start=?, dinner_end=?, work_hours=?, updated_at=datetime('now','localtime') WHERE id=?",
        (name, info, start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end, work_hours, shift_id)
    )
    # 如果改了名字，同步排班记录
    if old_name != name:
        db.execute("UPDATE schedules SET shift_name=? WHERE shift_name=?", (name, old_name))
    db.commit()
    row = db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/shifts/<shift_id>", methods=["DELETE"])
def api_shifts_delete(shift_id):
    db = get_db()
    shift = db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
    if not shift:
        return jsonify({"error": "班次不存在"}), 404
    db.execute("DELETE FROM shifts WHERE id=?", (shift_id,))
    db.commit()
    return jsonify({"ok": True})


# ==================== 排班 API ====================

@app.route("/api/schedules", methods=["GET"])
def api_schedules_list():
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    db = get_db()
    if start and end:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM schedules WHERE schedule_date>=? AND schedule_date<=? ORDER BY schedule_date, employee_name",
            (start, end)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM schedules ORDER BY schedule_date, employee_name"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/schedule/lookup", methods=["GET"])
def api_schedule_lookup():
    """查询某员工在某日期的班次信息"""
    employee = request.args.get("employee", "").strip()
    date = request.args.get("date", "").strip()
    if not employee or not date:
        return jsonify({"error": "缺少employee或date参数"}), 400
    db = get_db()
    row = db.execute(
        "SELECT s.shift_name, sh.start_time, sh.end_time FROM schedules s "
        "LEFT JOIN shifts sh ON sh.name = s.shift_name "
        "WHERE s.schedule_date = ? AND s.employee_name = ?",
        (date, employee)
    ).fetchone()
    if not row:
        return jsonify({"shift_name": None, "start_time": None, "end_time": None})
    return jsonify(dict(row))


@app.route("/api/schedules/batch", methods=["POST"])
def api_schedules_batch():
    """批量新增/更新排班: {entries: [{date, employee, shift}, ...]}"""
    data = request.json
    entries = data.get("entries") or []
    if not entries:
        return jsonify({"error": "无排班数据"}), 400

    db = get_db()
    count = 0
    for e in entries:
        d = (e.get("date") or "").strip()
        emp = (e.get("employee") or "").strip()
        shift = (e.get("shift") or "").strip()
        if not d or not emp:
            continue
        if not shift:
            shift = "休息"
        db.execute(
            "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name, created_at=datetime('now','localtime')",
            (d, emp, shift)
        )
        count += 1
    db.commit()
    return jsonify({"ok": True, "updated": count})


@app.route("/api/schedules/import", methods=["POST"])
def api_schedules_import():
    """Excel 导入排班"""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "请上传文件"}), 400

    from openpyxl import load_workbook
    try:
        wb = load_workbook(file)
    except Exception as e:
        return jsonify({"error": f"无法解析该文件：{e}"}), 400
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return jsonify({"error": "Excel至少包含两行数据"}), 400

    header = [str(c or "").lower() for c in rows[0]]
    date_idx = next((i for i, h in enumerate(header) if "日期" in h), -1)
    emp_idx = next((i for i, h in enumerate(header) if "员工" in h or "姓名" in h), -1)
    shift_idx = next((i for i, h in enumerate(header) if "班次" in h or "shift" in h), -1)

    if date_idx < 0 or emp_idx < 0 or shift_idx < 0:
        return jsonify({"error": "Excel需包含【日期,员工,班次】三列"}), 400

    db = get_db()
    count = 0
    failures = []
    for rn, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        try:
            d = str(row[date_idx] or "").strip()
            emp = str(row[emp_idx] or "").strip()
            shift = str(row[shift_idx] or "").strip()
        except IndexError:
            continue
        if not d or not emp:
            if emp or d:
                failures.append({"row": rn, "employee": emp or "(空)", "date": d or "(空)", "reason": "信息不完整"})
            continue
        if not shift:
            shift = "休息"
        date_str = _parse_date(d)
        if not date_str:
            failures.append({"row": rn, "employee": emp, "date": d, "reason": "日期格式无法识别"})
            continue
        db.execute(
            "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
            (date_str, emp, shift)
        )
        count += 1
    db.commit()
    wb.close()
    return jsonify({"ok": True, "updated": count, "failures": failures})


@app.route("/api/schedules/import-matrix", methods=["POST"])
def api_schedules_import_matrix():
    """Excel 矩阵格式导入排班
    格式：第一列为员工姓名，第一行为日期（从第二列开始），交叉单元格为班次代码
    A=A班, B=B班, C=C班, D=D班, E=E班, 假=请假, 空=休息
    """
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "请上传文件"}), 400

    from openpyxl import load_workbook
    try:
        wb = load_workbook(file)
    except Exception as e:
        return jsonify({"error": f"无法解析该文件：{e}"}), 400
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return jsonify({"error": "Excel至少包含表头和数据行"}), 400

    # 解析表头：第一列是"姓名"，其余列是日期
    raw_header = rows[0]
    header = [str(c or "").strip() for c in raw_header]
    dates = []
    for i in range(1, len(raw_header)):
        # 优先用原始值解析（可能是 datetime 对象），字符串版本作为备选
        d = _parse_date(raw_header[i]) or _parse_date(header[i])
        if d:
            dates.append((i, d))

    if not dates:
        sample = "、".join(header[1:6])
        return jsonify({"error": f"未识别到日期列，表头前几列为：{sample}。请使用日期格式（如2026-02-01、2/1、1日）"}), 400

    # 加载班次表，构建名称→名称的映射
    db = get_db()
    db_shifts = db.execute("SELECT name FROM shifts").fetchall()
    db_shift_names = [s["name"] for s in db_shifts]

    # 代码→班次名称 精确映射（优先）
    code_to_shift = {
        "A": "A班", "a": "A班",
        "B": "B班", "b": "B班",
        "C": "C班", "c": "C班",
        "T": "T班", "t": "T班",
        "E": "E班", "e": "E班",
        "F": "F班", "f": "F班",
        "休": "休息", "休假": "休息", "休息": "休息", "调休": "放休", "放休": "放休",
        "假": "请假", "请假": "请假",
    }

    def resolve_shift(raw_val):
        """将单元格值解析为班次名称。返回 (shift_name, None) 成功，或 (None, reason) 失败"""
        val = raw_val.strip()
        if not val:
            return "休息", None

        # 1. 精确映射
        if val in code_to_shift:
            target = code_to_shift[val]
            if target in db_shift_names:
                return target, None
            else:
                return None, f"映射目标班次\"{target}\"在班次表中不存在"

        # 2. 直接匹配班次名称
        if val in db_shift_names:
            return val, None

        # 3. 模糊匹配（双向子串）
        for sn in db_shift_names:
            if val in sn or sn in val:
                return sn, None

        return None, f"班次\"{val}\"无法识别"

    count = 0
    failures = []
    for rn, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        emp_name = str(row[0] or "").strip()
        if not emp_name:
            continue

        emp = db.execute("SELECT name FROM employees WHERE name=?", (emp_name,)).fetchone()
        if not emp:
            failures.append({"row": rn, "employee": emp_name, "date": "", "reason": "员工不存在"})
            continue

        for col_idx, date_str in dates:
            try:
                raw = str(row[col_idx] or "")
            except IndexError:
                raw = ""
            if not raw.strip():
                raw = ""  # 空值统一处理为休息

            shift, err = resolve_shift(raw)
            if err:
                failures.append({"row": rn, "employee": emp_name, "date": date_str, "reason": err})
                continue

            db.execute(
                "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
                (date_str, emp_name, shift)
            )
            count += 1

    db.commit()
    wb.close()
    return jsonify({"ok": True, "updated": count, "failures": failures})


@app.route("/api/schedules/export", methods=["GET"])
def api_schedules_export():
    """Excel 导出排班"""
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    db = get_db()

    # 查询员工
    employees = db.execute("SELECT name, team FROM employees ORDER BY id").fetchall()

    # 查询排班
    if start and end:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM schedules WHERE schedule_date>=? AND schedule_date<=? ORDER BY schedule_date",
            (start, end)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM schedules ORDER BY schedule_date"
        ).fetchall()

    # 构建 date -> emp -> shift 映射
    schedule_map = {}
    date_set = set()
    for r in rows:
        schedule_map[(r["schedule_date"], r["employee_name"])] = r["shift_name"]
        date_set.add(r["schedule_date"])

    wb = Workbook()
    ws = wb.active
    ws.title = "排班表"

    # 表头
    ws.cell(row=1, column=1, value="日期")
    ws.cell(row=1, column=2, value="员工")
    ws.cell(row=1, column=3, value="所属团队")
    ws.cell(row=1, column=4, value="班次")

    sorted_dates = sorted(date_set)
    row_idx = 2
    for d in sorted_dates:
        for emp in employees:
            shift = schedule_map.get((d, emp["name"]), "未排班")
            ws.cell(row=row_idx, column=1, value=d)
            ws.cell(row=row_idx, column=2, value=emp["name"])
            ws.cell(row=row_idx, column=3, value=emp["team"])
            ws.cell(row=row_idx, column=4, value=shift)
            row_idx += 1

    # 列宽
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True, download_name="排班数据.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==================== 原始排班 API ====================

def _sync_raw_to_schedule(db, date_str, emp_name, shift_name):
    """单向同步：原始排班 → 排班表"""
    db.execute(
        "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name, created_at=datetime('now','localtime')",
        (date_str, emp_name, shift_name)
    )


@app.route("/api/raw-schedules", methods=["GET"])
def api_raw_schedules_list():
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    db = get_db()
    if start and end:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM raw_schedules WHERE schedule_date>=? AND schedule_date<=? ORDER BY schedule_date, employee_name",
            (start, end)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM raw_schedules ORDER BY schedule_date, employee_name"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/raw-schedules/batch", methods=["POST"])
def api_raw_schedules_batch():
    """批量新增/更新原始排班: {entries: [{date, employee, shift}, ...]}，并单向同步到排班表"""
    data = request.json
    entries = data.get("entries") or []
    if not entries:
        return jsonify({"error": "无排班数据"}), 400

    db = get_db()
    count = 0
    for e in entries:
        d = (e.get("date") or "").strip()
        emp = (e.get("employee") or "").strip()
        shift = (e.get("shift") or "").strip()
        if not d or not emp:
            continue
        if not shift:
            shift = "休息"
        db.execute(
            "INSERT INTO raw_schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name, created_at=datetime('now','localtime')",
            (d, emp, shift)
        )
        _sync_raw_to_schedule(db, d, emp, shift)
        count += 1
    db.commit()
    return jsonify({"ok": True, "updated": count})


@app.route("/api/raw-schedules/import", methods=["POST"])
def api_raw_schedules_import():
    """Excel 导入原始排班（列表格式），单向同步到排班表"""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "请上传文件"}), 400

    from openpyxl import load_workbook
    try:
        wb = load_workbook(file)
    except Exception as e:
        return jsonify({"error": f"无法解析该文件：{e}"}), 400
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return jsonify({"error": "Excel至少包含两行数据"}), 400

    header = [str(c or "").lower() for c in rows[0]]
    date_idx = next((i for i, h in enumerate(header) if "日期" in h), -1)
    emp_idx = next((i for i, h in enumerate(header) if "员工" in h or "姓名" in h), -1)
    shift_idx = next((i for i, h in enumerate(header) if "班次" in h or "shift" in h), -1)

    if date_idx < 0 or emp_idx < 0 or shift_idx < 0:
        return jsonify({"error": "Excel需包含【日期,员工,班次】三列"}), 400

    db = get_db()
    count = 0
    failures = []
    for rn, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        try:
            d = str(row[date_idx] or "").strip()
            emp = str(row[emp_idx] or "").strip()
            shift = str(row[shift_idx] or "").strip()
        except IndexError:
            continue
        if not d or not emp:
            if emp or d:
                failures.append({"row": rn, "employee": emp or "(空)", "date": d or "(空)", "reason": "信息不完整"})
            continue
        if not shift:
            shift = "休息"
        date_str = _parse_date(d)
        if not date_str:
            failures.append({"row": rn, "employee": emp, "date": d, "reason": "日期格式无法识别"})
            continue
        db.execute(
            "INSERT INTO raw_schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
            (date_str, emp, shift)
        )
        _sync_raw_to_schedule(db, date_str, emp, shift)
        count += 1
    db.commit()
    wb.close()
    return jsonify({"ok": True, "updated": count, "failures": failures})


@app.route("/api/raw-schedules/import-matrix", methods=["POST"])
def api_raw_schedules_import_matrix():
    """Excel 矩阵格式导入原始排班，单向同步到排班表"""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "请上传文件"}), 400

    from openpyxl import load_workbook
    try:
        wb = load_workbook(file)
    except Exception as e:
        return jsonify({"error": f"无法解析该文件：{e}"}), 400
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return jsonify({"error": "Excel至少包含表头和数据行"}), 400

    raw_header = rows[0]
    header = [str(c or "").strip() for c in raw_header]
    dates = []
    for i in range(1, len(raw_header)):
        d = _parse_date(raw_header[i]) or _parse_date(header[i])
        if d:
            dates.append((i, d))

    if not dates:
        sample = "、".join(header[1:6])
        return jsonify({"error": f"未识别到日期列，表头前几列为：{sample}。请使用日期格式（如2026-02-01、2/1、1日）"}), 400

    db = get_db()
    db_shifts = db.execute("SELECT name FROM shifts").fetchall()
    db_shift_names = [s["name"] for s in db_shifts]

    code_to_shift = {
        "A": "A班", "a": "A班",
        "B": "B班", "b": "B班",
        "C": "C班", "c": "C班",
        "T": "T班", "t": "T班",
        "E": "E班", "e": "E班",
        "F": "F班", "f": "F班",
        "休": "休息", "休假": "休息", "休息": "休息", "调休": "放休", "放休": "放休",
        "假": "请假", "请假": "请假",
    }

    def resolve_shift(raw_val):
        val = raw_val.strip()
        if not val:
            return "休息", None
        if val in code_to_shift:
            target = code_to_shift[val]
            if target in db_shift_names:
                return target, None
            else:
                return None, f"映射目标班次\"{target}\"在班次表中不存在"
        if val in db_shift_names:
            return val, None
        for sn in db_shift_names:
            if val in sn or sn in val:
                return sn, None
        return None, f"班次\"{val}\"无法识别"

    count = 0
    failures = []
    for rn, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        emp_name = str(row[0] or "").strip()
        if not emp_name:
            continue

        emp = db.execute("SELECT name FROM employees WHERE name=?", (emp_name,)).fetchone()
        if not emp:
            failures.append({"row": rn, "employee": emp_name, "date": "", "reason": "员工不存在"})
            continue

        for col_idx, date_str in dates:
            try:
                raw = str(row[col_idx] or "")
            except IndexError:
                raw = ""
            if not raw.strip():
                raw = ""

            shift, err = resolve_shift(raw)
            if err:
                failures.append({"row": rn, "employee": emp_name, "date": date_str, "reason": err})
                continue

            db.execute(
                "INSERT INTO raw_schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
                (date_str, emp_name, shift)
            )
            _sync_raw_to_schedule(db, date_str, emp_name, shift)
            count += 1

    db.commit()
    wb.close()
    return jsonify({"ok": True, "updated": count, "failures": failures})


@app.route("/api/raw-schedules/export", methods=["GET"])
def api_raw_schedules_export():
    """Excel 导出原始排班"""
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    db = get_db()

    employees = db.execute("SELECT name, team FROM employees ORDER BY id").fetchall()

    if start and end:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM raw_schedules WHERE schedule_date>=? AND schedule_date<=? ORDER BY schedule_date",
            (start, end)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT schedule_date, employee_name, shift_name FROM raw_schedules ORDER BY schedule_date"
        ).fetchall()

    schedule_map = {}
    date_set = set()
    for r in rows:
        schedule_map[(r["schedule_date"], r["employee_name"])] = r["shift_name"]
        date_set.add(r["schedule_date"])

    wb = Workbook()
    ws = wb.active
    ws.title = "原始排班表"

    ws.cell(row=1, column=1, value="日期")
    ws.cell(row=1, column=2, value="员工")
    ws.cell(row=1, column=3, value="所属团队")
    ws.cell(row=1, column=4, value="班次")

    sorted_dates = sorted(date_set)
    row_idx = 2
    for d in sorted_dates:
        for emp in employees:
            shift = schedule_map.get((d, emp["name"]), "未排班")
            ws.cell(row=row_idx, column=1, value=d)
            ws.cell(row=row_idx, column=2, value=emp["name"])
            ws.cell(row=row_idx, column=3, value=emp["team"])
            ws.cell(row=row_idx, column=4, value=shift)
            row_idx += 1

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True, download_name="原始排班数据.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==================== 工作安排 API ====================

@app.route("/api/assignments", methods=["GET"])
def api_assignments_list():
    """查询某日工作安排"""
    date_str = request.args.get("date", "").strip()
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    rows = db.execute(
        "SELECT * FROM daily_assignments WHERE date=? ORDER BY employee_name",
        (date_str,)
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["work_types"] = json.loads(d["work_types"])
        results.append(d)
    return jsonify(results)


@app.route("/api/assignments", methods=["POST"])
def api_assignments_save():
    """批量保存工作安排: {date, assignments: [{employee_name, work_types, lunch_slot, dinner_slot}, ...]}"""
    data = request.json
    date_str = (data.get("date") or "").strip()
    entries = data.get("assignments") or []
    if not date_str:
        return jsonify({"error": "日期不能为空"}), 400

    db = get_db()
    count = 0
    for e in entries:
        emp = (e.get("employee_name") or "").strip()
        work_types = json.dumps(e.get("work_types") or [], ensure_ascii=False)
        lunch_slot = (e.get("lunch_slot") or "").strip()
        dinner_slot = (e.get("dinner_slot") or "").strip()
        if not emp:
            continue
        db.execute(
            "INSERT INTO daily_assignments(date, employee_name, work_types, lunch_slot, dinner_slot) "
            "VALUES(?,?,?,?,?) ON CONFLICT(date, employee_name) DO UPDATE SET "
            "work_types=excluded.work_types, lunch_slot=excluded.lunch_slot, dinner_slot=excluded.dinner_slot, "
            "updated_at=datetime('now','localtime')",
            (date_str, emp, work_types, lunch_slot, dinner_slot)
        )
        count += 1
    db.commit()
    return jsonify({"ok": True, "updated": count})


# ==================== 加班换班 API ====================

def _calc_leave_hours(start_time, end_time):
    """计算加班时长（小时），支持跨天"""
    sm = _time_to_minutes(start_time)
    em = _time_to_minutes(end_time)
    if sm is None or em is None:
        return 0
    if em <= sm:
        em += 24 * 60
    return round((em - sm) / 6) / 10


@app.route("/api/leave-records", methods=["GET"])
def api_leave_records_list():
    team = request.args.get("team", "").strip()
    month = request.args.get("month", "").strip()
    db = get_db()

    sql = "SELECT * FROM leave_records WHERE 1=1"
    params = []
    if team:
        sql += " AND team = ?"
        params.append(team)
    if month:
        sql += " AND leave_date LIKE ?"
        params.append(month + "%")
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/leave-records", methods=["POST"])
def api_leave_records_create():
    data = request.json
    team = (data.get("team") or "").strip()
    leave_date = (data.get("leaveDate") or "").strip()
    employee_name = (data.get("employeeName") or "").strip()
    start_time = (data.get("startTime") or "").strip()
    end_time = (data.get("endTime") or "").strip()
    remark = (data.get("remark") or "").strip()
    submitter = (data.get("submitter") or "").strip()
    deduction = data.get("deduction", 0)
    if deduction is None:
        deduction = 0
    deduction = float(deduction)

    if not team:
        return jsonify({"error": "请选择所属团队"}), 400
    if not leave_date:
        return jsonify({"error": "请选择加班日期"}), 400
    if not employee_name:
        return jsonify({"error": "请选择员工"}), 400
    if not start_time:
        return jsonify({"error": "请选择加班开始时间"}), 400
    if not end_time:
        return jsonify({"error": "请选择加班结束时间"}), 400
    if len(remark) > 200:
        return jsonify({"error": "备注不能超过200字符"}), 400
    if deduction < 0 or deduction > 8:
        return jsonify({"error": "扣除时长范围0~8小时"}), 400

    db = get_db()
    emp = db.execute("SELECT dongfu_id FROM employees WHERE name=?", (employee_name,)).fetchone()
    dongfu_id = emp["dongfu_id"] if emp else ""

    hours = max(0, round((_calc_leave_hours(start_time, end_time) - deduction) * 10) / 10)

    db.execute(
        "INSERT INTO leave_records(team, leave_date, dongfu_id, employee_name, start_time, end_time, hours, remark, submitter, deduction) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (team, leave_date, dongfu_id, employee_name, start_time, end_time, hours, remark, submitter, deduction)
    )
    db.commit()
    row = db.execute("SELECT * FROM leave_records WHERE id=last_insert_rowid()").fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/leave-records/<int:record_id>", methods=["PUT"])
def api_leave_records_update(record_id):
    data = request.json
    db = get_db()
    record = db.execute("SELECT * FROM leave_records WHERE id=?", (record_id,)).fetchone()
    if not record:
        return jsonify({"error": "记录不存在"}), 404

    team = (data.get("team") or "").strip()
    leave_date = (data.get("leaveDate") or "").strip()
    employee_name = (data.get("employeeName") or "").strip()
    start_time = (data.get("startTime") or "").strip()
    end_time = (data.get("endTime") or "").strip()
    remark = (data.get("remark") or "").strip()
    submitter = (data.get("submitter") or "").strip()
    deduction = data.get("deduction", 0)
    if deduction is None:
        deduction = 0
    deduction = float(deduction)

    if not team or not leave_date or not employee_name or not start_time or not end_time:
        return jsonify({"error": "必填字段不能为空"}), 400
    if len(remark) > 200:
        return jsonify({"error": "备注不能超过200字符"}), 400
    if deduction < 0 or deduction > 8:
        return jsonify({"error": "扣除时长范围0~8小时"}), 400

    emp = db.execute("SELECT dongfu_id FROM employees WHERE name=?", (employee_name,)).fetchone()
    dongfu_id = emp["dongfu_id"] if emp else ""

    hours = max(0, round((_calc_leave_hours(start_time, end_time) - deduction) * 10) / 10)

    db.execute(
        "UPDATE leave_records SET team=?, leave_date=?, dongfu_id=?, employee_name=?, start_time=?, end_time=?, hours=?, remark=?, submitter=?, deduction=?, updated_at=datetime('now','localtime') WHERE id=?",
        (team, leave_date, dongfu_id, employee_name, start_time, end_time, hours, remark, submitter, deduction, record_id)
    )
    db.commit()
    row = db.execute("SELECT * FROM leave_records WHERE id=?", (record_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/leave-records/<int:record_id>", methods=["DELETE"])
def api_leave_records_delete(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM leave_records WHERE id=?", (record_id,)).fetchone()
    if not record:
        return jsonify({"error": "记录不存在"}), 404
    db.execute("DELETE FROM leave_records WHERE id=?", (record_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/leave-records/export", methods=["GET"])
def api_leave_records_export():
    team = request.args.get("team", "").strip()
    month = request.args.get("month", "").strip()
    employees_str = request.args.get("employees", "").strip()
    db = get_db()

    sql = "SELECT * FROM leave_records WHERE 1=1"
    params = []
    if team:
        sql += " AND team = ?"
        params.append(team)
    if month:
        sql += " AND leave_date LIKE ?"
        params.append(month + "%")
    if employees_str:
        names = [n.strip() for n in employees_str.split(",") if n.strip()]
        if names:
            placeholders = ",".join("?" for _ in names)
            sql += f" AND employee_name IN ({placeholders})"
            params.extend(names)
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "调休记录"
    ws.append(["清单ID", "所属团队", "加班日期", "东福工号", "员工", "开始时间", "结束时间", "加班时长(h)", "备注", "提交人", "最后修改时间"])

    for r in rows:
        leave_date = r["leave_date"]
        start_time = r["start_time"]
        end_time = r["end_time"]

        # 拼接日期+时间；跨天场景 end_date 加一天
        export_start = f"{leave_date} {start_time}"
        if _time_to_minutes(end_time) is not None and _time_to_minutes(start_time) is not None:
            if _time_to_minutes(end_time) <= _time_to_minutes(start_time):
                from datetime import datetime as dt, timedelta
                next_day = dt.strptime(leave_date, "%Y-%m-%d") + timedelta(days=1)
                export_end = f"{next_day.strftime('%Y-%m-%d')} {end_time}"
            else:
                export_end = f"{leave_date} {end_time}"
        else:
            export_end = f"{leave_date} {end_time}"

        ws.append([
            r["id"], r["team"], r["leave_date"], r["dongfu_id"], r["employee_name"],
            export_start, export_end, r["hours"], r["remark"], r["submitter"],
            r["updated_at"] or r["created_at"]
        ])

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 20
    ws.column_dimensions["G"].width = 20
    ws.column_dimensions["H"].width = 14
    ws.column_dimensions["I"].width = 24
    ws.column_dimensions["J"].width = 12
    ws.column_dimensions["K"].width = 20

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True, download_name="调休记录导出.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==================== 换班/换休 API ====================

@app.route("/api/swap-records", methods=["GET"])
def api_swap_records_list():
    team = request.args.get("team", "").strip()
    month = request.args.get("month", "").strip()
    db = get_db()
    sql = "SELECT * FROM swap_records WHERE 1=1"
    params = []
    if team:
        sql += " AND (team_a = ? OR team_b = ?)"
        params.extend([team, team])
    if month:
        sql += " AND (date_a LIKE ? OR date_b LIKE ?)"
        params.extend([month + "%", month + "%"])
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/swap-records", methods=["POST"])
def api_swap_records_create():
    data = request.json
    swap_type = (data.get("swapType") or "").strip()
    person_a = (data.get("personA") or "").strip()
    date_a = (data.get("dateA") or "").strip()
    person_b = (data.get("personB") or "").strip()
    date_b = (data.get("dateB") or "").strip()
    remark = (data.get("remark") or "").strip()
    operator = (data.get("operator") or "").strip()

    if swap_type not in ("shift_swap", "rest_swap"):
        return jsonify({"error": "无效的换班类型"}), 400
    if not person_a or not date_a:
        return jsonify({"error": "请选择换班人和日期"}), 400
    if not person_b or not date_b:
        return jsonify({"error": "请选择交换人和日期"}), 400
    if not remark:
        return jsonify({"error": "请填写备注"}), 400
    if len(remark) > 200:
        return jsonify({"error": "备注不能超过200字符"}), 400
    if not operator:
        return jsonify({"error": "请选择操作人"}), 400

    db = get_db()

    # 查询两个日期上两人的排班
    row_a1 = db.execute(
        "SELECT shift_name FROM schedules WHERE schedule_date=? AND employee_name=?",
        (date_a, person_a)
    ).fetchone()
    row_a2 = db.execute(
        "SELECT shift_name FROM schedules WHERE schedule_date=? AND employee_name=?",
        (date_b, person_a)
    ).fetchone()
    row_b1 = db.execute(
        "SELECT shift_name FROM schedules WHERE schedule_date=? AND employee_name=?",
        (date_a, person_b)
    ).fetchone()
    row_b2 = db.execute(
        "SELECT shift_name FROM schedules WHERE schedule_date=? AND employee_name=?",
        (date_b, person_b)
    ).fetchone()

    if not row_a1:
        return jsonify({"error": f"{person_a} 在 {date_a} 无排班记录"}), 400
    if not row_b2:
        return jsonify({"error": f"{person_b} 在 {date_b} 无排班记录"}), 400

    # 查询团队
    emp_a = db.execute("SELECT team FROM employees WHERE name=?", (person_a,)).fetchone()
    team_a = emp_a["team"] if emp_a else ""

    def _upsert_shift(date, emp, shift):
        db.execute(
            "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) "
            "ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
            (date, emp, shift)
        )

    if person_a == person_b:
        # 自换：同一人两个日期互换
        if not row_a2:
            return jsonify({"error": f"{person_a} 在 {date_b} 无排班记录"}), 400
        a1_old = row_a1["shift_name"]
        a2_old = row_a2["shift_name"]
        team_b = team_a

        _upsert_shift(date_a, person_a, a2_old)
        _upsert_shift(date_b, person_a, a1_old)

        cur = db.execute(
            "INSERT INTO swap_records(swap_type, person_a, team_a, date_a, shift_a, person_b, team_b, date_b, shift_b, remark, operator) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (swap_type, person_a, team_a, date_a, a1_old, person_a, team_a, date_b, a2_old, remark, operator)
        )
        swap_id = cur.lastrowid

        if swap_type == "rest_swap":
            _create_rest_overtime(db, person_a, team_a, date_a, a1_old, a2_old, person_a, operator, remark)
            _create_rest_overtime(db, person_a, team_a, date_b, a2_old, a1_old, person_a, operator, remark)
    else:
        # 互换算两人在两个日期上的班次
        a1_old = row_a1["shift_name"]
        a2_old = row_a2["shift_name"] if row_a2 else "休息"
        b1_old = row_b1["shift_name"] if row_b1 else "休息"
        b2_old = row_b2["shift_name"]

        emp_b = db.execute("SELECT team FROM employees WHERE name=?", (person_b,)).fetchone()
        team_b = emp_b["team"] if emp_b else ""

        _upsert_shift(date_a, person_a, b1_old)
        _upsert_shift(date_a, person_b, a1_old)
        _upsert_shift(date_b, person_a, b2_old)
        _upsert_shift(date_b, person_b, a2_old)

        cur = db.execute(
            "INSERT INTO swap_records(swap_type, person_a, team_a, date_a, shift_a, person_b, team_b, date_b, shift_b, remark, operator) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (swap_type, person_a, team_a, date_a, a1_old, person_b, team_b, date_b, b2_old, remark, operator)
        )
        swap_id = cur.lastrowid

        if swap_type == "rest_swap":
            _create_rest_overtime(db, person_a, team_a, date_a, a1_old, b1_old, person_b, operator)
            _create_rest_overtime(db, person_a, team_a, date_b, a2_old, b2_old, person_b, operator)
            _create_rest_overtime(db, person_b, team_b, date_a, b1_old, a1_old, person_a, operator)
            _create_rest_overtime(db, person_b, team_b, date_b, b2_old, a2_old, person_a, operator)

    db.commit()
    row = db.execute("SELECT * FROM swap_records WHERE id=?", (swap_id,)).fetchone()
    return jsonify(dict(row)), 201


def _create_rest_overtime(db, employee, team, date, old_shift, new_shift, other_person, operator, remark=None):
    """如果员工原班次是休息、新班次是工作，创建一条加班记录"""
    if old_shift not in ("休息", "放休", "请假"):
        return
    if new_shift in ("休息", "放休", "请假", ""):
        return

    shift = db.execute(
        "SELECT start_time, end_time, work_hours FROM shifts WHERE name=?",
        (new_shift,)
    ).fetchone()
    if not shift or not shift["start_time"] or not shift["end_time"]:
        return

    start_time = shift["start_time"]
    end_time = shift["end_time"]
    hours = shift["work_hours"] if shift["work_hours"] else _calc_leave_hours(start_time, end_time)

    emp = db.execute("SELECT dongfu_id FROM employees WHERE name=?", (employee,)).fetchone()
    dongfu_id = emp["dongfu_id"] if emp else ""

    overtime_remark = remark if remark else f"与{other_person}换班"

    db.execute(
        "INSERT INTO leave_records(team, leave_date, dongfu_id, employee_name, start_time, end_time, hours, remark, submitter) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (team, date, dongfu_id, employee, start_time, end_time, hours, overtime_remark, operator)
    )


# ==================== 辅助函数 ====================

def _time_to_minutes(t):
    if not t:
        return None
    parts = t.split(":")
    if len(parts) != 2:
        return None
    return int(parts[0]) * 60 + int(parts[1])


def _calc_work_hours(start_time, end_time, lunch_start, lunch_end, dinner_start, dinner_end):
    sm = _time_to_minutes(start_time)
    em = _time_to_minutes(end_time)
    if sm is None or em is None:
        return 0
    if em <= sm:
        em += 24 * 60
    work_min = em - sm
    if lunch_start and lunch_end:
        ls = _time_to_minutes(lunch_start)
        le = _time_to_minutes(lunch_end)
        if ls is not None and le is not None:
            if le <= ls:
                le += 24 * 60
            work_min -= (le - ls)
    if dinner_start and dinner_end:
        ds = _time_to_minutes(dinner_start)
        de = _time_to_minutes(dinner_end)
        if ds is not None and de is not None:
            if de <= ds:
                de += 24 * 60
            work_min -= (de - ds)
    return round(work_min / 6) / 10


def _parse_date(val):
    """尝试解析各种日期格式为 YYYY-MM-DD"""
    import re
    # 处理 datetime 对象（openpyxl 可能返回）
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    val = str(val).strip()
    # YYYY-MM-DD（可能带时间部分，如 "2026-05-01 00:00:00"）
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s|T|$)", val)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # YYYY/MM/DD
    if re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", val):
        return val.replace("/", "-")
    # YYYY.M.DD 或 YYYY.M.D
    m = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", val)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # YYYY年M月D日
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", val)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", val)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    # M/D（月/日，如 2/1、5/01）
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", val)
    if m:
        now = datetime.now()
        return f"{now.year}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    # M月D日（如 5月1日、12月15日）
    m = re.match(r"^(\d{1,2})月(\d{1,2})日$", val)
    if m:
        now = datetime.now()
        return f"{now.year}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    # D日（如 1日、15日）
    m = re.match(r"^(\d{1,2})日$", val)
    if m:
        now = datetime.now()
        return f"{now.year}-{now.month:02d}-{m.group(1).zfill(2)}"
    # 纯数字 1-31（日数）
    try:
        n = int(val)
        if 1 <= n <= 31:
            now = datetime.now()
            return f"{now.year}-{now.month:02d}-{n:02d}"
    except (ValueError, TypeError):
        pass
    # Excel 序列号
    try:
        n = float(val)
        if n > 40000:
            from datetime import timedelta
            d = datetime(1899, 12, 30) + timedelta(days=n)
            return d.strftime("%Y-%m-%d")
    except ValueError:
        pass
    return ""


# ==================== 工作安排统计 API ====================

ASSIGNMENT_WORK_TYPES = ["反向工单", "自主售后", "售后单", "紧急", "本地生活"]


@app.route("/api/assignment-stats", methods=["GET"])
def api_assignment_stats():
    """按自然月统计工作安排，按团队过滤"""
    year = request.args.get("year", "")
    month = request.args.get("month", "")
    team_str = request.args.get("team", "售后组").strip()

    now = datetime.now()
    if not year:
        year = str(now.year)
    if not month:
        month = str(now.month)

    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    start_date = f"{year_int}-{month_int:02d}-01"
    end_date = f"{year_int}-{month_int:02d}-{last_day}"

    db = get_db()

    # 支持逗号分隔多团队
    teams = [t.strip() for t in team_str.split(",") if t.strip()]

    # 获取指定团队的员工
    if teams:
        placeholders = ",".join("?" for _ in teams)
        employees = db.execute(
            f"SELECT name FROM employees WHERE team IN ({placeholders}) AND status='active' ORDER BY name",
            teams
        ).fetchall()
    else:
        employees = db.execute(
            "SELECT name FROM employees WHERE status='active' ORDER BY name"
        ).fetchall()
    emp_names = {e["name"] for e in employees}

    # 查询当月所有工作安排
    rows = db.execute(
        "SELECT employee_name, work_types FROM daily_assignments WHERE date>=? AND date<=? ORDER BY date",
        (start_date, end_date)
    ).fetchall()

    # 统计：员工 -> 工作类型 -> 次数
    stats = {}
    for e in employees:
        stats[e["name"]] = {w: 0 for w in ASSIGNMENT_WORK_TYPES}

    for r in rows:
        emp = r["employee_name"]
        if emp not in emp_names:
            continue
        work_types = json.loads(r["work_types"])
        for w in work_types:
            if w in stats[emp]:
                stats[emp][w] += 1

    results = []
    for e in employees:
        entry = {"name": e["name"]}
        entry.update(stats[e["name"]])
        results.append(entry)

    # 所有可选团队
    all_teams = db.execute("SELECT DISTINCT team FROM employees WHERE status='active' ORDER BY team").fetchall()
    team_list = [r["team"] for r in all_teams]

    return jsonify({"rows": results, "teams": team_list, "month": f"{year_int}年{month_int}月"})


@app.route("/api/assignment-stats/export", methods=["GET"])
def api_assignment_stats_export():
    """导出工作安排统计Excel"""
    year = request.args.get("year", "")
    month = request.args.get("month", "")
    team_str = request.args.get("team", "售后组").strip()

    now = datetime.now()
    if not year:
        year = str(now.year)
    if not month:
        month = str(now.month)

    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    start_date = f"{year_int}-{month_int:02d}-01"
    end_date = f"{year_int}-{month_int:02d}-{last_day}"

    db = get_db()

    teams = [t.strip() for t in team_str.split(",") if t.strip()]
    if teams:
        placeholders = ",".join("?" for _ in teams)
        employees = db.execute(
            f"SELECT name FROM employees WHERE team IN ({placeholders}) AND status='active' ORDER BY name",
            teams
        ).fetchall()
    else:
        employees = db.execute(
            "SELECT name FROM employees WHERE status='active' ORDER BY name"
        ).fetchall()
    emp_names = {e["name"] for e in employees}

    rows = db.execute(
        "SELECT employee_name, work_types FROM daily_assignments WHERE date>=? AND date<=? ORDER BY date",
        (start_date, end_date)
    ).fetchall()

    stats = {}
    for e in employees:
        stats[e["name"]] = {w: 0 for w in ASSIGNMENT_WORK_TYPES}

    for r in rows:
        emp = r["employee_name"]
        if emp not in emp_names:
            continue
        work_types = json.loads(r["work_types"])
        for w in work_types:
            if w in stats[emp]:
                stats[emp][w] += 1

    wb = Workbook()
    ws = wb.active
    ws.title = f"{year_int}年{month_int}月工作安排统计"
    ws.append(["员工姓名"] + ASSIGNMENT_WORK_TYPES)

    for e in employees:
        row = [e["name"]] + [stats[e["name"]][w] for w in ASSIGNMENT_WORK_TYPES]
        ws.append(row)

    ws.column_dimensions["A"].width = 12
    for i in range(len(ASSIGNMENT_WORK_TYPES)):
        ws.column_dimensions[get_column_letter(i + 2)].width = 14

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True,
                     download_name=f"工作安排统计_{year_int}年{month_int}月.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==================== 月度时长统计 API ====================

@app.route("/api/monthly-hours-stats", methods=["GET"])
def api_monthly_hours_stats():
    year = request.args.get("year", "")
    month = request.args.get("month", "")
    work_system = request.args.get("work_system", "").strip()
    teams_str = request.args.get("teams", "").strip()

    now = datetime.now()
    if not year:
        year = str(now.year)
    if not month:
        month = str(now.month)

    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    start_date = f"{year_int}-{month_int:02d}-01"
    end_date = f"{year_int}-{month_int:02d}-{last_day}"

    db = get_db()

    query = "SELECT id, name, team, dongfu_id, work_hour_system FROM employees WHERE status='active'"
    params = []
    if work_system:
        query += " AND work_hour_system = ?"
        params.append(work_system)
    teams = [t.strip() for t in teams_str.split(",") if t.strip()]
    if teams:
        placeholders = ",".join("?" for _ in teams)
        query += f" AND team IN ({placeholders})"
        params.extend(teams)
    query += " ORDER BY id"
    employees = db.execute(query, params).fetchall()

    shifts = db.execute("SELECT id, name, work_hours FROM shifts").fetchall()
    shift_map = {s["name"]: {"id": s["id"], "work_hours": s["work_hours"]} for s in shifts}

    schedules = db.execute(
        "SELECT employee_name, shift_name FROM schedules WHERE schedule_date >= ? AND schedule_date <= ?",
        (start_date, end_date)
    ).fetchall()

    emp_shifts = {}
    for s in schedules:
        emp = s["employee_name"]
        shift = s["shift_name"]
        if emp not in emp_shifts:
            emp_shifts[emp] = {}
        emp_shifts[emp][shift] = emp_shifts[emp].get(shift, 0) + 1

    results = []
    for emp in employees:
        name = emp["name"]
        shifts_count = emp_shifts.get(name, {})

        total_hours = 0.0
        total_days = 0
        for shift_name, days in shifts_count.items():
            info = shift_map.get(shift_name)
            if info and "SHF001" <= info["id"] <= "SHF006":
                total_hours += info["work_hours"] * days
                total_days += days

        work_system = (emp["work_hour_system"] or "").strip()
        if work_system == "综合计算工时制":
            system_hours = 167.0
        else:
            system_hours = 8.0 * count_working_days(year_int, month_int)

        diff = round(total_hours - system_hours, 1)

        results.append({
            "dongfu_id": emp["dongfu_id"] or "",
            "name": name,
            "team": emp["team"] or "",
            "work_system": work_system,
            "scheduled_hours": round(total_hours, 1),
            "system_hours": round(system_hours, 1),
            "diff": diff
        })

    # 返回所有可选团队（用于筛选器）
    all_teams = db.execute("SELECT DISTINCT team FROM employees WHERE status='active' ORDER BY team").fetchall()
    team_list = [r["team"] for r in all_teams]

    return jsonify({"rows": results, "teams": team_list})


@app.route("/api/monthly-hours-stats/export", methods=["GET"])
def api_monthly_hours_stats_export():
    year = request.args.get("year", "")
    month = request.args.get("month", "")
    work_system = request.args.get("work_system", "").strip()
    teams_str = request.args.get("teams", "").strip()

    now = datetime.now()
    if not year:
        year = str(now.year)
    if not month:
        month = str(now.month)

    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    start_date = f"{year_int}-{month_int:02d}-01"
    end_date = f"{year_int}-{month_int:02d}-{last_day}"

    db = get_db()

    query = "SELECT id, name, team, dongfu_id, work_hour_system FROM employees WHERE status='active'"
    params = []
    if work_system:
        query += " AND work_hour_system = ?"
        params.append(work_system)
    teams = [t.strip() for t in teams_str.split(",") if t.strip()]
    if teams:
        placeholders = ",".join("?" for _ in teams)
        query += f" AND team IN ({placeholders})"
        params.extend(teams)
    query += " ORDER BY id"
    employees = db.execute(query, params).fetchall()

    shifts = db.execute("SELECT id, name, work_hours FROM shifts").fetchall()
    shift_map = {s["name"]: {"id": s["id"], "work_hours": s["work_hours"]} for s in shifts}

    schedules = db.execute(
        "SELECT employee_name, shift_name FROM schedules WHERE schedule_date >= ? AND schedule_date <= ?",
        (start_date, end_date)
    ).fetchall()

    emp_shifts = {}
    for s in schedules:
        emp = s["employee_name"]
        shift = s["shift_name"]
        if emp not in emp_shifts:
            emp_shifts[emp] = {}
        emp_shifts[emp][shift] = emp_shifts[emp].get(shift, 0) + 1

    TEAM_ORDER = ["在线组","热线组","售后组","综合组","VIP组","质检组","支持组"]

    results = []
    for emp in employees:
        name = emp["name"]
        shifts_count = emp_shifts.get(name, {})

        total_hours = 0.0
        total_days = 0
        for shift_name, days in shifts_count.items():
            info = shift_map.get(shift_name)
            if info and "SHF001" <= info["id"] <= "SHF006":
                total_hours += info["work_hours"] * days
                total_days += days

        ws = (emp["work_hour_system"] or "").strip()
        if ws == "综合计算工时制":
            system_hours = 167.0
        else:
            system_hours = 8.0 * count_working_days(year_int, month_int)

        diff = round(total_hours - system_hours, 1)

        results.append({
            "team": emp["team"] or "",
            "dongfu_id": emp["dongfu_id"] or "",
            "name": name,
            "scheduled_hours": round(total_hours, 1),
            "system_hours": round(system_hours, 1),
            "diff": diff
        })

    # 排序
    results.sort(key=lambda r: (TEAM_ORDER.index(r["team"]) if r["team"] in TEAM_ORDER else 999, r["name"]))

    # 生成 Excel
    wb = Workbook()
    ws_sheet = wb.active
    ws_sheet.title = f"{year_int}年{month_int}月时长统计"
    ws_sheet.append(["所属团队", "东福工号", "员工姓名", "原始排班时长(h)", "工时制度时长(h)", "差额(h)"])

    # 团队列颜色
    team_colors = {
        "在线组": "c6efce", "热线组": "b4d6fd", "售后组": "fcd5a7",
        "综合组": "e4c6ec", "VIP组": "f7c6d7", "质检组": "fce9a2", "支持组": "b9e4e0"
    }
    from openpyxl.styles import PatternFill, Font

    for row in results:
        ws_sheet.append([row["team"], row["dongfu_id"], row["name"],
                         row["scheduled_hours"], row["system_hours"], row["diff"]])
        r = ws_sheet.max_row
        color = team_colors.get(row["team"])
        if color:
            ws_sheet.cell(row=r, column=1).fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        # 差额颜色
        diff_cell = ws_sheet.cell(row=r, column=6)
        if row["diff"] > 0:
            diff_cell.font = Font(color="10b981", bold=True)
        elif row["diff"] < 0:
            diff_cell.font = Font(color="ef4444", bold=True)

    ws_sheet.column_dimensions["A"].width = 12
    ws_sheet.column_dimensions["B"].width = 14
    ws_sheet.column_dimensions["C"].width = 12
    ws_sheet.column_dimensions["D"].width = 18
    ws_sheet.column_dimensions["E"].width = 18
    ws_sheet.column_dimensions["F"].width = 12

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()
    return send_file(tmp.name, as_attachment=True,
                     download_name=f"月度时长统计_{year_int}年{month_int}月.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==================== 数据库管理 ====================

@app.route("/api/db/download")
def api_db_download():
    """下载数据库文件"""
    return send_file(DATABASE, as_attachment=True, download_name="schedule.db")


@app.route("/api/db/stats")
def api_db_stats():
    """数据库统计信息"""
    db = get_db()
    emp_count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    shift_count = db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
    sch_count = db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    date_range = db.execute("SELECT MIN(schedule_date), MAX(schedule_date) FROM schedules").fetchone()
    return jsonify({
        "employees": emp_count,
        "shifts": shift_count,
        "schedules": sch_count,
        "dateFrom": date_range[0] or "",
        "dateTo": date_range[1] or ""
    })


# ==================== 通知设置 API ====================

NOTIFY_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_config.json")
TEAM_ORDER = ["在线组", "热线组", "售后组", "综合组", "VIP组", "质检组", "支持组"]

DEFAULT_NOTIFY_CONFIG = {
    "webhook_token": "",
    "tasks": []
}


def load_notify_config():
    if os.path.exists(NOTIFY_CONFIG_FILE):
        try:
            with open(NOTIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "webhook_token" not in cfg:
                    cfg["webhook_token"] = ""
                if "tasks" not in cfg:
                    cfg["tasks"] = []
                return cfg
        except Exception:
            pass
    return {"webhook_token": "", "tasks": []}


def save_notify_config(cfg):
    with open(NOTIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def sync_all_scheduled_tasks(cfg):
    """同步系统定时任务：Windows 用计划任务，Linux 用 cron"""
    tasks = cfg.get("tasks", [])
    has_enabled = any(t.get("enabled", True) for t in tasks)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "send_daily_notice.py")
    python_exe = sys.executable

    import subprocess
    if sys.platform == "win32":
        _sync_windows_task(has_enabled, python_exe, script_path)
    else:
        _sync_linux_cron(has_enabled, python_exe, script_path)


def _sync_windows_task(has_enabled, python_exe, script_path):
    import subprocess
    pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe
    task_name = r"\排班系统\排班每日通知"
    if has_enabled:
        # 始终用 /create /f 覆盖，确保调度周期和命令行是最新的
        subprocess.run(
            ["schtasks", "/create", "/tn", task_name, "/sc", "minute", "/mo", "30", "/st", "00:00",
             "/tr", f'"{pythonw_exe}" "{script_path}" --check-and-send',
             "/f"],
            capture_output=True, text=True
        )
    else:
        # 没有启用任务时，如果任务存在则禁用它
        check = subprocess.run(
            ["schtasks", "/query", "/tn", task_name],
            capture_output=True, text=True
        )
        if check.returncode == 0:
            subprocess.run(
                ["schtasks", "/change", "/tn", task_name, "/disable"],
                capture_output=True, text=True
            )


def _sync_linux_cron(has_enabled, python_exe, script_path):
    import subprocess
    marker = "# 排班通知定时任务"
    cron_line = f"*/30 * * * * {python_exe} {script_path} --check-and-send {marker}"

    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = proc.stdout if proc.returncode == 0 else ""

    lines = [l for l in current.splitlines() if marker not in l]
    if has_enabled:
        lines.append(cron_line)

    new_crontab = "\n".join(lines) + "\n" if lines else ""
    subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)


def get_all_task_status():
    """获取计划任务状态"""
    if sys.platform == "win32":
        return _get_windows_task_status()
    else:
        return _get_linux_cron_status()


def _get_windows_task_status():
    import subprocess
    task_name = r"\排班系统\排班每日通知"
    result = {"exists": False, "enabled": False, "next_run": ""}
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "csv", "/v"],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if len(lines) >= 2:
                fields = lines[1].replace('"', '').split(",")
                if len(fields) >= 16:
                    result = {
                        "exists": True,
                        "enabled": fields[5] != "Disabled",
                        "next_run": fields[15]
                    }
    except Exception:
        pass
    return result


def _get_linux_cron_status():
    import subprocess
    marker = "# 排班通知定时任务"
    result = {"exists": False, "enabled": False, "next_run": "每30分钟"}
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode == 0 and marker in r.stdout:
            result["exists"] = True
            result["enabled"] = True
    except Exception:
        pass
    return result


def build_schedule_message(schedules, target_date, prefix="", suffix=""):
    """构建排班消息（可复用的核心逻辑）"""
    weekday = ["一", "二", "三", "四", "五", "六", "日"][date.fromisoformat(target_date).weekday()]
    lines = [f"#### 排班通知 {target_date} 周{weekday}"]

    if not schedules:
        lines.append("\n暂无排班数据")
    else:
        supervisors = [s for s in schedules if s["position"] == "主管"]
        agents = [s for s in schedules if s["position"] != "主管"]
        team_map = {}
        for a in agents:
            t = a["team"]
            if t not in team_map:
                team_map[t] = []
            team_map[t].append(a["name"])

        lines.append(f"\n上班人数：**{len(schedules)}人**（含主管）")
        if supervisors:
            lines.append(f"主管（{len(supervisors)}人）：{', '.join(s['name'] for s in supervisors)}")
        for t in TEAM_ORDER:
            if t not in team_map:
                continue
            emps = team_map[t]
            lines.append(f"{t}（{len(emps)}人）：{', '.join(emps)}")

    body = "\n\n".join(lines)
    parts = []
    if prefix.strip():
        parts.append(prefix.strip())
    parts.append(body)
    if suffix.strip():
        parts.append(suffix.strip())
    return "\n\n".join(parts)


def query_schedule_data(target_date):
    """查询指定日期的排班数据"""
    db = get_db()
    cur = db.execute("""
        SELECT e.name, e.team, e.position, s.shift_name
        FROM schedules s JOIN employees e ON s.employee_name = e.name
        WHERE s.schedule_date = ? AND e.status = 'active'
          AND s.shift_name NOT IN ('休息','放休','请假')
        ORDER BY e.team, s.shift_name, e.name
    """, (target_date,))
    return [dict(r) for r in cur.fetchall()]


# ── 配置读写 ──

@app.route("/api/notify/config", methods=["GET"])
def api_notify_config():
    cfg = load_notify_config()
    task_status = get_all_task_status()
    # 为每个任务附加计划任务状态
    for task in cfg.get("tasks", []):
        task["_scheduler"] = task_status
    return jsonify(cfg)


@app.route("/api/notify/config", methods=["POST"])
def api_notify_config_save():
    data = request.json or {}
    cfg = load_notify_config()
    if "webhook_token" in data:
        cfg["webhook_token"] = data["webhook_token"].strip()
    if "tasks" in data:
        cfg["tasks"] = data["tasks"]
    save_notify_config(cfg)
    sync_all_scheduled_tasks(cfg)
    task_status = get_all_task_status()
    for task in cfg.get("tasks", []):
        task["_scheduler"] = task_status
    return jsonify({"ok": True, "config": cfg})


# ── 测试 Webhook ──

@app.route("/api/notify/test", methods=["POST"])
def api_notify_test():
    cfg = load_notify_config()
    token = cfg.get("webhook_token", "")
    if not token:
        return jsonify({"error": "请先配置 Webhook Token"}), 400

    import urllib.request
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": " 排班 系统测试消息，Webhook配置成功！"}
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://oapi.dingtalk.com/robot/send?access_token={token}",
        data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("errcode") == 0:
            return jsonify({"ok": True, "message": "测试消息已发送"})
        return jsonify({"error": result.get("errmsg", "发送失败")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── 发送通知 ──

@app.route("/api/notify/send", methods=["POST"])
def api_notify_send():
    data = request.json or {}
    cfg = load_notify_config()
    token = cfg.get("webhook_token", "")
    if not token:
        return jsonify({"error": "请先配置 Webhook Token"}), 400

    task_id = data.get("task_id", "")
    task = next((t for t in cfg.get("tasks", []) if t["id"] == task_id), None)

    # 确定目标日期
    if data.get("date"):
        target_date = data["date"]
    elif task:
        from datetime import timedelta
        offset = task.get("date_offset", 0)
        d = date.today() + timedelta(days=offset)
        target_date = d.isoformat()
    else:
        target_date = date.today().isoformat()

    # 确定前后缀
    prefix = data.get("prefix", task.get("prefix", "") if task else "")
    suffix = data.get("suffix", task.get("suffix", "") if task else "")
    task_name = task.get("name", "") if task else ""

    schedules = query_schedule_data(target_date)
    msg = build_schedule_message(schedules, target_date, prefix=prefix, suffix=suffix)
    title = f"{task_name} {target_date}".strip() if task_name else f"排班通知 {target_date}"

    import urllib.request
    payload = json.dumps({"msgtype": "markdown", "markdown": {"title": title, "text": msg}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://oapi.dingtalk.com/robot/send?access_token={token}",
        data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("errcode") == 0:
            return jsonify({"ok": True, "message": f"{target_date} 排班通知已发送"})
        return jsonify({"error": result.get("errmsg", "发送失败")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── 消息预览 ──

@app.route("/api/notify/preview", methods=["GET"])
def api_notify_preview():
    target_date = request.args.get("date", date.today().isoformat())
    prefix = request.args.get("prefix", "")
    suffix = request.args.get("suffix", "")

    schedules = query_schedule_data(target_date)
    text = build_schedule_message(schedules, target_date, prefix=prefix, suffix=suffix)
    return jsonify({"text": text})


# ── 任务 CRUD ──

@app.route("/api/notify/task", methods=["POST"])
def api_notify_task_add():
    data = request.json or {}
    cfg = load_notify_config()
    task = {
        "id": data.get("id", "").strip(),
        "name": data.get("name", "").strip(),
        "time": data.get("time", "08:00"),
        "enabled": data.get("enabled", True),
        "date_offset": int(data.get("date_offset", 0)),
        "prefix": data.get("prefix", ""),
        "suffix": data.get("suffix", ""),
        "template": "schedule"
    }
    if not task["id"]:
        return jsonify({"error": "任务ID不能为空"}), 400
    # 检查重复
    if any(t["id"] == task["id"] for t in cfg.get("tasks", [])):
        return jsonify({"error": "任务ID已存在"}), 400
    cfg.setdefault("tasks", []).append(task)
    save_notify_config(cfg)
    sync_all_scheduled_tasks(cfg)
    return jsonify({"ok": True, "task": task})


@app.route("/api/notify/task/<task_id>", methods=["PUT"])
def api_notify_task_update(task_id):
    data = request.json or {}
    cfg = load_notify_config()
    tasks = cfg.get("tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["id"] == task_id), None)
    if idx is None:
        return jsonify({"error": "任务不存在"}), 404
    task = tasks[idx]
    if "name" in data:
        task["name"] = data["name"].strip()
    if "time" in data:
        task["time"] = data["time"]
    if "enabled" in data:
        task["enabled"] = bool(data["enabled"])
    if "date_offset" in data:
        task["date_offset"] = int(data["date_offset"])
    if "prefix" in data:
        task["prefix"] = data["prefix"]
    if "suffix" in data:
        task["suffix"] = data["suffix"]
    save_notify_config(cfg)
    sync_all_scheduled_tasks(cfg)
    return jsonify({"ok": True, "task": task})


@app.route("/api/notify/task/<task_id>", methods=["DELETE"])
def api_notify_task_delete(task_id):
    cfg = load_notify_config()
    tasks = cfg.get("tasks", [])
    cfg["tasks"] = [t for t in tasks if t["id"] != task_id]
    if len(cfg["tasks"]) == len(tasks):
        return jsonify({"error": "任务不存在"}), 404
    save_notify_config(cfg)
    sync_all_scheduled_tasks(cfg)
    return jsonify({"ok": True})


# ==================== 静态文件 ====================

@app.route("/")
def index():
    return app.send_static_file("排班表.html")


# ==================== 启动 ====================

if __name__ == "__main__":
    setup_logging()
    init_db()
    print("=" * 50)
    print("  客服排班系统后端已启动")
    print("  打开浏览器访问: http://127.0.0.1:5000")
    print("=" * 50)
    try:
        from waitress import serve
        print("  使用 waitress 生产服务器")
        serve(app, host="0.0.0.0", port=5000, threads=4)
    except ImportError:
        print("  waitress 未安装，使用开发服务器")
        print("  建议执行: pip install waitress")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
