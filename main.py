import sys
import customtkinter as ctk
from main_window import MainWindow


# 添加主程序入口点
if __name__ == "__main__":
    # 避免在子进程中创建GUI
    if len(sys.argv) > 1:
        # 这是一个子进程调用，不创建GUI
        sys.exit(0)
        
    # 设置customtkinter的外观模式和主题
    ctk.set_appearance_mode("Light")  # 默认设置为浅色模式
    ctk.set_default_color_theme("green")
        
    app = MainWindow()
    app.mainloop()