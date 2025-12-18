import json
import os


class DataManager:
    """数据管理类，负责保存和加载配置数据"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def save_data(self, show_status=True):
        """保存数据到配置文件"""
        try:
            # 收集所有需要保存的数据
            config_data = {
                "theme": self.main_window.theme_var.get(),
                "mode1_items": [],
                "mode2_items": [],
                "current_mode": self.main_window.current_mode,
                "child_process_injection_enabled": self.main_window.child_process_injection_var.get(),  # 保存子进程注入开关状态
                "auto_start_enabled": self.main_window.auto_start_var.get(),  # 保存开机自启动设置
                "fullscreen_antiscreenshot_enabled": self.main_window.fullscreen_antiscreenshot_var.get() if hasattr(self.main_window, 'fullscreen_antiscreenshot_var') else False,  # 保存全屏反截屏开关状态
                "fullscreen_antiscreenshot_interval": self.main_window.fullscreen_interval_var.get() if hasattr(self.main_window, 'fullscreen_interval_var') else "0.1",  # 保存全屏反截屏间隔
                "continuous_protection_enabled": self.main_window.continuous_protection_var.get() if hasattr(self.main_window, 'continuous_protection_var') else True  # 保存连续保护开关状态
            }
            
            # 保存模式一列表项
            for i in range(self.main_window.mode1_listbox.size()):
                item_text = self.main_window.mode1_listbox.get(i)
                # 检查是否有状态指示器（红点表示禁用，绿点表示启用）
                is_enabled = True
                if item_text.startswith("● "):
                    # 获取项目状态
                    is_enabled = getattr(self.main_window.mode1_listbox, f"item_{i}_status", "enabled") != "disabled"
                    # 保存时不带状态指示器的文本
                    clean_text = item_text[2:]
                else:
                    clean_text = item_text
                    
                config_data["mode1_items"].append({
                    "text": clean_text,
                    "enabled": is_enabled
                })
            
            # 保存模式二列表项
            for i in range(self.main_window.mode2_listbox.size()):
                item_text = self.main_window.mode2_listbox.get(i)
                # 检查是否有状态指示器（红点表示禁用，绿点表示启用）
                is_enabled = True
                if item_text.startswith("● "):
                    # 获取项目状态
                    is_enabled = getattr(self.main_window.mode2_listbox, f"item_{i}_status", "disabled") != "disabled"
                    # 保存时不带状态指示器的文本
                    clean_text = item_text[2:]
                else:
                    clean_text = item_text
                    
                config_data["mode2_items"].append({
                    "text": clean_text,
                    "enabled": is_enabled
                })
            
            # 保存到配置文件
            config_file = "config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            
            # 只在手动保存时显示状态信息
            if show_status:
                self.main_window.status_label.configure(text=f"配置已保存到 {config_file}")
        except Exception as e:
            if show_status:
                self.main_window.status_label.configure(text=f"保存配置失败: {str(e)}")
    
    def load_data(self):
        """从配置文件加载数据"""
        try:
            config_file = "config.json"
            if not os.path.exists(config_file):
                self.main_window.status_label.configure(text="配置文件不存在")
                # 即使没有配置文件，也要刷新列表
                self.main_window.after(100, self.main_window._delayed_list_refresh)
                return
                
            # 从配置文件加载数据
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            # 恢复主题设置
            theme = config_data.get("theme", "Light")
            self.main_window.theme_var.set(theme)
            self.main_window.change_theme()
            
            # 恢复反截屏开关状态（已移除程序自身反截屏功能）
            anti_screenshot_enabled = config_data.get("anti_screenshot_enabled", True)
            # 程序自身反截屏功能已移除，忽略此配置
            # 根据配置设置反截屏功能，但仅在开关启用时才执行
            if anti_screenshot_enabled:
                # 程序自身反截屏功能已移除，忽略此配置
                pass
            
            # 恢复子进程注入开关状态
            child_process_injection_enabled = config_data.get("child_process_injection_enabled", False)
            self.main_window.child_process_injection_var.set(child_process_injection_enabled)
            
            # 恢复全屏反截屏开关状态
            fullscreen_antiscreenshot_enabled = config_data.get("fullscreen_antiscreenshot_enabled", False)
            if hasattr(self.main_window, 'fullscreen_antiscreenshot_var'):
                self.main_window.fullscreen_antiscreenshot_var.set(fullscreen_antiscreenshot_enabled)
                # 如果启用，启动全屏反截屏保护
                if fullscreen_antiscreenshot_enabled:
                    self.main_window.after(250, self.main_window.toggle_fullscreen_antiscreenshot)
            
            # 恢复全屏反截屏间隔设置
            fullscreen_antiscreenshot_interval = config_data.get("fullscreen_antiscreenshot_interval", "0.1")
            if hasattr(self.main_window, 'fullscreen_interval_var'):
                self.main_window.fullscreen_interval_var.set(fullscreen_antiscreenshot_interval)
                
            # 恢复连续保护开关状态
            continuous_protection_enabled = config_data.get("continuous_protection_enabled", True)
            if hasattr(self.main_window, 'continuous_protection_var'):
                self.main_window.continuous_protection_var.set(continuous_protection_enabled)
            
            # 清空现有列表
            self.main_window.mode1_listbox.delete(0, "end")
            self.main_window.mode2_listbox.delete(0, "end")
            
            # 恢复模式一列表项
            for item in config_data.get("mode1_items", []):
                item_text = item["text"]
                is_enabled = item.get("enabled", True)
                
                # 根据状态添加适当的指示器
                if not is_enabled:
                    display_text = "● " + item_text
                    # 为禁用项设置状态属性
                    index = self.main_window.mode1_listbox.size()
                    setattr(self.main_window.mode1_listbox, f"item_{index}_status", "disabled")
                else:
                    display_text = item_text
                    index = self.main_window.mode1_listbox.size()
                    setattr(self.main_window.mode1_listbox, f"item_{index}_status", "enabled")
                    
                self.main_window.mode1_listbox.insert("end", display_text)
            
            # 恢复模式二列表项
            for item in config_data.get("mode2_items", []):
                item_text = item["text"]
                is_enabled = item.get("enabled", True)
                
                # 根据状态添加适当的指示器
                if not is_enabled:
                    display_text = "●" + item_text
                    # 为禁用项设置状态属性
                    index = self.main_window.mode2_listbox.size()
                    setattr(self.main_window.mode2_listbox, f"item_{index}_status", "disabled")
                else:
                    display_text = item_text
                    index = self.main_window.mode2_listbox.size()
                    setattr(self.main_window.mode2_listbox, f"item_{index}_status", "enabled")
                    
                self.main_window.mode2_listbox.insert("end", display_text)
            
            # 恢复当前模式
            self.main_window.current_mode = config_data.get("current_mode", 1)
            if self.main_window.current_mode == 1:
                self.main_window.toggle_button.configure(text="当前模式: 模式一")
            else:
                self.main_window.toggle_button.configure(text="当前模式: 模式二")
            
            # 应用反截屏保护（两个列表都需要应用）
            # 使用延迟确保UI已完全初始化
            self.main_window.after(100, lambda: self.main_window.apply_anti_screenshot_protection(self.main_window.mode1_listbox))
            self.main_window.after(150, lambda: self.main_window.apply_anti_screenshot_protection(self.main_window.mode2_listbox))
            
            self.main_window.status_label.configure(text="配置加载成功")
            
            # 延迟刷新列表，确保在应用反截屏保护之后
            self.main_window.after(200, self.main_window._delayed_list_refresh)
        except Exception as e:
            self.main_window.status_label.configure(text=f"加载配置失败: {str(e)}")
            import traceback
            traceback.print_exc()
            # 即使加载配置失败，也要刷新列表
            self.main_window.after(100, self.main_window._delayed_list_refresh)