# -*- coding: utf-8 -*-
"""
登录核心模块（韩师校园网 CAS 认证）
流程：检测校园网环境 → 采集本机网络信息 → 拼登录地址 → 取 execution 标识 →
取 CAS 公钥 → RSA 加密密码 → 提交登录 → 解析结果。

登录流程逻辑与旧版脚本（原电脑/校园网.py）保持一致，修复了以下问题：
- 所有网络请求增加超时，不再无限卡死
- execution / 标题解析失败时明确报错，不再返回 None 继续执行
- 网关解析兼容中英文 Windows（同时识别"在链路上"和"On-link"）
- 去掉 BeautifulSoup / rsa 依赖，用正则 + pycryptodome 替代
"""
import re
import uuid
import base64
import socket
import subprocess

import requests
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ===== 登录结果常量 =====
成功 = "成功"
已在线 = "已在线"
非校园网 = "非校园网"
失败 = "失败"

# ===== 学校认证服务器配置 =====
_CAS服务器 = "https://hscas.hstc.edu.cn/cas/login"
_公钥地址 = "https://hscas.hstc.edu.cn/cas/jwt/publicKey"
_门户地址 = "http://192.168.2.34:801/eportal/portal/cas/login"
_校园网检测地址 = "http://rz.hstc.edu.cn/"
_请求头 = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
}

# 网关 → 接入点名称映射（沿用旧版配置）
_接入点映射 = {
    "192.168.2.33": "CORE-RG-N18012",
    "10.0.0.1": "CORE-ROUTER-2",
    "172.16.0.1": "BACKUP-AP",
}


def 是否在校园网():
    """检测当前是否连接到校园网（校园内网址可达即视为在校园网）"""
    try:
        响应 = requests.get(_校园网检测地址, timeout=3)
        return 响应.status_code == 200
    except Exception:
        return False


def 获取本机IP():
    """获取本机内网 IPv4 地址（UDP 连接法，不会真正发包）"""
    try:
        套接字 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        套接字.connect(("8.8.8.8", 80))
        地址 = 套接字.getsockname()[0]
        套接字.close()
        return 地址
    except Exception:
        return "192.168.1.1"


def 获取MAC地址():
    """获取本机 MAC 地址（12 位无分隔小写）"""
    return "{:012x}".format(uuid.getnode())


def 获取网关IP():
    """解析系统路由表获取默认网关，兼容中英文系统；失败时回退默认值"""
    try:
        结果 = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, encoding="gbk", errors="ignore",
        )
        for 行 in 结果.stdout.splitlines():
            字段 = 行.split()
            # 默认路由行：目标 0.0.0.0 + 掩码 0.0.0.0 + 网关
            if (len(字段) >= 3 and 字段[0] == "0.0.0.0" and 字段[1] == "0.0.0.0"
                    and 字段[2] not in ("在链路上", "On-link")):
                return 字段[2]
    except Exception:
        pass
    return "192.168.2.33"


def 构造登录地址():
    """采集本机信息并构造 CAS 登录地址"""
    本机IP = 获取本机IP()
    MAC = 获取MAC地址()
    网关 = 获取网关IP()
    接入点 = _接入点映射.get(网关, "UNKNOWN-AP")

    # state 字符串与旧版保持一致
    状态串 = "1|0|{}||{}||{}|{}|".format(本机IP, MAC, 网关, 接入点)
    状态编码 = base64.b64encode(状态串.encode("utf-8")).decode("utf-8")
    服务地址 = "{}?state={}".format(_门户地址, 状态编码)
    return "{}?service={}".format(_CAS服务器, quote(服务地址, safe=""))


def _提取execution(页面内容):
    """从登录页 HTML 中提取 execution 标识，失败返回 None"""
    匹配 = re.search(r'name="execution"[^>]*value="([^"]+)"', 页面内容)
    if not 匹配:
        # 属性顺序可能相反：value 在前 name 在后
        匹配 = re.search(r'value="([^"]+)"[^>]*name="execution"', 页面内容)
    return 匹配.group(1) if 匹配 else None


def _加密密码(密码, 公钥文本):
    """使用 CAS 公钥 RSA 加密密码（PKCS1_v1_5，加 __RSA__ 前缀，与服务器约定一致）"""
    密钥 = RSA.import_key(公钥文本)
    加密器 = PKCS1_v1_5.new(密钥)
    密文字节 = 加密器.encrypt(密码.encode("utf-8"))
    return "__RSA__" + base64.b64encode(密文字节).decode("utf-8")


def 登录(账号, 密码):
    """执行完整登录流程，返回 (结果, 说明)。
    结果取值：成功 / 已在线 / 非校园网 / 失败"""
    if not 是否在校园网():
        return 非校园网, "当前不在校园网环境，无需登录"

    会话 = requests.Session()
    会话.headers.update(_请求头)

    try:
        # 1. 打开登录页，取 execution 标识
        登录地址 = 构造登录地址()
        页面响应 = 会话.get(登录地址, timeout=10)
        页面响应.raise_for_status()
        execution = _提取execution(页面响应.text)
        if not execution:
            return 失败, "登录页解析失败（未找到 execution 标识）"

        # 2. 获取 CAS 公钥并加密密码
        公钥响应 = 会话.get(_公钥地址, timeout=10)
        公钥响应.raise_for_status()
        加密后密码 = _加密密码(密码, 公钥响应.text.strip())

        # 3. 提交登录
        表单 = {
            "username": 账号,
            "password": 加密后密码,
            "currentMenu": "1",
            "_eventId": "submit",
            "submit": "Login1",
            "failN": "0",
            "execution": execution,
        }
        提交响应 = 会话.post(登录地址, data=表单, timeout=15)

        if 提交响应.status_code == 401:
            return 失败, "账号或密码错误"

        # 4. 按返回页标题判断结果（与旧版判定规则一致）
        标题匹配 = re.search(r"<title>(.*?)</title>", 提交响应.text, re.S)
        if 标题匹配:
            标题 = 标题匹配.group(1).strip()
            if 标题 == "信息页":
                return 已在线, "已经在线，无需重复登录"
            if 标题 == "认证成功页":
                return 成功, "校园网认证成功"
            return 失败, "认证异常：" + 标题
        return 失败, "服务器响应异常（未找到页面标题）"

    except requests.exceptions.Timeout:
        return 失败, "网络请求超时，请检查网络后重试"
    except requests.exceptions.RequestException as 错误:
        return 失败, "网络请求失败：{}".format(错误)
    except Exception as 错误:
        return 失败, "未知错误：{}".format(错误)


if __name__ == "__main__":
    # 自测：仅检测网络环境，不真正登录
    print("是否在校园网：", 是否在校园网())
    print("本机IP：", 获取本机IP())
    print("MAC地址：", 获取MAC地址())
    print("网关IP：", 获取网关IP())
    print("登录地址：", 构造登录地址())
