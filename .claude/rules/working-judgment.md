# Working 状态判断逻辑

排班数据 + 调整标签 → 联合判定员工当天是否上班。

## 核心规则

设 `wh` = 排班班次的 work_hours + 加班/换班记录的小时数，`rh` = 放休/换休记录的小时数。

| # | 排班 | 标签 | 判定 | 说明 |
|---|---|---|---|---|
| 1 | wh > 0 | 无 | working = true | 正常上班 |
| 2 | wh > 0 | 请假 或 换休 | working = false | 请假/换休优先级最高，全天不上 |
| 3 | wh > 0 | 放休 | working = (wh - rh) > 0 | 部分放休，剩余>0则仍上班 |
| 4 | wh > 0 | 加班/换班 | working = true | 加班附加在 wh 中，总时长不超过 24h |
| 5 | wh = 0 | 无 | working = false | 休息日 |
| 6 | wh = 0 | 加班/换班 | working = true | 休息日替班，wh 来自加班记录 |
| 7 | wh = 0 | 放休/换休 | 异常 | 休息日不应有放休，应拦截 |

## 涉及位置

### 后端

| 位置 | 说明 |
|---|---|
| `app.py` → `api_bot_schedules` | 钉钉机器人排班查询，返回 working 字段 |
| `app.py` → `query_schedule_data` | 通知消息查询，排除请假/换休，加入换班 |
| `send_daily_notice.py` → `query_schedules` | 独立通知脚本，逻辑同 query_schedule_data |

### 前端

| 位置 | 说明 |
|---|---|
| `总览.html` → `isEffWorking()` | 今日/明日上班人数、团队卡片、日历统计 |
| `工作安排.html` → `isEffWorking()` | 按日期筛选上班人员，工作安排保存 |

### 数据加载

前端两个页面统一从 `/api/leave-records` 加载全部调整记录，构建三个 Map：
- `restMap` — 放休 + 换休小时数
- `overtimeMap` — 加班 + 换班小时数
- `leaveDaySet` — 请假员工集合

## 修改影响

当改动 leave_records 的类型语义、排班表结构、或 working 判定公式时，以上所有位置均需同步更新。
