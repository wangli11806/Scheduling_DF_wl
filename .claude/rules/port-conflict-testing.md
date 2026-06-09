# 端口冲突与本地测试排障

## 规则

**本地开发测试时，必须先检查目标端口是否有多个进程监听。Windows 上多个 Python 进程可同时绑定同一端口，浏览器可能连接到旧进程。**

## 为什么

- Windows 允许多进程 `SO_REUSEADDR` 绑定同一端口，无报错静默冲突
- `python app.py &` 每次创建新进程但旧进程不自动退出
- Windows Service 可能自动重启 Python 进程（如 systemd 替代方案 NSSM）
- 浏览器连接到旧进程 → 返回旧代码的错误文案 → 误判为"修改无效"
- 本次排班调整功能调试了 2 小时以上，最终发现 7 个 Python 进程抢 5000 端口

## 排查流程

收到"改了代码但没用"的报告时，按以下顺序排查：

1. **检查端口进程数**
   ```bash
   netstat -ano | grep ":5000.*LISTEN"
   ```
   超过 1 个 → 存在端口冲突。

2. **对比错误文案**
   浏览器 F12 Console 里后端返回的错误信息，与源文件中 `grep` 的同名文案对比。不一致 → 必有旧代码在运行。

3. **用 test_client 旁路验证**
   ```python
   from app import app
   with app.test_client() as c:
       c.post('/api/auth/login', json={'password': '...'})
       resp = c.post('/api/leave-records', json={...})
       print(resp.status_code)
   ```
   test_client 不走网络，结果与浏览器不同 → 端口冲突确认。

## 正确做法

1. **开发测试用独立端口**：避免与生产 Windows Service 冲突
   ```bash
   python -c "from app import app; app.run(port=5001)"
   ```

2. **清理旧进程再启动**
   ```bash
   taskkill /F /IM python.exe 2>/dev/null
   sleep 2
   python app.py
   ```

3. **不用 `&` 多次后台启动**：每次 `&` 都创建新进程。如果必须后台运行，先确认没有残留进程。

4. **测试完清理数据**：`finally` 块或手动 `DELETE` 测试记录 + 对应 schedules。
