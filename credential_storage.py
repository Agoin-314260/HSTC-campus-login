# -*- coding: utf-8 -*-
"""
凭证存储模块
使用 Windows DPAPI（数据保护 API）加密账号密码，绑定当前 Windows 用户，
拷贝到其他电脑或供其他用户登录时均无法解密。
存储位置为当前用户注册表（HKCU\\Software\\校园网登录器），磁盘上不产生任何文件，
软件目录无论在哪台电脑上都只有 exe 一个文件。

另含旧凭证自动迁移（读取凭证 内部自动完成）：
- 旧版的 凭证.dat（exe 旁边）→ 迁入注册表后自动删除该文件
- V1.3 的 credentials.json + private_key.pem → 解密后转为注册表存储，旧文件保持原样
"""
import ctypes
import json
import os
import sys
import winreg
from ctypes import wintypes
from base64 import b64decode

# 注册表存储位置（当前用户）
_注册表路径 = r"Software\校园网登录器"
_凭证值名 = "凭证"

# DPAPI 附加熵：即使其他程序也调用 DPAPI，不知道这串熵也无法解密本程序的凭证
_应用熵 = b"HSTC-Campus-Login-v2.0"

# Windows API 常量
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _数据块(ctypes.Structure):
    """对应 Windows 的 DATA_BLOB 结构"""
    _fields_ = [
        ("大小", wintypes.DWORD),
        ("内容", ctypes.POINTER(ctypes.c_byte)),
    ]


def 程序目录():
    """获取程序所在目录（兼容 PyInstaller 打包后的环境）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _DPAPI加密(明文):
    """调用 crypt32.dll 的 CryptProtectData 加密字节串"""
    输入缓冲 = ctypes.create_string_buffer(明文, len(明文))
    输入块 = _数据块(len(明文), ctypes.cast(输入缓冲, ctypes.POINTER(ctypes.c_byte)))
    熵缓冲 = ctypes.create_string_buffer(_应用熵, len(_应用熵))
    熵块 = _数据块(len(_应用熵), ctypes.cast(熵缓冲, ctypes.POINTER(ctypes.c_byte)))
    输出块 = _数据块()
    成功 = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(输入块), None, ctypes.byref(熵块), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(输出块),
    )
    if not 成功:
        raise OSError("DPAPI 加密失败（错误码 %d）" % ctypes.GetLastError())
    try:
        return ctypes.string_at(输出块.内容, 输出块.大小)
    finally:
        ctypes.windll.kernel32.LocalFree(输出块.内容)


def _DPAPI解密(密文):
    """调用 crypt32.dll 的 CryptUnprotectData 解密字节串"""
    输入缓冲 = ctypes.create_string_buffer(密文, len(密文))
    输入块 = _数据块(len(密文), ctypes.cast(输入缓冲, ctypes.POINTER(ctypes.c_byte)))
    熵缓冲 = ctypes.create_string_buffer(_应用熵, len(_应用熵))
    熵块 = _数据块(len(_应用熵), ctypes.cast(熵缓冲, ctypes.POINTER(ctypes.c_byte)))
    输出块 = _数据块()
    成功 = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(输入块), None, ctypes.byref(熵块), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(输出块),
    )
    if not 成功:
        raise OSError("DPAPI 解密失败：数据无效或非本机本用户加密（错误码 %d）" % ctypes.GetLastError())
    try:
        return ctypes.string_at(输出块.内容, 输出块.大小)
    finally:
        ctypes.windll.kernel32.LocalFree(输出块.内容)


def _写入注册表(账号, 密码):
    """加密账号密码并写入当前用户注册表"""
    明文 = json.dumps({"账号": 账号, "密码": 密码}, ensure_ascii=False).encode("utf-8")
    密文 = _DPAPI加密(明文)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _注册表路径) as 键:
        winreg.SetValueEx(键, _凭证值名, 0, winreg.REG_BINARY, 密文)


def _读取注册表凭证():
    """从注册表读取并解密凭证，返回 (账号, 密码) 或 None"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _注册表路径) as 键:
            密文, _ = winreg.QueryValueEx(键, _凭证值名)
        数据 = json.loads(_DPAPI解密(bytes(密文)).decode("utf-8"))
        return 数据["账号"], 数据["密码"]
    except OSError:
        return None  # 未保存过
    except Exception:
        return None  # 数据无效


