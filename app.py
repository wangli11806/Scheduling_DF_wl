"""
客服排班系统 - 后端服务
Flask + SQLite，单文件部署
启动: pip install flask openpyxl && python app.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages'))

import sqlite3
from datetime import datetime, date
from flask import Flask, request, jsonify, g, send_file
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

app = Flask(__name__, static_folder=".", static_url_path="")
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.db")


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
            supervisor  TEXT DEFAULT '',
            entry_date  TEXT NOT NULL,
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
    """)
    db.commit()

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

    if not name:
        return jsonify({"error": "请输入员工姓名"}), 400
    if not team:
        return jsonify({"error": "请选择所属团队"}), 400
    if not position:
        return jsonify({"error": "请选择岗位"}), 400
    if not entry_date:
        return jsonify({"error": "请选择入职时间"}), 400

    db = get_db()
    exist = db.execute("SELECT id FROM employees WHERE name=?", (name,)).fetchone()
    if exist:
        return jsonify({"error": f"员工\"{name}\"已存在"}), 400

    # ID 自增
    row = db.execute("SELECT MAX(CAST(SUBSTR(id,4) AS INTEGER)) FROM employees").fetchone()
    next_id = (row[0] or 0) + 1
    emp_id = f"EMP{next_id:03d}"

    db.execute(
        "INSERT INTO employees(id, name, team, position, supervisor, entry_date) VALUES(?,?,?,?,?,?)",
        (emp_id, name, team, position, supervisor, entry_date)
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

    name = (data.get("name") or "").strip()
    team = (data.get("team") or "").strip()
    position = (data.get("position") or "").strip()
    supervisor = (data.get("supervisor") or "").strip()
    entry_date = (data.get("entryDate") or "").strip()

    if not name:
        return jsonify({"error": "请输入员工姓名"}), 400

    exist = db.execute("SELECT id FROM employees WHERE name=? AND id!=?", (name, emp_id)).fetchone()
    if exist:
        return jsonify({"error": f"员工\"{name}\"已存在"}), 400

    old_name = emp["name"]
    db.execute(
        "UPDATE employees SET name=?, team=?, position=?, supervisor=?, entry_date=?, updated_at=datetime('now','localtime') WHERE id=?",
        (name, team, position, supervisor, entry_date, emp_id)
    )
    # 如果改了名字，同步更新上下级引用和排班记录
    if old_name != name:
        db.execute("UPDATE employees SET supervisor=? WHERE supervisor=?", (name, old_name))
        db.execute("UPDATE schedules SET employee_name=? WHERE employee_name=?", (name, old_name))
    db.commit()
    row = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    return jsonify(dict(row))


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
    wb = load_workbook(file, read_only=True)
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
    for row in rows[1:]:
        if not row:
            continue
        try:
            d = str(row[date_idx]).strip()
            emp = str(row[emp_idx]).strip()
            shift = str(row[shift_idx]).strip()
        except IndexError:
            continue
        if not d or not emp or not shift:
            continue
        # 尝试解析日期
        date_str = _parse_date(d)
        if not date_str:
            continue
        db.execute(
            "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
            (date_str, emp, shift)
        )
        count += 1
    db.commit()
    wb.close()
    return jsonify({"ok": True, "updated": count})


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
    val = val.strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", val):
        return val
    # YYYY/MM/DD
    if re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", val):
        return val.replace("/", "-")
    # MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", val)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
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


# ==================== 静态文件 ====================

@app.route("/")
def index():
    return app.send_static_file("排班表.html")


# ==================== 启动 ====================

if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  客服排班系统后端已启动")
    print("  打开浏览器访问: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
