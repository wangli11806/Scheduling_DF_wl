"""
从截图读取的2026年2月排班数据，转换为系统格式并导入。

截图格式说明（矩阵模板）：
- 第一列：员工姓名
- 第一行：日期（从第二列开始，2/1 ~ 2/28）
- 单元格：A=A班, B=B班, 空=休息, 假=请假
- 此格式即为日常上传的排班Excel模板格式

识别过程：
1. 观察截图中的颜色：绿色单元格=A班，蓝色单元格=B班，白色/空白=休息，标注"假"=请假
2. 2月周末日期：1(Sun), 7(Sat), 8(Sun), 14(Sat), 15(Sun), 21(Sat), 22(Sun), 28(Sat)
3. 逐行读取每位员工28天的排班数据
4. 转换为 (姓名, 日期, 班次) 单行格式，通过 POST /api/schedules/batch 导入

============================================================
班次代码映射表（与 app.py code_to_shift 保持一致）
============================================================

三级匹配逻辑（app.py resolve_shift）：
  1. 精确代码映射 → 代码表中的目标班次名，再校验是否在班次表中存在
  2. 直接名称匹配 → 单元格值是否等于班次表中的班次名称
  3. 模糊子串匹配 → 双向子串匹配（"A班"包含"A"，"早班"包含"班"等）

代码映射表：
  A / a       → A班 (SHF001)
  B / b       → B班 (SHF002)
  C / c       → C班 (SHF003)
  T / t       → T班 (SHF004)
  E / e       → E班 (SHF005)
  F / f       → F班 (SHF006)
  休 / 休假 / 休息  → 休息 (SHF007)
  调休 / 放休       → 放休 (SHF008)
  假 / 请假         → 请假

空单元格           → 休息（resolve_shift 直接返回，不经过代码映射）

============================================================
导入方式说明
============================================================

对于 Excel 文件上传，系统提供两个端点：
  - POST /api/schedules/import-matrix  → 矩阵格式（推荐，行列交叉）
  - POST /api/schedules/import         → 列表格式（日期、员工、班次三列）

导入结果反馈：
  - 成功时返回 {"ok": true, "updated": N} 显示成功条数
  - 部分失败时额外返回 failures 数组，每项含 row/employee/date/reason
  - 前端自动下载失败行 Excel，延迟 2-10s 随机触发
  - 同员工同日期已有排班 → 自动替换（ON CONFLICT ... DO UPDATE）

本脚本因数据来源为截图（非 Excel 文件），故将硬编码数据转换为列表格式后，
通过 POST /api/schedules/batch 批量导入，效果与 Excel 导入一致。
"""

import json
import urllib.request
import urllib.error

API = "http://127.0.0.1:5000/api"

# ============================================================
# 以下为从截图中逐行识别的排班数据
# 格式：{员工姓名: [2/1班次, 2/2班次, ..., 2/28班次]}
# A=A班, B=B班, 空字符串=休息, 假=请假
# ============================================================

