import subprocess, json, os

os.chdir('/opt/schedule')
cfg = json.load(open('auth_config.json'))
token = cfg['bot_token']

import urllib.request
url = f'http://127.0.0.1:5000/api/bot/schedules?date=2026-07-08&token={token}'
resp = urllib.request.urlopen(url)
data = json.loads(resp.read())

print(f"Total schedules: {data.get('count', 0)}")
for s in data.get('schedules', []):
    name = s['employee']
    working = s['working']
    shift = s['shift']
    if '杨沛堃' in name or '堃' in name:
        print(f'>>> FOUND: {name}, working={working}, shift={shift}')

# Also check overview-style API
print()
print('=== Checking /api/schedules + /api/leave-records approach ===')
import urllib.request
sched_data = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/schedules?start=2026-07-08&end=2026-07-08').read())
leave_data = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/leave-records').read())

# Find 杨沛堃
target = None
for s in sched_data:
    if '堃' in s['employee_name']:
        target = s
        break
if target:
    print(f'Schedule for 杨沛堃: {target["shift_name"]}')
else:
    print('杨沛堃 NOT in schedules API response!')

# Find leave records for 杨沛堃 on 2026-07-08
for lr in leave_data:
    if '堃' in lr['employee_name'] and lr['leave_date'] == '2026-07-08':
        print(f'Leave record: id={lr["id"]}, type={lr["type"]}, hours={lr["hours"]}')
