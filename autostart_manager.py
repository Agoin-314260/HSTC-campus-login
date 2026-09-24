# -*- coding: utf-8 -*-
"""
自启动管理模块（Windows 任务计划）
通过 schtasks 创建/查询/删除任务计划，触发条件：
  1. 当前用户登录时（延迟 5 秒，等网络就绪）
  2. 网络连接变化时（连接/断开，覆盖 WiFi 重连、插拔网线等场景）
  3. 系统从睡眠/休眠恢复时（延迟 5 秒；有些机器唤醒后网卡不断线重连，
     只靠网络事件触发不到，需监听电源恢复事件兜底）
  4. 从锁屏解锁时（延迟 5 秒；用任务计划原生 SessionUnlock 触发器）

相比旧版（V1.3）的修复：
- 旧版"解锁触发器"用错了事件号（4800 是锁屏不是解锁）且需要管理员权限，
  现改用任务计划原生的 SessionUnlock 触发器（普通权限，锁屏解锁即触发）
- RunLevel 降为 LeastPrivilege，普通用户权限即可设置，不再要求右键管理员运行
- 执行命令带 --silent 参数，静默登录完成即退出，不弹窗口不占后台
- 登录失败（退出码非 0）时任务计划每分钟自动重试，最多 3 次
- 兼容 V1.3 升级：旧任务是管理员权限创建的，普通权限覆盖不了时，
  自动弹一次 UAC 提权完成"删旧建新"，之后的管理不再需要提权
- 取消自启动时顺带清理 V1.3 遗留的注册表 Run 启动项
"""
import os
import sys
import winreg
import tempfile
import subprocess

任务名 = "校园网自动登录"

# 旧版 V1.3 写入注册表 Run 键的启动项名称
_旧版注册表项名 = "校园网.exe"


def _运行schtasks(参数列表):
    """执行 schtasks 命令，返回 (返回码, 输出文本)"""
    结果 = subprocess.run(
        ["schtasks"] + 参数列表,
        capture_output=True, text=True, encoding="gbk", errors="ignore",
    )
    输出 = (结果.stdout or "") + (结果.stderr or "")
    return 结果.returncode, 输出.strip()


def _当前用户标识():
    """获取当前用户标识（DOMAIN\\用户名 形式）。
    直接读环境变量，不启动子进程（比 whoami 快，且避免杀毒软件拦截）。"""
    域 = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME", "")
    用户 = os.environ.get("USERNAME", "")
    if 域 and 用户:
        return "{}\\{}".format(域, 用户)
    return None


def _XML转义(文本):
    return 文本.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _任务XML(命令, 参数, 用户标识):
    """生成任务计划 XML：登录触发（延迟5秒）+ 网络连接变化触发 + 睡眠/休眠恢复触发
    + 锁屏解锁触发（延迟5秒），普通权限运行，失败自动重试（间隔 1 分钟，最多 3 次）。
    注意：LogonTrigger 必须带 UserId（限定当前用户），否则"任意用户登录"触发需要管理员权限。
    UserId 支持 DOMAIN\\用户名 或 SID 两种写法。"""
    用户段 = "<UserId>{}</UserId>".format(用户标识) if 用户标识 else ""
    xml = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>校园网自动登录（登录/联网时静默认证，完成即退出）</Description>
  </RegistrationInfo>
  <Triggers>
    <!-- 当前用户登录时触发，延迟 5 秒等网络就绪 -->
    <LogonTrigger>
      <Enabled>true</Enabled>
      {用户段}
      <Delay>PT5S</Delay>
    </LogonTrigger>
    <!-- 网络连接/断开时触发（10000=连接 10001=断开） -->
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;
          &lt;Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"&gt;
            &lt;Select Path="Microsoft-Windows-NetworkProfile/Operational"&gt;
              *[System[Provider[@Name='Microsoft-Windows-NetworkProfile']
                and (EventID=10000 or EventID=10001)]]
            &lt;/Select&gt;
          &lt;/Query&gt;
        &lt;/QueryList&gt;
      </Subscription>
    </EventTrigger>
    <!-- 系统从睡眠/休眠恢复时触发（Power-Troubleshooter 事件 1），延迟 5 秒等网络就绪 -->
    <EventTrigger>
      <Enabled>true</Enabled>
      <Delay>PT5S</Delay>
      <Subscription>&lt;QueryList&gt;
          &lt;Query Id="0" Path="System"&gt;
            &lt;Select Path="System"&gt;
              *[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter']
                and EventID=1]]
            &lt;/Select&gt;
          &lt;/Query&gt;
        &lt;/QueryList&gt;
      </Subscription>
    </EventTrigger>
    <!-- 从锁屏解锁时触发（原生 SessionUnlock），延迟 5 秒 -->
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      {用户段}
      <Delay>PT5S</Delay>
      <StateChange>SessionUnlock</StateChange>
    </SessionStateChangeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      {用户段}
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{命令}</Command>
      <Arguments>{参数}</Arguments>
    </Exec>
  </Actions>
