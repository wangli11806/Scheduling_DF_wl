import os, json, sqlite3
os.chdir('/opt/schedule')

db = sqlite3.connect('schedule.db')

# Simulate frontend logic
# 1. Get schedules for 2026-07-08
schedules = db.execute("SELECT employee_name, shift_name FROM schedules WHERE schedule_date='2026-07-08'").fetchall()
schedule_map = {s[0]: s[1] for s in schedules}

# 2. Get all leave_records
leave_records = db.execute("SELECT * FROM leave_records").fetchall()
cols = [d[0] for d in db.execute("SELECT * FROM leave_records LIMIT 1").description]

# 3. Get shifts
shifts = db.execute("SELECT name, work_hours FROM shifts").fetchall()
shift_hours = {s[0]: s[1] or 0 for s in shifts}

# Build maps
rest_map = {}
overtime_map = {}
leave_set = set()

for r in leave_records:
    d = dict(zip(cols, r))
    key = d['leave_date'] + '|' + d['employee_name']
    rt = d['type'] or 'overtime'
    if rt == 'leave':
        leave_set.add(key)
    elif rt in ('rest', '换休'):
        rest_map[key] = rest_map.get(key, 0) + (d['hours'] or 0)
    elif rt in ('overtime', '换班'):
        overtime_map[key] = overtime_map.get(key, 0) + (d['hours'] or 0)

# Check 杨沛堃
emp_name = db.execute("SELECT name FROM employees WHERE id='EMP030'").fetchone()[0]
print(f'Employee: {emp_name}')
shift_name = schedule_map.get(emp_name, 'MISSING')
print(f'Schedule shift: {shift_name}')
print(f'leave_set check: {"2026-07-08|"+emp_name in leave_set}')
print(f'overtime_map: {overtime_map.get("2026-07-08|"+emp_name, 0)}')
print(f'rest_map: {rest_map.get("2026-07-08|"+emp_name, 0)}')

# Simulate isEffWorking
key = '2026-07-08|' + emp_name
if key in leave_set:
    working = False
else:
    sh = shift_hours.get(shift_name, 0)
    oh = overtime_map.get(key, 0)
    wh = sh + oh
    if wh <= 0:
        working = False
    else:
        rh = rest_map.get(key, 0)
        working = (wh - rh) > 0

print(f'Computed working: {working}')
print(f'Details: sh={shift_hours.get(shift_name, 0)}, oh={overtime_map.get(key, 0)}, wh={sh + overtime_map.get(key, 0)}, rh={rest_map.get(key, 0)}')

db.close()