def _凭证文件路径():
    """旧版凭证文件（凭证.dat）的位置：exe 同目录"""
    return os.path.join(程序目录(), "凭证.dat")


def 凭证已存在():
    """判断是否已保存过凭证（注册表已存，或存在待迁移的旧凭证文件）"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _注册表路径) as 键:
            winreg.QueryValueEx(键, _凭证值名)
        return True
    except OSError:
        pass
    return os.path.exists(_凭证文件路径())


def 保存凭证(账号, 密码):
    """加密并保存账号密码（注册表存储，磁盘不产生文件）"""
    _写入注册表(账号, 密码)


def 读取凭证():
    """读取凭证，返回 (账号, 密码)；未保存时自动迁移旧凭证；失败返回 None"""
    凭证 = _读取注册表凭证()
    if 凭证 is not None:
        return 凭证
    凭证 = _迁移凭证文件()
    if 凭证 is not None:
        return 凭证
    return 迁移旧凭证()


def _迁移凭证文件():
    """把 exe 旁边的旧版 凭证.dat 迁入注册表，成功后删除该文件"""
    路径 = _凭证文件路径()
    if not os.path.exists(路径):
        return None
    try:
        with open(路径, "rb") as 文件:
            密文 = 文件.read()
        数据 = json.loads(_DPAPI解密(密文).decode("utf-8"))
        账号, 密码 = 数据["账号"], 数据["密码"]
        if not 账号 or not 密码:
            return None
        _写入注册表(账号, 密码)
        os.remove(路径)  # 迁移完成，软件目录只保留 exe
        return 账号, 密码
    except Exception:
        return None


def 旧凭证存在():
    """判断旧版（V1.3）凭证文件是否存在于程序目录"""
    目录 = 程序目录()
    return (os.path.exists(os.path.join(目录, "credentials.json"))
            and os.path.exists(os.path.join(目录, "private_key.pem")))


def 迁移旧凭证():
    """把旧版的 RSA 加密凭证迁移为注册表存储，成功返回 (账号, 密码)，失败返回 None。
    旧文件（credentials.json / private_key.pem）保持原样，不删除。"""
    if not 旧凭证存在():
        return None
    try:
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5

        目录 = 程序目录()
        with open(os.path.join(目录, "credentials.json"), "r", encoding="utf-8") as 文件:
            加密数据 = json.load(文件)
        with open(os.path.join(目录, "private_key.pem"), "rb") as 文件:
            私钥 = RSA.import_key(文件.read())

        解密器 = PKCS1_v1_5.new(私钥)
        账号 = 解密器.decrypt(b64decode(加密数据["username"]), sentinel=b"").decode("utf-8")
        密码 = 解密器.decrypt(b64decode(加密数据["password"]), sentinel=b"").decode("utf-8")
        if not 账号 or not 密码:
            return None

        # 解密成功，转为注册表存储
        保存凭证(账号, 密码)
        return 账号, 密码
    except Exception:
        return None


if __name__ == "__main__":
    # 自测：保存 → 读取 → 校验 → 清理注册表
    保存凭证("123456789012", "测试密码!@#")
    结果 = 读取凭证()
    print("读取结果：", 结果)
    assert 结果 == ("123456789012", "测试密码!@#"), "自测失败"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _注册表路径, 0,
                        winreg.KEY_SET_VALUE) as 键:
        winreg.DeleteValue(键, _凭证值名)
    print("凭证存储模块自测通过（注册表存储，磁盘无文件）")
