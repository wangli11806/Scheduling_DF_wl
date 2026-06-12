"""
排班通知脚本
支持多任务配置，每个任务可指定日期偏移、自定义前后缀
用法:
  python send_daily_notice.py --task-id morning
  python send_daily_notice.py --task-id evening --date 2026-05-25
  python send_daily_notice.py --check-and-send   (定时任务触发用，检查哪些该发)
"""
import sys, os, sqlite3, json, urllib.request, argparse
from datetime import date, datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# pythonw.exe 静默运行时没有控制台，stdout/stderr 为 None，需要重定向到空设备避免 print 报错
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_config.json")
TEAM_ORDER = ["在线组", "热线组", "售后组", "综合组", "VIP组", "质检组", "支持组"]


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_webhook_url(cfg):
    token = cfg.get("webhook_token", "")
    if not token:
        print("[SKIP] 未配置 Webhook Token")
        sys.exit(0)
    return f"https://oapi.dingtalk.com/robot/send?access_token={token}"


def query_schedules(target_date):
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. 从排班表获取工作班次员工（排除休息、放休）
    cur.execute("""
        SELECT e.name, e.team, e.position, s.shift_name
        FROM schedules s JOIN employees e ON s.employee_name = e.name
        WHERE s.schedule_date = ? AND e.status = 'active'
          AND s.shift_name NOT IN ('休息','放休')
        ORDER BY e.team, s.shift_name, e.name
    """, (target_date,))
    working = {r['name']: dict(r) for r in cur.fetchall()}

    # 2. 排除当日有换休或请假记录的员工
    cur.execute("""
        SELECT DISTINCT employee_name FROM leave_records
        WHERE type IN ('换休','leave') AND leave_date = ?
    """, (target_date,))
    for r in cur.fetchall():
        working.pop(r['employee_name'], None)

    # 3. 加入当日有换班记录的员工
    cur.execute("""
        SELECT lr.employee_name, e.team, e.position
        FROM leave_records lr
        LEFT JOIN employees e ON e.name = lr.employee_name AND e.status = 'active'
        WHERE lr.type = '换班' AND lr.leave_date = ?
    """, (target_date,))
    for r in cur.fetchall():
        name = r['employee_name']
        if name not in working:
            working[name] = {
                'name': name,
                'team': r['team'] or '',
                'position': r['position'] or '',
                'shift_name': '换班'
            }

    rows = list(working.values())
    conn.close()
    return rows


def build_message(schedules, target_date, prefix="", suffix=""):
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


def build_title(target_date, task_name=""):
    prefix = f"{task_name} " if task_name else ""
    return f"{prefix}{target_date}"


def send_dingtalk(webhook_url, markdown_text, title):
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"title": title, "text": markdown_text}
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=payload,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    return result.get("errcode") == 0


def run_task(task, cfg, override_date=None):
    """执行单个任务"""
    webhook_url = get_webhook_url(cfg)

    if override_date:
        target_date = override_date
    else:
        offset = task.get("date_offset", 0)
        d = date.today()
        if offset:
            from datetime import timedelta
            d = d + timedelta(days=offset)
        target_date = d.isoformat()

    schedules = query_schedules(target_date)
    msg = build_message(
        schedules, target_date,
        prefix=task.get("prefix", ""),
        suffix=task.get("suffix", "")
    )
    title = build_title(target_date, task.get("name", ""))
    ok = send_dingtalk(webhook_url, msg, title)

    if ok:
        print(f"[OK] {task.get('name','')} {target_date} 已发送")
    else:
        print(f"[FAIL] {task.get('name','')} {target_date} 发送失败")
        sys.exit(1)


def check_and_send():
    """定时任务入口：检查当前时间匹配哪些任务，执行匹配的"""
    cfg = load_config()
    tasks = cfg.get("tasks", [])
    if not tasks:
        return

    now = datetime.now().strftime("%H:%M")
    for task in tasks:
        if not task.get("enabled", True):
            continue
        if task.get("time", "") == now:
            print(f"[TRIGGER] {now} -> {task.get('name','')}")
            run_task(task, cfg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="排班通知脚本")
    parser.add_argument("--task-id", help="指定任务ID")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD")
    parser.add_argument("--check-and-send", action="store_true", help="检查当前时间并执行匹配任务")
    args = parser.parse_args()

    cfg = load_config()

    if args.check_and_send:
        check_and_send()
    elif args.task_id:
        task = next((t for t in cfg.get("tasks", []) if t["id"] == args.task_id), None)
        if not task:
            print(f"[ERROR] 任务 {args.task_id} 不存在")
            sys.exit(1)
        run_task(task, cfg, override_date=args.date)
    else:
        # 兼容旧用法：直接发今天的
        task = {"id": "manual", "name": "手动发送", "date_offset": 0, "prefix": "", "suffix": ""}
        run_task(task, cfg, override_date=args.date)
