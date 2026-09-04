"""
钉钉工作安排通知脚本
每天16:00由 cron 调用，查询次日售后组客服的工作安排，按工作类型聚合后推送到钉钉群。

用法：
    python scripts/send_work_notice.py                # 推送次日安排
    python scripts/send_work_notice.py --date 2026-07-30   # 推送指定日期（测试用）
    python scripts/send_work_notice.py --dry-run      # 只打印消息，不发送
"""

import sys
import os
import json
import sqlite3
import urllib.request
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, "schedule.db")
AUTH_FILE = os.path.join(BASE_DIR, "auth_config.json")

TEAM = "售后组"
TARGET_WORK_TYPES = ["工单", "反向工单", "自主售后", "售后单", "紧急", "本地生活"]


def next_date():
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


def load_webhook():
    if not os.path.exists(AUTH_FILE):
        raise RuntimeError("auth_config.json 不存在")
    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("dingtalk_work_webhook", "")


def query_assignments(target_date):
    """返回 {工作类型: [员工名...]}，按员工名排序"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """
        SELECT a.employee_name, a.work_types
        FROM daily_assignments a
        JOIN employees e ON e.name = a.employee_name
        WHERE a.date = ?
          AND e.team = ?
          AND e.status = 'active'
          AND e.position = '客服'
        ORDER BY a.employee_name
        """,
        [target_date, TEAM],
    ).fetchall()
    db.close()

    type_map = {}
    for r in rows:
        try:
            work_types = json.loads(r["work_types"] or "[]")
        except (ValueError, TypeError):
            work_types = []
        for w in work_types:
            if w in TARGET_WORK_TYPES:
                type_map.setdefault(w, []).append(r["employee_name"])
    return type_map


def build_message(target_date, type_map):
    lines = [f"明天 **{target_date}** 售后组工作安排如下："]
    for w in TARGET_WORK_TYPES:
        names = type_map.get(w, [])
        lines.append(f"**{w}**：{'、'.join(names)}")
    lines.append("关于工作安排有任何问题，请联系主管~")
    return "\n\n".join(lines)


def send_to_dingtalk(webhook, title, content):
    payload = json.dumps(
        {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": content},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    target_date = next_date()
    if "--date" in args:
        i = args.index("--date")
        if i + 1 < len(args):
            target_date = args[i + 1]

    type_map = query_assignments(target_date)
    if not type_map:
        print(f"[跳过] {target_date} 售后组无匹配的工作安排")
        return

    content = build_message(target_date, type_map)
    print(content)

    if dry_run:
        print("\n[dry-run] 未发送")
        return

    webhook = load_webhook()
    if not webhook:
        print("[错误] auth_config.json 缺少 dingtalk_work_webhook")
        return
    title = f"售后组工作安排 {target_date}"
    resp = send_to_dingtalk(webhook, title, content)
    print(f"\n[已发送] {resp}")


if __name__ == "__main__":
    main()
