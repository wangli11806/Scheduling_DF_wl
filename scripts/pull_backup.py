#!/usr/bin/env python3
"""每日从 ECS 下载当天数据库备份到本地，保留最近 30 天。
由 Windows 计划任务每天 22:10 调用（略晚于 ECS 的 22:00 备份）。
"""
import subprocess, os, glob, time, sys, datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(BASE_DIR, "数据备份")
LOG_FILE = os.path.join(BASE_DIR, "logs", "pull_backup.log")
REMOTE_HOST = "root@47.102.102.115"
REMOTE_DIR = "/opt/schedule/数据备份"
RETENTION_DAYS = 30


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    remote = f"{REMOTE_HOST}:{REMOTE_DIR}/schedule_{today}.db"
    local = os.path.join(BACKUP_DIR, f"schedule_ecs_{today}.db")

    os.makedirs(BACKUP_DIR, exist_ok=True)

    env = os.environ.copy()
    env["SSH_ASKPASS"] = "/d/askpass.sh"
    env["SSH_ASKPASS_REQUIRE"] = "force"

    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "PubkeyAuthentication=no",
                "-o", "PreferredAuthentications=password"]

    r = subprocess.run(["scp", *ssh_opts, remote, local],
                       env=env, capture_output=True, timeout=120, start_new_session=True)

    if r.returncode == 0:
        log(f"已下载备份: {local}")
    else:
        log(f"下载失败: {r.stderr.decode('utf-8', errors='replace').strip()}")
        sys.exit(1)

    cutoff = time.time() - RETENTION_DAYS * 86400
    for f in glob.glob(os.path.join(BACKUP_DIR, "schedule_ecs_*.db")):
        if os.path.getmtime(f) < cutoff:
            os.remove(f)
            log(f"已清理过期备份: {os.path.basename(f)}")


if __name__ == "__main__":
    main()
