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

app = Flask(__name__, static_folder=".", static_url_path="")
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
