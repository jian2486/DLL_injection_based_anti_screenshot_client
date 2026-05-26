#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
import win32gui
import win32con
import threading
import time
import sys
import os
from ctypes import windll, c_bool
from ctypes.wintypes import HWND, DWORD


# 定义常量
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011


class FullScreenAntiScreenshot:
    """
    全屏反截屏保护类
    创建一个全屏、无边框、鼠标穿透、不会被聚焦的窗口，并应用模式二的反截屏保护
    """

    def __init__(self, protection_interval=0.1, protection_enabled=True, continuous_protection=True):
        """
        初始化全屏反截屏保护
        
        Args:
            protection_interval (float): 保护应用间隔（秒）
            protection_enabled (bool): 是否启用保护
            continuous_protection (bool): 是否启用连续保护（循环设置反截屏和置顶属性）
        """
        self.protection_interval = protection_interval
        self.protection_enabled = protection_enabled
        self.continuous_protection = continuous_protection  # 新增：是否启用连续保护
        self.root = None
        self._running = False

    def setup_fullscreen_window(self):
        """设置全屏窗口"""
        if self.root:
            return

        self.root = tk.Tk()
        # 移除窗口边框和标题栏
        self.root.overrideredirect(True)

        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # 设置窗口大小为全屏
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        # 设置窗口背景色为透明黑色
        self.root.configure(bg='black')
        self.root.attributes('-transparentcolor', 'black')

        # 创建一个标签用于显示信息
        info_label = tk.Label(
            self.root,
            text="全屏反截屏保护已激活\n此窗口会阻止屏幕截图软件捕获屏幕内容",
            font=("Arial", 16),
            fg="white",
            bg="black"
        )
        info_label.pack(expand=True)

    def apply_window_properties(self):
        """应用窗口特殊属性"""
        if not self.root:
            return

        # 确保窗口更新完成后获取HWND
        self.root.update_idletasks()
        self.root.update()

        # 获取窗口句柄
        hwnd = win32gui.GetParent(self.root.winfo_id()) or self.root.winfo_id()

        # 设置窗口样式为无边框并应用所需属性
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            ex_style | win32con.WS_EX_TOPMOST | win32con.WS_EX_TRANSPARENT |
            win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_LAYERED
        )

        # 设置窗口始终置顶 (HWND_TOPMOST)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        )

        # 设置窗口透明度为完全透明但仍可见
        win32gui.SetLayeredWindowAttributes(hwnd, 0, 1, win32con.LWA_ALPHA)

    def apply_display_affinity(self, enable=True):
        """应用显示关联性保护（模式二）"""
        if not self.root:
            return

        # 获取窗口句柄
        hwnd = win32gui.GetParent(self.root.winfo_id()) or self.root.winfo_id()

        # 设置或移除WDA_MONITOR属性以防止或允许屏幕截图
        try:
            # 使用ctypes调用SetWindowDisplayAffinity函数
            user32 = windll.user32
            user32.SetWindowDisplayAffinity.argtypes = [HWND, DWORD]
            user32.SetWindowDisplayAffinity.restype = c_bool
            
            # 根据enable参数决定是应用保护还是移除保护
            affinity = DWORD(WDA_MONITOR) if enable else DWORD(WDA_NONE)
            result = user32.SetWindowDisplayAffinity(HWND(hwnd), affinity)
            if result:
                if enable:
                    print("成功应用反截屏保护")
                else:
                    print("成功移除反截屏保护")
            else:
                # 获取错误代码
                error_code = windll.kernel32.GetLastError()
                if enable:
                    print(f"应用反截屏保护失败，错误代码: {error_code}")
                else:
                    print(f"移除反截屏保护失败，错误代码: {error_code}")
        except Exception as e:
            if enable:
                print(f"应用反截屏保护时出现错误: {e}")
            else:
                print(f"移除反截屏保护时出现错误: {e}")

    def start_anti_screenshot_protection(self):
        """持续应用反截屏保护"""
        def protection_loop():
            # 如果不启用连续保护，只执行一次
            if not self.continuous_protection:
                if self.protection_enabled:
                    self.apply_display_affinity(True)  # 启用保护
                    self.apply_window_properties()  # 确保窗口属性也被应用
                return
            
            # 如果启用连续保护，循环执行
            while self._running:
                if self.protection_enabled:
                    self.apply_display_affinity(True)  # 启用保护
                    self.apply_window_properties()  # 持续应用窗口属性
                else:
                    # 即使保护被禁用，也要确保属性被移除
                    self.apply_display_affinity(False)  # 禁用保护
                time.sleep(self.protection_interval)

        # 在后台线程中运行保护循环
        self._running = True
        protection_thread = threading.Thread(target=protection_loop, daemon=True)
        protection_thread.start()

    def set_protection_enabled(self, enabled):
        """
        启用或禁用保护
        
        Args:
            enabled (bool): 是否启用保护
        """
        self.protection_enabled = enabled
        # 如果不是连续保护模式，我们需要立即应用更改
        if not self.continuous_protection and self._running:
            self.apply_display_affinity(enabled)

    def set_continuous_protection(self, continuous):
        """
        设置是否启用连续保护
        
        Args:
            continuous (bool): 是否启用连续保护
        """
        self.continuous_protection = continuous

    def start(self):
        """启动全屏反截屏保护"""
        if self._running:
            return

        self.setup_fullscreen_window()
        # 即使不启用连续保护，也要至少应用一次窗口属性
        self.apply_window_properties()
        self.start_anti_screenshot_protection()

        # 开始主循环
        if self.root:
            self.root.mainloop()

    def stop(self):
        """停止全屏反截屏保护"""
        self._running = False
        if self.root:
            # 确保在主线程中销毁窗口
            self.root.after(0, self._destroy_root)
            self.root = None
    
    def _destroy_root(self):
        """在主线程中销毁根窗口"""
        try:
            if self.root:
                self.root.destroy()
        except Exception as e:
            print(f"销毁窗口时出错: {e}")


# 测试代码（独立运行时使用）
if __name__ == "__main__":
    app = FullScreenAntiScreenshot()
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()
        print("程序已退出")