#!/bin/bash
# 每日数据库备份脚本（由 crontab 每天 22:00 调用）
# 复制 schedule.db 到备份目录，保留最近 30 天

DB="/opt/schedule/schedule.db"
BACKUP_DIR="/opt/schedule/数据备份"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据库文件不存在: $DB" >&2
    exit 1
fi

STAMP=$(date +%Y-%m-%d)
cp "$DB" "$BACKUP_DIR/schedule_${STAMP}.db"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已备份: schedule_${STAMP}.db"

# 清理超过保留期的备份文件
find "$BACKUP_DIR" -name "schedule_*.db" -mtime +${RETENTION_DAYS} -delete
