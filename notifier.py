# -*- coding: utf-8 -*-
"""
系统通知模块
基于 winotify 的 Windows 10/11 原生 toast 通知（替代已废弃的 win10toast）。
用于静默自动登录的结果提醒：成功用提醒音、失败用默认音，方便用户区分；
通知失败不影响登录主流程。
"""
from winotify import Notification, audio


def 弹出通知(标题, 内容):
    """弹出系统通知（默认提示音，用于失败等场景）；
    任何异常都静默忽略，保证不影响登录主流程"""
    try:
        通知 = Notification(app_id="校园网登录器", title=标题, msg=内容)
        通知.set_audio(audio.Default, loop=False)
        通知.show()
    except Exception:
        pass


def 弹出成功通知(标题, 内容):
    """弹出成功类通知（提醒音，与失败通知区分）；
    任何异常都静默忽略，保证不影响登录主流程"""
    try:
        通知 = Notification(app_id="校园网登录器", title=标题, msg=内容)
        通知.set_audio(audio.Reminder, loop=False)
        通知.show()
    except Exception:
        pass


if __name__ == "__main__":
    弹出通知("测试通知", "默认提示音")
    弹出成功通知("测试成功通知", "提醒音")
