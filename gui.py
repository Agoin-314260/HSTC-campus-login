# -*- coding: utf-8 -*-
"""
界面模块（CustomTkinter 图形界面）
布局沿用旧版 V1.3 风格（深色主题），底部展示赞赏码、问题反馈与开源地址：
  账号密码输入（实时校验）/ 保存凭证（DPAPI 加密）/ 立即登录 / 自启动管理
首次打开时若检测到旧版凭证文件，自动迁移为 DPAPI 存储。
"""
import os
import sys
import webbrowser
import threading
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

import credential_storage as 凭证存储
import login_core as 登录核心
import autostart_manager as 自启动管理

# 凭证已保存时密码输入框显示的占位内容（账号直接显示真实账号）
_密码占位 = "********"

_成功色 = "#4CAF50"
_失败色 = "#F44336"
_提示色 = "#2196F3"

# 开源仓库与问题反馈地址
_开源地址 = "https://github.com/Agoin-314260/HSTC-campus-login"
_反馈地址 = _开源地址 + "/issues"


def _资源路径(文件名):
    """获取随程序打包的数据文件路径（PyInstaller onefile 运行时解压到临时目录）"""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, 文件名)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 文件名)


class 登录界面:
    def __init__(self, 根窗口):
        self.根窗口 = 根窗口
        self.根窗口.title("校园网登录器")
        self.根窗口.geometry("420x650")
        self.根窗口.resizable(False, False)

        # ===== 主容器 =====
        主框架 = ctk.CTkFrame(根窗口)
        主框架.pack(pady=20, padx=20, fill="both", expand=True)

        标题 = ctk.CTkLabel(主框架, text="韩师校园网",
                            font=("Microsoft YaHei", 18, "bold"))
        标题.pack(pady=(10, 5))

        提示 = ctk.CTkLabel(主框架, text="账号：12位数字\n密码：包含特殊符号！",
                            text_color="#FFB74D", font=("Microsoft YaHei", 12))
        提示.pack(pady=(0, 10))

        # ===== 账号输入 =====
        账号框架 = ctk.CTkFrame(主框架, fg_color="transparent")
        账号框架.pack(pady=5)
        ctk.CTkLabel(账号框架, text="账 号：", width=60, anchor="e").pack(side="left")
        self.账号输入框 = ctk.CTkEntry(账号框架, width=220,
                                       placeholder_text="输入12位数字账号")
        self.账号输入框.pack(side="left", padx=5)

        # ===== 密码输入 =====
        密码框架 = ctk.CTkFrame(主框架, fg_color="transparent")
        密码框架.pack(pady=5)
        ctk.CTkLabel(密码框架, text="密 码：", width=60, anchor="e").pack(side="left")
        self.密码输入框 = ctk.CTkEntry(密码框架, width=220, show="•",
                                       placeholder_text="输入密码")
        self.密码输入框.pack(side="left", padx=5)

        # ===== 实时校验提示 =====
        self.校验标签 = ctk.CTkLabel(主框架, text="", text_color=_失败色,
                                     font=("Microsoft YaHei", 11))
        self.校验标签.pack(pady=(10, 0))

        # ===== 按钮区 =====
        按钮框架 = ctk.CTkFrame(主框架, fg_color="transparent")
        按钮框架.pack(pady=10)

        第一行 = ctk.CTkFrame(按钮框架, fg_color="transparent")
        第一行.pack(pady=5)
        self.保存按钮 = ctk.CTkButton(第一行, text="保存凭证", width=120,
                                      command=self.保存凭证)
        self.保存按钮.pack(side="left", padx=10)
        self.登录按钮 = ctk.CTkButton(第一行, text="立即登录", width=120,
                                      fg_color=_成功色, hover_color="#45a049",
                                      command=self.开始登录)
        self.登录按钮.pack(side="left", padx=10)

        第二行 = ctk.CTkFrame(按钮框架, fg_color="transparent")
        第二行.pack(pady=5)
        self.设自启按钮 = ctk.CTkButton(第二行, text="设置自启动", width=120,
                                        fg_color=_提示色, hover_color="#1976D2",
                                        command=self.设置自启动)
        self.设自启按钮.pack(side="left", padx=10)
        self.取消自启按钮 = ctk.CTkButton(第二行, text="取消自启动", width=120,
                                          fg_color=_失败色, hover_color="#D32F2F",
                                          command=self.取消自启动)
        self.取消自启按钮.pack(side="left", padx=10)

        # ===== 自启动状态 =====
        self.自启状态标签 = ctk.CTkLabel(主框架, text="", font=("Microsoft YaHei", 10))
        self.自启状态标签.pack(pady=(5, 0))

        # ===== 赞赏码与反馈（固定在窗口底部） =====
        底部框架 = ctk.CTkFrame(主框架, fg_color="transparent")
        底部框架.pack(side="bottom", pady=(10, 0))
        赞赏图 = Image.open(_资源路径("赞赏码.jpg"))
        # 原图 902×698：中部为正方形识别图案，底部为黑底配文区。
        # 裁出识别图案（含四周白边），保证按正方形缩放时扫码图案完整占满不变形
        赞赏图 = 赞赏图.crop((220, 68, 676, 524))
        self.赞赏码图 = ctk.CTkImage(light_image=赞赏图, dark_image=赞赏图,
                                     size=(180, 180))
        ctk.CTkLabel(底部框架, image=self.赞赏码图, text="").pack()

        反馈链接 = ctk.CTkLabel(底部框架, text="有问题可以打赏备注反馈或者GitHub反馈",
                               text_color=_提示色, cursor="hand2",
                               font=("Microsoft YaHei", 11, "underline"))
        反馈链接.pack(pady=(6, 0))
        反馈链接.bind("<Button-1>", lambda 事件: webbrowser.open(_反馈地址))

        开源链接 = ctk.CTkLabel(
            底部框架, text="开源地址：github.com/Agoin-314260/HSTC-campus-login",
            text_color=_提示色, cursor="hand2",
            font=("Microsoft YaHei", 10, "underline"))
        开源链接.pack(pady=(2, 0))
        开源链接.bind("<Button-1>", lambda 事件: webbrowser.open(_开源地址))

        # ===== 登录进度条 =====
        self.进度框架 = ctk.CTkFrame(主框架, fg_color="transparent")
        self.进度条 = ctk.CTkProgressBar(self.进度框架, width=300, height=6,
                                         mode="indeterminate", indeterminate_speed=1.2)
        self.进度条.pack(pady=(5, 0))
        self.进度条.set(0)
        self.状态标签 = ctk.CTkLabel(主框架, text="", font=("Microsoft YaHei", 12))
        self.状态标签.pack(pady=5)
        self.进度框架.pack_forget()  # 初始隐藏

        # ===== 事件绑定 =====
        self.账号输入框.bind("<KeyRelease>", self.实时校验)
        self.密码输入框.bind("<KeyRelease>", self.实时校验)

        # ===== 启动初始化 =====
        self.初始化凭证()
        self.刷新自启状态()

    # ---------- 凭证初始化与迁移 ----------

    def 初始化凭证(self):
        """启动时加载凭证：优先自动迁移旧版凭证，否则显示已保存状态"""
        if not 凭证存储.凭证已存在() and 凭证存储.旧凭证存在():
            凭证 = 凭证存储.读取凭证()  # 内部自动执行旧凭证迁移
            if 凭证:
                self._显示已保存状态()
                self.校验标签.configure(
                    text="已自动迁移旧版凭证，可直接点击登录", text_color=_成功色)
                return
            self.校验标签.configure(
                text="旧版凭证迁移失败，请重新输入并保存", text_color=_失败色)
            return
        if 凭证存储.凭证已存在():
            self._显示已保存状态()

    def _显示已保存状态(self):
        """账号框显示真实账号，密码框保持隐藏"""
        凭证 = 凭证存储.读取凭证()
        if not 凭证:
            return
        self.账号输入框.delete(0, "end")
        self.账号输入框.insert(0, 凭证[0])
        self.密码输入框.delete(0, "end")
        self.密码输入框.insert(0, _密码占位)
        self.校验标签.configure(text="凭证已保存，请点击登录按钮", text_color=_成功色)

    def _已保存账号(self):
        """读取已保存的账号，未保存返回 None"""
        凭证 = 凭证存储.读取凭证()
        return 凭证[0] if 凭证 else None

    # ---------- 输入校验 ----------

    def 校验账号格式(self, 账号):
        return len(账号) == 12 and 账号.isdigit()

    def 实时校验(self, 事件=None):
        账号 = self.账号输入框.get()
        self.账号输入框.configure(
            border_color=_成功色 if self.校验账号格式(账号) else _失败色)
        if 账号 and not self.校验账号格式(账号):
            self.校验标签.configure(text="✖ 账号需要12位数字", text_color=_失败色)

    # ---------- 保存凭证 ----------

    def 保存凭证(self):
        账号 = self.账号输入框.get()
        密码 = self.密码输入框.get()
        if 密码 == _密码占位:
            if 账号 == self._已保存账号():
                messagebox.showinfo("提示", "凭证已保存过，无需重复保存")
            else:
                messagebox.showwarning("保存失败", "账号已修改，请输入该账号的密码")
            return
        if not self.校验账号格式(账号):
            messagebox.showwarning("保存失败", "账号必须为12位纯数字")
            return
        if not 密码:
            messagebox.showwarning("保存失败", "密码不能为空")
            return
        try:
            凭证存储.保存凭证(账号, 密码)
        except Exception as 错误:
            messagebox.showerror("保存异常", "加密存储失败：{}".format(错误))
            return
        self._显示已保存状态()

    # ---------- 登录 ----------

    def 开始登录(self):
        账号 = self.账号输入框.get()
        密码 = self.密码输入框.get()
        if 密码 == _密码占位:
            # 密码未改动：直接用已保存凭证（账号必须也未被修改）
            if 账号 != self._已保存账号():
                messagebox.showwarning("登录失败", "账号已修改，请同时输入该账号的密码")
                return
        else:
            if not self.校验账号格式(账号):
                messagebox.showwarning("登录失败", "账号格式不正确（12位数字）")
                return
            if not 密码:
                messagebox.showwarning("登录失败", "请输入密码")
                return
        self._显示加载中("正在登录校园网……")
        threading.Thread(target=self._后台登录, daemon=True).start()

    def _后台登录(self):
        try:
            密码 = self.密码输入框.get()
            if 密码 == _密码占位:
                凭证 = 凭证存储.读取凭证()
                if 凭证 is None:
                    self.根窗口.after(0, lambda: messagebox.showwarning(
                        "登录失败", "未找到已保存的凭证，请输入账号密码并保存"))
                    return
                账号, 密码 = 凭证
            else:
                账号 = self.账号输入框.get()

            结果, 说明 = 登录核心.登录(账号, 密码)

            # 按结果弹窗（在主线程中执行）
            if 结果 == 登录核心.成功:
                弹窗 = lambda: messagebox.showinfo("登录成功", 说明)
            elif 结果 == 登录核心.失败:
                弹窗 = lambda: messagebox.showerror("登录失败", 说明)
            else:  # 已在线 / 非校园网
                弹窗 = lambda: messagebox.showinfo("提示", 说明)
            self.根窗口.after(0, 弹窗)
        except Exception as 错误:
            消息 = "登录过程出错：{}".format(错误)
            self.根窗口.after(0, lambda: messagebox.showerror("登录异常", 消息))
        finally:
            self.根窗口.after(0, self._隐藏加载)

    def _显示加载中(self, 文本):
        self.进度框架.pack(pady=(10, 5), fill="x")
        self.状态标签.configure(text=文本)
        self.进度条.start()
        self.登录按钮.configure(state="disabled")
        self.保存按钮.configure(state="disabled")

    def _隐藏加载(self):
        self.进度框架.pack_forget()
        self.进度条.stop()
        self.状态标签.configure(text="")
        self.登录按钮.configure(state="normal")
        self.保存按钮.configure(state="normal")

    # ---------- 自启动（后台线程执行，避免界面冻结） ----------

    def 设置自启动(self):
        self._锁定自启按钮("正在设置自启动……")
        threading.Thread(target=self._后台自启操作, args=(True,), daemon=True).start()

    def 取消自启动(self):
        self._锁定自启按钮("正在取消自启动……")
        threading.Thread(target=self._后台自启操作, args=(False,), daemon=True).start()

    def _锁定自启按钮(self, 提示):
        """点击后立即给出反馈，防止重复点击"""
        self.设自启按钮.configure(state="disabled")
        self.取消自启按钮.configure(state="disabled")
        self.自启状态标签.configure(text=提示, text_color=_提示色)

    def _后台自启操作(self, 是否设置):
        try:
            if 是否设置:
                结果 = 自启动管理.设置自启动()
            else:
                结果 = 自启动管理.取消自启动()
        except Exception as 错误:
            结果 = (False, "操作出错：{}".format(错误))
        self.根窗口.after(0, lambda: self._结束自启操作(是否设置, 结果))

    def _结束自启操作(self, 是否设置, 结果):
        成功, 说明 = 结果
        self.设自启按钮.configure(state="normal")
        self.取消自启按钮.configure(state="normal")
        if 成功:
            messagebox.showinfo("操作成功" if 是否设置 else "取消成功", 说明)
        else:
            messagebox.showerror("设置失败" if 是否设置 else "取消失败", 说明)
        self.刷新自启状态()

    def 刷新自启状态(self):
        """后台查询自启动状态（schtasks 查询较慢，不阻塞界面）"""
        threading.Thread(target=self._后台刷新自启状态, daemon=True).start()

    def _后台刷新自启状态(self):
        已设置 = 自启动管理.是否已设置()

        def 更新状态():
            if 已设置:
                self.自启状态标签.configure(text="已设置自启动", text_color=_成功色)
            else:
                self.自启状态标签.configure(text="未设置自启动", text_color=_失败色)

        self.根窗口.after(0, 更新状态)


def 启动界面():
    """程序入口：创建并运行主窗口"""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    根窗口 = ctk.CTk()
    登录界面(根窗口)
    根窗口.mainloop()


if __name__ == "__main__":
    启动界面()
