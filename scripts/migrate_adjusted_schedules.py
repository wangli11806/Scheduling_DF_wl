# -*- coding: utf-8 -*-
"""一次性迁移：把 schedules 从「原始班次」改为「调整后班次」。

- 休假(leave)：全天 → 休假；按小时 → 原班次工时-休假小时<=0 → 休假，否则不变
- 换班/换休：按 swap_records + raw_schedules 重放，互换 schedules
- 加班：不改（历史全按「按小时」，班次仍休息）

运行前会自动备份 schedule.db 到 数据备份/。
"""
import sqlite3
import shutil
import datetime
import os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schedule.db")
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "数据备份")


def _upsert(db, date, emp, shift):
    db.execute(
        "INSERT INTO schedules(schedule_date, employee_name, shift_name) VALUES(?,?,?) "
        "ON CONFLICT(schedule_date, employee_name) DO UPDATE SET shift_name=excluded.shift_name",
        (date, emp, shift)
    )


def _raw_shift(db, date, emp):
    row = db.execute(
        "SELECT shift_name FROM raw_schedules WHERE schedule_date=? AND employee_name=?",
        (date, emp)
    ).fetchone()
    return (row[0] if row else "休息") or "休息"


def _work_hours(db, shift):
    row = db.execute("SELECT work_hours FROM shifts WHERE name=?", (shift,)).fetchone()
    return (row[0] if row else 0) or 0


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup = os.path.join(BACKUP_DIR, f"schedule_migrate_{ts}.db")
    shutil.copy(DB, backup)
    print(f"已备份: {backup}")

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    # 1. 休假 backfill
    leave_rows = db.execute("SELECT * FROM leave_records WHERE type='leave'").fetchall()
    leave_changed = 0
    for r in leave_rows:
        date, emp = r["leave_date"], r["employee_name"]
        raw_shift = _raw_shift(db, date, emp)
        if r["start_time"]:
            # 按小时：原班次工时 - 休假小时 <= 0 → 休假
            if _work_hours(db, raw_shift) - (r["hours"] or 0) <= 0:
                _upsert(db, date, emp, "休假")
                leave_changed += 1
        else:
            # 全天 → 休假
            _upsert(db, date, emp, "休假")
            leave_changed += 1
    print(f"休假 backfill: {leave_changed} 条")

    # 2. 换班/换休 backfill
    swaps = db.execute("SELECT * FROM swap_records").fetchall()
    swap_changed = 0
    for s in swaps:
        pa, da, sa = s["person_a"], s["date_a"], s["shift_a"]
        pb, db2, sb = s["person_b"], s["date_b"], s["shift_b"]
        if pa == pb:
            # 自换：date_a ↔ date_b
            _upsert(db, da, pa, sb)
            _upsert(db, db2, pa, sa)
        else:
            a2 = _raw_shift(db, db2, pa)  # A 在 date_b 的原始班次
            b1 = _raw_shift(db, da, pb)   # B 在 date_a 的原始班次
            _upsert(db, da, pa, b1)   # A 在 date_a → B 的原班次
            _upsert(db, db2, pa, sb)  # A 在 date_b → B 的 date_b 班次
            _upsert(db, da, pb, sa)   # B 在 date_a → A 的 date_a 班次
            _upsert(db, db2, pb, a2)  # B 在 date_b → A 的原班次
        swap_changed += 1
    print(f"换班 backfill: {swap_changed} 条")

    # 3. 清理遗留旧班次（请假/放休 → 休假）
    sched_clean = db.execute(
        "UPDATE schedules SET shift_name='休假' WHERE shift_name IN ('请假','放休')"
    ).rowcount
    raw_clean = db.execute(
        "UPDATE raw_schedules SET shift_name='休假' WHERE shift_name IN ('请假','放休')"
    ).rowcount
    print(f"清理遗留班次: schedules={sched_clean}, raw_schedules={raw_clean}")

    db.commit()
    db.close()
    print("迁移完成")


if __name__ == "__main__":
    main()