raw_data = {
    "张三": [
        "",                     # 2/1  Sun 休息
        "A", "A", "B", "B", "A",  # 2/2~2/6 Mon-Fri
        "", "",                 # 2/7~2/8 Sat-Sun 休息
        "A", "A", "B", "B", "A",  # 2/9~2/13 Mon-Fri
        "", "",                 # 2/14~2/15 Sat-Sun 休息
        "A",                    # 2/16 Mon
        "假",                   # 2/17 Tue 请假
        "B", "B", "A",          # 2/18~2/20 Wed-Fri
        "", "",                 # 2/21~2/22 Sat-Sun 休息
        "A", "A", "B", "B", "A",  # 2/23~2/27 Mon-Fri
        "",                     # 2/28 Sat 休息
    ],
    "李四": [
        "",                     # 2/1  Sun 休息
        "B", "B", "A", "A", "B",  # 2/2~2/6 Mon-Fri
        "", "",                 # 2/7~2/8 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/9~2/13 Mon-Fri
        "", "",                 # 2/14~2/15 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/16~2/20 Mon-Fri
        "", "",                 # 2/21~2/22 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/23~2/27 Mon-Fri
        "",                     # 2/28 Sat 休息
    ],
    "王芳": [
        "",                     # 2/1  Sun 休息
        "A", "A", "B", "B", "A",  # 2/2~2/6 Mon-Fri
        "", "",                 # 2/7~2/8 Sat-Sun 休息
        "A", "A", "B", "B", "A",  # 2/9~2/13 Mon-Fri
        "", "",                 # 2/14~2/15 Sat-Sun 休息
        "A", "A", "B", "B", "A",  # 2/16~2/20 Mon-Fri
        "", "",                 # 2/21~2/22 Sat-Sun 休息
        "A", "A", "B", "B", "A",  # 2/23~2/27 Mon-Fri
        "",                     # 2/28 Sat 休息
    ],
    "赵磊": [
        "",                     # 2/1  Sun 休息
        "B", "B", "A", "A", "B",  # 2/2~2/6 Mon-Fri
        "", "",                 # 2/7~2/8 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/9~2/13 Mon-Fri
        "", "",                 # 2/14~2/15 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/16~2/20 Mon-Fri
        "", "",                 # 2/21~2/22 Sat-Sun 休息
        "B", "B", "A", "A", "B",  # 2/23~2/27 Mon-Fri
        "",                     # 2/28 Sat 休息
    ],
    "陈敏": [
        "",                     # 2/1  Sun 休息
        "A", "B", "A", "B", "A",  # 2/2~2/6 Mon-Fri (主管轮值)
        "", "",                 # 2/7~2/8 Sat-Sun 休息
        "A", "B", "A", "B", "A",  # 2/9~2/13 Mon-Fri
        "", "",                 # 2/14~2/15 Sat-Sun 休息
        "A", "B", "A", "B", "A",  # 2/16~2/20 Mon-Fri
        "", "",                 # 2/21~2/22 Sat-Sun 休息
        "A", "B", "A", "B", "A",  # 2/23~2/27 Mon-Fri
        "",                     # 2/28 Sat 休息
    ],
}

# 代码→班次名称映射（与 app.py code_to_shift 保持一致，三级匹配的第一级）
SHIFT_MAP = {
    "A": "A班", "a": "A班",
    "B": "B班", "b": "B班",
    "C": "C班", "c": "C班",
    "T": "T班", "t": "T班",
    "E": "E班", "e": "E班",
    "F": "F班", "f": "F班",
    "休": "休息", "休假": "休息", "休息": "休息",
    "调休": "放休", "放休": "放休",
    "假": "请假", "请假": "请假",
}


def convert_to_entries(data):
    """将矩阵格式转换为 [{date, employee, shift}, ...]
    使用与 app.py resolve_shift 一致的映射逻辑：
    - 空单元格 → "休息"
    - 有值单元格 → SHIFT_MAP 精确映射
    """
    entries = []
    for emp_name, shifts in data.items():
        if len(shifts) != 28:
            print(f"  [!] {emp_name}: 数据不足28天（{len(shifts)}天）")
        for i, code in enumerate(shifts):
            day = i + 1
            date_str = f"2026-02-{day:02d}"
            if not code:
                shift = "休息"
            else:
                shift = SHIFT_MAP.get(code, code)
            entries.append({
                "date": date_str,
                "employee": emp_name,
                "shift": shift,
            })
    return entries


def import_schedules(entries):
    """通过 POST /api/schedules/batch 批量导入排班数据
    同员工同日期已有排班 → 自动替换（ON CONFLICT DO UPDATE）
    """
    url = f"{API}/schedules/batch"
    data = json.dumps({"entries": entries}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


if __name__ == "__main__":
    print("=" * 55)
    print("  矩阵格式排班数据导入工具")
    print("  截图来源：2026年2月排班表Excel截图")
    print("=" * 55)

    entries = convert_to_entries(raw_data)
    print(f"\n转换结果：{len(entries)} 条排班记录")
    print(f"  其中休息: {sum(1 for e in entries if e['shift'] == '休息')} 天")
    print(f"  其中A班:  {sum(1 for e in entries if e['shift'] == 'A班')} 天")
    print(f"  其中B班:  {sum(1 for e in entries if e['shift'] == 'B班')} 天")
    print(f"  其中请假: {sum(1 for e in entries if e['shift'] == '请假')} 天")

    # 预览前几条
    print("\n数据预览（前10条）：")
    for e in entries[:10]:
        print(f"  {e['date']}  {e['employee']}  ->  {e['shift']}")
    print("  ...")

    # 确认导入
    print("\n正在导入到数据库...")
    result = import_schedules(entries)
    if result.get("ok"):
        print(f"[OK] 成功导入 {result['updated']} 条排班记录！")
    else:
        print(f"[FAIL] 导入失败: {result}")
