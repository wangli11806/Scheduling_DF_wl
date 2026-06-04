"""
密码设置工具
用于设置/修改登录密码，密码哈希存储在 auth_config.json 中
"""
import json
import os
import hashlib
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(BASE_DIR, "auth_config.json")


def hash_password(password: str, salt: str = None) -> tuple:
    """PBKDF2 哈希密码，返回 (hash_hex, salt_hex)"""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000)
    return dk.hex(), salt


def setup():
    print("=" * 40)
    print("  排班系统 - 登录密码设置")
    print("=" * 40)

    password = input("请输入新密码: ").strip()
    if not password:
        print("密码不能为空！")
        return
    confirm = input("请再次输入密码: ").strip()
    if password != confirm:
        print("两次密码不一致！")
        return

    # 加载或创建配置
    config = {}
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 生成密码哈希
    pwd_hash, salt = hash_password(password)
    config["password_hash"] = pwd_hash
    config["salt"] = salt

    # 生成 Flask session secret_key（如果不存在）
    if "secret_key" not in config:
        config["secret_key"] = secrets.token_hex(32)

    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"\n密码已设置，配置文件: {AUTH_FILE}")


if __name__ == "__main__":
    setup()
