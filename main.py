# -*- coding: utf-8 -*-
"""
校园网登录器（电脑版）主程序

用法：
  校园网登录器.exe           打开图形界面（配置凭证、手动登录、管理自启动）
  校园网登录器.exe --silent  静默模式：后台自动登录，完成即退出，不占后台
                             （由自启动任务计划在登录/联网/休眠唤醒时触发；
                              所有结果都弹系统通知，失败后任务计划自动重试）
"""
import sys


def 静默登录():
    """静默模式：读取凭证 → 自动登录 → 退出。
    所有结果（成功/失败/已在线/非校园网）都弹系统通知；失败以退出码 1 结束，
    任务计划检测到非零退出码后每分钟自动重试，最多 3 次。"""
    import credential_storage as 凭证存储
    import login_core as 登录核心
    import notifier as 系统通知

    凭证 = 凭证存储.读取凭证()
    if 凭证 is None:
        系统通知.弹出通知("校园网登录失败", "未找到已保存的账号密码，请打开软件重新保存")
        sys.exit(1)

    结果, 说明 = 登录核心.登录(凭证[0], 凭证[1], 等待网络秒=30)
    if 结果 == 登录核心.失败:
        系统通知.弹出通知("校园网登录失败", 说明)
        sys.exit(1)
    if 结果 == 登录核心.成功:
        系统通知.弹出成功通知("校园网登录成功", 说明)
    else:  # 已在线 / 非校园网：同样弹通知告知结果
        系统通知.弹出通知("校园网登录提示", 说明)
    sys.exit(0)


def main():
    if "--silent" in sys.argv:
        静默登录()
    else:
        import ctypes
        try:
            # 高分屏适配：按系统 DPI 渲染，125%/150% 缩放下界面文字不模糊
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass  # 旧系统没有该 API，忽略即可
        from gui import 启动界面
        启动界面()


if __name__ == "__main__":
    main()