</Task>"""
    return xml.format(
        用户段=用户段,
        命令=_XML转义(命令),
        参数=_XML转义(参数),
    )


def _构建执行命令():
    """根据运行环境（打包 exe / 开发脚本）生成任务计划要执行的命令和参数"""
    if getattr(sys, "frozen", False):
        # 打包后：直接执行本 exe，静默模式
        return sys.executable, "--silent"
    # 开发环境：用 pythonw（无控制台窗口）执行 main.py
    python目录 = os.path.dirname(sys.executable)
    pythonw = os.path.join(python目录, "pythonw.exe")
    解释器 = pythonw if os.path.exists(pythonw) else sys.executable
    主程序 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return 解释器, '"{}" --silent'.format(主程序)


def _任务存在():
    """任务计划是否存在（不区分新旧版本）"""
    try:
        返回码, _ = _运行schtasks(["/query", "/tn", 任务名])
        return 返回码 == 0
    except Exception:
        return False


def _任务指向本程序():
    """查询现有任务的执行命令，判断是否已指向本程序（区分 V1.3 旧任务）。
    注意：schtasks /xml 管道输出编码与系统区域设置有关（GBK 或 UTF-8），
    两种编码都解码后合并匹配，保证任何机器都不会误判。"""
    命令, _ = _构建执行命令()
    try:
        结果 = subprocess.run(
            ["schtasks", "/query", "/tn", 任务名, "/xml"], capture_output=True)
        if 结果.returncode != 0:
            return False
        原始 = 结果.stdout
        if 原始.startswith(b"\xff\xfe"):
            文本 = 原始.decode("utf-16", errors="ignore")
        else:
            文本 = (原始.decode("gbk", errors="ignore")
                    + 原始.decode("utf-8", errors="ignore"))
        # 匹配解释器文件名（pythonw.exe / 校园网登录器.exe）
        return os.path.basename(命令).lower() in 文本.lower()
    except Exception:
        return False


def _提权执行脚本(脚本内容):
    """弹出 UAC 确认框，以管理员权限执行 PowerShell 脚本并等待完成。
    用户取消 UAC 或执行失败返回 False。"""
    ps1 = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, encoding="utf-8-sig")
    try:
        ps1.write(脚本内容)
        ps1.close()
        # 外层 PowerShell 负责弹出 UAC 并等待提权进程结束
        启动命令 = (
            "Start-Process -Verb RunAs -Wait -FilePath powershell "
            "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{}'"
        ).format(ps1.name)
        结果 = subprocess.run(
            ["powershell", "-NoProfile", "-Command", 启动命令],
            capture_output=True, timeout=180)
        return 结果.returncode == 0
    except Exception:
        return False
    finally:
        try:
            os.unlink(ps1.name)
        except OSError:
            pass


def _清理旧版注册表项():
    """删除 V1.3 遗留的注册表 Run 启动项（HKCU 无需提权，不存在则忽略）"""
    try:
        注册表键 = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_WRITE,
        )
        try:
            winreg.DeleteValue(注册表键, _旧版注册表项名)
        finally:
            winreg.CloseKey(注册表键)
    except OSError:
        pass


def 设置自启动():
    """创建自启动任务计划，返回 (是否成功, 说明)。
    直接以普通权限创建（/f 覆盖式，重复设置无副作用）；
    若被 V1.3 管理员创建的旧任务阻挡，自动弹一次 UAC 完成替换。"""
    命令, 参数 = _构建执行命令()
    xml内容 = _任务XML(命令, 参数, _当前用户标识())
    xml临时 = tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-16")
    try:
        xml临时.write(xml内容)
        xml临时.close()
        返回码, 输出 = _运行schtasks(
            ["/create", "/tn", 任务名, "/xml", xml临时.name, "/f"])
        if 返回码 == 0:
            return True, "已设置自启动（登录、联网、休眠唤醒和解锁时自动静默登录）"

        # 普通权限失败：多为 V1.3 旧任务（管理员创建）阻挡，提权一次性替换
        脚本 = 'schtasks /delete /tn "{0}" /f\nschtasks /create /tn "{0}" /xml "{1}" /f\n'.format(
            任务名, xml临时.name)
        if _提权执行脚本(脚本) and _任务指向本程序():
            return True, "已设置自启动（替换了旧版任务，如弹出确认框请允许）"
        return False, "任务计划创建失败：{}".format(输出 or "未知错误")
    finally:
        try:
            os.unlink(xml临时.name)
        except OSError:
            pass


def 取消自启动():
    """删除自启动任务计划（含 V1.3 遗留），并清理注册表启动项，返回 (是否成功, 说明)"""
    _清理旧版注册表项()
    返回码, 输出 = _运行schtasks(["/delete", "/tn", 任务名, "/f"])
    if 返回码 == 0:
        return True, "已取消自启动"
    # 普通权限删不掉（V1.3 管理员任务）→ 提权删除
    脚本 = 'schtasks /delete /tn "{}" /f\n'.format(任务名)
    if _提权执行脚本(脚本) and not _任务存在():
        return True, "已取消自启动（如弹出确认框请允许）"
    return False, "任务计划不存在或删除失败：{}".format(输出 or "未知错误")


def 是否已设置():
    """查询自启动是否已指向本程序（存在 V1.3 旧任务不算）"""
    return _任务指向本程序()


if __name__ == "__main__":
    # 自测：设置 → 查询 → 取消（可能弹 UAC 确认框）
    print("设置：", 设置自启动())
    print("查询：", 是否已设置())
    print("取消：", 取消自启动())
    print("查询：", 是否已设置())
