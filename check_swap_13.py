import sqlite3, os
os.chdir('/opt/schedule')
db = sqlite3.connect('/opt/schedule/schedule.db')

# Get swap record 13
r = db.execute('SELECT * FROM swap_records WHERE id=13').fetchone()
cols = [d[0] for d in db.execute('SELECT * FROM swap_records WHERE id=13').description]
print('swap_records id=13:')
for i, c in enumerate(cols):
    print(f'  {c}={repr(r[i])}')

print()

# Check leave_records id=79 and 80 with hex
for rid in [79, 80]:
    r = db.execute('SELECT id, type, hex(type) as hex_type, leave_date, employee_name, hex(employee_name) as hex_emp, hours FROM leave_records WHERE id=?', [rid]).fetchone()
    if r:
        print(f'id={r[0]}, type={repr(r[1])}, type_hex={r[2]}, date={r[3]}, emp={repr(r[4])}, emp_hex={r[5]}, hours={r[6]}')

print()

# Also check all leave_records created after the swap
print('=== All leave_records id >= 79 ===')
for r in db.execute('SELECT id, type, leave_date, employee_name, hours FROM leave_records WHERE id >= 79 ORDER BY id').fetchall():
    print(f'  id={r[0]}, type={repr(r[1])}, date={r[2]}, emp={repr(r[3])}, hours={r[4]}')

db.close()
