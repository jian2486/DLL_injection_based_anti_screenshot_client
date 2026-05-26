import sys
import os
import psutil
import win32gui
import customtkinter as ctk
from tkinter import simpledialog
import tkinter as tk
import threading
import shutil

from dll_injector import DLLInjector
from ui_components import UIComponents
from data_manager import DataManager
from loader import ProcessLoader, WindowLoader


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 配置窗口
        self.title("反截屏管理程序")
        self.geometry("1000x700")

        # 在初始化时解压DLL文件（如果需要）
        self._extract_dll_files_if_needed()
        
        # 使用DLL注入方式替代原有的反截屏功能
        # 添加全屏反截屏状态跟踪
        self.fullscreen_anti_screenshot_enabled = False
        
        # 防止反截屏保护重复应用的标志
        self._anti_screenshot_applying = False
        
        # 创建UI组件管理器
        self.ui_components = UIComponents(self)
        
        # 创建数据管理器
        self.data_manager = DataManager(self)
        
        # 创建主布局
        self.ui_components.create_main_layout()
        
        # 初始化组件
        self.init_components()
        
        # 初始化加载器
        self.process_loader = None
        self.window_loader = None
        self.process_loading = False
        self.window_loading = False
        
        # 初始化定时器
        self.after(10000, self.auto_refresh)  # 每10秒自动刷新一次
        
        # 窗口完全初始化后刷新列表
        self.show_lists_refresh = True
        self.after(100, self.initial_refresh)
        
        # 移除白名单相关的变量初始化，因为我们已移除白名单功能
        
        # 添加开关节流控制
        self._last_toggle_time = 0
        self._pending_save = False
        
        # 添加设置界面开关节流控制
        self._last_setting_toggle_time = 0
        
    def _extract_dll_files_if_needed(self):
        """
        如果需要，将DLL文件从打包程序中解压到程序同目录
        """
        # 检查是否在PyInstaller打包环境中运行
        if not hasattr(sys, '_MEIPASS'):
            # 不在打包环境中，跳过解压
            return
            
        # 检查目标DLL目录是否已存在
        target_dll_dir = os.path.join(os.path.dirname(sys.executable), "dll")
        if os.path.exists(target_dll_dir):
            # 检查必要的子目录是否存在
            x86_dir = os.path.join(target_dll_dir, "x86")
            x64_dir = os.path.join(target_dll_dir, "x64")
            if os.path.exists(x86_dir) and os.path.exists(x64_dir):
                print("DLL架构目录已存在，跳过解压")
                return
        
        # 创建目标目录
        os.makedirs(target_dll_dir, exist_ok=True)
        
        # 从打包资源中复制DLL文件
        source_dll_dir = os.path.join(sys._MEIPASS, "dll")
        if os.path.exists(source_dll_dir):
            print(f"正在将DLL文件从 {source_dll_dir} 复制到 {target_dll_dir}")
            try:
                # 分别复制x86和x64目录
                source_x86_dir = os.path.join(source_dll_dir, "x86")
                source_x64_dir = os.path.join(source_dll_dir, "x64")
                target_x86_dir = os.path.join(target_dll_dir, "x86")
                target_x64_dir = os.path.join(target_dll_dir, "x64")
                
                if os.path.exists(source_x86_dir):
                    os.makedirs(target_x86_dir, exist_ok=True)
                    for file in os.listdir(source_x86_dir):
                        source_file = os.path.join(source_x86_dir, file)
                        target_file = os.path.join(target_x86_dir, file)
                        shutil.copy2(source_file, target_file)
                
                if os.path.exists(source_x64_dir):
                    os.makedirs(target_x64_dir, exist_ok=True)
                    for file in os.listdir(source_x64_dir):
                        source_file = os.path.join(source_x64_dir, file)
                        target_file = os.path.join(target_x64_dir, file)
                        shutil.copy2(source_file, target_file)
                
                print("DLL文件解压完成")
            except Exception as e:
                print(f"解压DLL文件时出错: {e}")
        else:
            print(f"源DLL目录不存在: {source_dll_dir}")
            
    def init_components(self):
        """初始化所有组件"""
        # 创建左侧模式一列表
        self.ui_components.create_mode1_section()
        
        # 创建左侧模式二列表
        self.ui_components.create_mode2_section()
        
        # 创建控制标签页
        self.ui_components.create_control_tab()
        
        # 创建设置标签页
        self.ui_components.create_settings_tab()
        
        # 创建关于标签页
        self.ui_components.create_about_tab()

    def save_data(self, show_status=True):
        """保存数据到配置文件"""
        self.data_manager.save_data(show_status)
        
    def load_data(self):
        """从配置文件加载数据"""
        self.data_manager.load_data()

    def _delayed_list_refresh(self):
        """延迟刷新列表"""
        self.refresh_processes_list()
        self.refresh_windows_list()
        self.show_lists_refresh = False
        
    def apply_anti_screenshot_protection(self, listbox):
        """应用反截屏保护"""
        try:
            # 检查是否正在执行，防止重复执行
            if self._anti_screenshot_applying:
                return  # 如果正在执行，则直接返回
            
            # 设置执行状态
            self._anti_screenshot_applying = True
            
            # 在后台线程中执行耗时操作
            threading.Thread(target=self._apply_anti_screenshot_protection_thread, args=(listbox,), daemon=True).start()
        except Exception as e:
            self.status_label.configure(text=f"应用反截屏保护时发生错误")
            import traceback
            traceback.print_exc()
            # 重置执行状态
            self._anti_screenshot_applying = False

    def _apply_anti_screenshot_protection_thread(self, listbox):
        """在后台线程中应用反截屏保护"""
        try:
            # 初始化DLL注入器
            dll_injector = DLLInjector()
            
            # 确定当前是哪个列表（模式一还是模式二）
            is_mode1 = (listbox == self.mode1_listbox)
            
            # 从列表项中提取进程信息
            process_items = []
            for i in range(listbox.size()):
                text = listbox.get(i)
                # 获取项目状态
                item_status = getattr(listbox, f'item_{i}_status', 'enabled')
                
                # 如果项目被禁用，跳过
                if item_status == 'disabled':
                    continue
                    
                # 处理状态指示器
                if text.startswith("●"):
                    text = text[2:]
                    
                # 处理两种格式:
                # 1. "进程名 (PID: 1234)" 格式
                # 2. "窗口标题 [进程名]" 格式
                # 3. 自定义添加的项目格式
                if " [" in text and text.endswith("]"):
                    # 窗口列表格式: "窗口标题 [进程名]" - 提取进程名
                    process_name = text.split(" [")[-1][:-1]
                    process_items.append({"name": process_name, "type": "window", "text": text})
                elif " (" in text and text.endswith(")"):
                    # 进程列表格式: "进程名 (PID: 1234)"
                    process_name = text.split(" (")[0]
                    # 提取PID
                    try:
                        pid_str = text.split("(PID: ")[1].split(")")[0]
                        pid = int(pid_str)
                        process_items.append({"name": process_name, "type": "process", "text": text, "pid": pid})
                    except (IndexError, ValueError):
                        # 如果无法提取PID，只使用进程名
                        process_items.append({"name": process_name, "type": "process", "text": text})
                else:
                    # 自定义添加的项目格式，尝试直接作为进程名处理
                    process_items.append({"name": text, "type": "custom", "text": text})
            
            # 如果启用了子进程注入，则收集所有子进程（仅对进程类型项目）
            all_process_items = process_items.copy()
            if hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
                for item in process_items:
                    if item["type"] == "process" and "pid" in item:  # 只对有PID的进程列表中的项目查找子进程
                        child_processes = self._get_child_processes_by_pid(item["pid"])
                        for child_process in child_processes:
                            all_process_items.append({"name": child_process["name"], "type": "child", "text": item["text"], "pid": child_process["pid"]})
            
            # 获取所有正在运行的进程
            import psutil
            injected_count = 0
            
            # 用于跟踪已处理的进程PID，避免重复注入
            processed_pids = set()
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name']
                    proc_pid = proc.info['pid']
                    
                    # 检查进程是否在需要保护的列表中
                    for item in all_process_items:
                        should_inject = False
                        
                        if item["type"] == "window":
                            # 窗口类型项目，检查进程名匹配
                            should_inject = (proc_name == item["name"])
                        elif item["type"] in ["process", "child"]:
                            # 进程或子进程类型项目
                            # 如果有PID信息，优先使用PID匹配
                            if "pid" in item:
                                should_inject = (proc_pid == item["pid"])
                            else:
                                should_inject = (proc_name == item["name"])
                        elif item["type"] == "custom":
                            # 自定义类型项目
                            should_inject = (proc_name == item["name"])
                        
                        if should_inject and proc_pid not in processed_pids:
                            # 根据模式选择不同的DLL进行注入
                            if is_mode1:
                                # 模式一使用AffinityTrans.dll
                                success = dll_injector.inject_affinity_trans_dll(proc_pid)
                            else:
                                # 模式二使用AffinityHide.dll
                                success = dll_injector.inject_affinity_hide_dll(proc_pid)
                                
                            if success:
                                injected_count += 1
                                processed_pids.add(proc_pid)
                            break  # 找到匹配项后跳出循环
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # 忽略无法访问的进程
                    pass
            
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(
                text=f"已尝试向 {injected_count} 个进程注入{'AffinityTrans' if is_mode1 else 'AffinityHide'}.dll"))
        except Exception as e:
            # 在出现错误时显示更明显的提示（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"应用反截屏保护时发生错误，请查看日志"))
            import traceback
            traceback.print_exc()
        finally:
            # 重置执行状态
            self._anti_screenshot_applying = False
        
    def _get_child_processes_by_pid(self, parent_pid):
        """
        获取指定进程的所有子进程信息
        
        Args:
            parent_pid (int): 父进程PID
            
        Returns:
            list: 子进程信息列表 [{"name": str, "pid": int}, ...]
        """
        child_processes = []
        try:
            import psutil
            
            # 查找所有子进程
            for child_proc in psutil.process_iter(['pid', 'name', 'ppid']):
                try:
                    if child_proc.info['ppid'] == parent_pid:
                        child_processes.append({
                            "name": child_proc.info['name'],
                            "pid": child_proc.info['pid']
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                    
        except Exception as e:
            # 避免在获取子进程时出现错误影响主流程
            pass
            
        return child_processes

    def _clear_list_thread(self, process_names, mode_name):
        """在后台线程中为进程取消反截屏保护"""
        try:
            # 如果启用了子进程注入，则也包括子进程（仅对进程项目）
            all_process_names = process_names.copy()
            if hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
                # 只处理进程项目，不处理窗口项目
                for process_name in process_names:
                    # 检查是否为进程项目格式（窗口项目格式：包含 [ 和 ] 但不包含 PID 信息）
                    if not (" [" in process_name and process_name.endswith("]")):
                        # 是进程项目，查找子进程
                        child_processes = self._get_child_processes(process_name)
                        all_process_names.extend(child_processes)
            
            # 去重
            all_process_names = list(set(all_process_names))
            
            # 初始化DLL注入器
            dll_injector = DLLInjector()
            
            # 获取所有正在运行的进程
            import psutil
            uninjected_count = 0
            processed_pids = set()  # 防止重复注入
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name']
                    proc_pid = proc.info['pid']
                    
                    # 检查进程是否在需要取消保护的列表中
                    if proc_name in all_process_names and proc_pid not in processed_pids:
                        # 注入AffinityUnhide.dll取消反截屏保护
                        success = dll_injector.inject_affinity_unhide_dll(proc_pid)
                        if success:
                            uninjected_count += 1
                            processed_pids.add(proc_pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # 忽略无法访问的进程
                    pass
                    
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"已尝试向 {uninjected_count} 个进程注入AffinityUnhide.dll取消反截屏保护"))
        except Exception as e:
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"为进程取消反截屏保护时出错，请查看日志"))
            print(f"DEBUG: 为进程取消反截屏保护时出错: {e}")
        
    def _remove_selected_item_thread(self, removed_process_names, mode_name):
        """在后台线程中为移除的进程取消反截屏保护"""
        try:
            # 如果启用了子进程注入，则也包括子进程（仅对进程项目）
            all_process_names = removed_process_names.copy()
            if hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
                # 只处理进程项目，不处理窗口项目
                for process_name in removed_process_names:
                    # 检查是否为进程项目格式（窗口项目格式：包含 [ 和 ] 但不包含 PID 信息）
                    if not (" [" in process_name and process_name.endswith("]")):
                        # 是进程项目，查找子进程
                        child_processes = self._get_child_processes(process_name)
                        all_process_names.extend(child_processes)
            
            # 去重
            all_process_names = list(set(all_process_names))
            
            # 初始化DLL注入器
            dll_injector = DLLInjector()
            
            # 获取所有正在运行的进程
            import psutil
            uninjected_count = 0
            processed_pids = set()  # 防止重复注入
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name']
                    proc_pid = proc.info['pid']
                    
                    # 检查进程是否在需要取消保护的列表中
                    if proc_name in all_process_names and proc_pid not in processed_pids:
                        # 注入AffinityUnhide.dll取消反截屏保护
                        success = dll_injector.inject_affinity_unhide_dll(proc_pid)
                        if success:
                            uninjected_count += 1
                            processed_pids.add(proc_pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # 忽略无法访问的进程
                    pass
                    
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"已从 {mode_name} 中移除选中的项目，并尝试向 {uninjected_count} 个进程注入AffinityUnhide.dll"))
        except Exception as e:
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"为进程取消反截屏保护时出错，请查看日志"))
            print(f"DEBUG: 为进程取消反截屏保护时出错: {e}")
        
    def add_custom_item(self, listbox, mode_name):
        """添加自定义项目"""
        item_text = simpledialog.askstring("添加项目", "请输入项目名称:")
        if item_text:
            # 检查是否已存在相同项目（去除状态指示器前缀后比较）
            exists = False
            for i in range(listbox.size()):
                existing_item = listbox.get(i)
                # 去除状态指示器前缀进行比较
                clean_existing = existing_item[2:] if existing_item.startswith("●") else existing_item

                if clean_existing == item_text:
                    exists = True
                    break
            
            if exists:
                self.status_label.configure(text=f"项目 '{item_text}' 已存在于 {mode_name} 中")
            else:
                # 检查该项目是否已经存在于另一个列表中
                other_listbox = self.mode2_listbox if listbox == self.mode1_listbox else self.mode1_listbox
                other_mode_name = "模式二" if mode_name == "模式一" else "模式一"
                already_exists_in_other = False
                
                for i in range(other_listbox.size()):
                    existing_item = other_listbox.get(i)
                    clean_existing = existing_item[2:] if existing_item.startswith("●") else existing_item
                    if clean_existing == item_text:
                        already_exists_in_other = True
                        break
                
                if already_exists_in_other:
                    self.status_label.configure(text=f"项目 '{item_text}' 已存在于 {other_mode_name} 中，无法同时添加到两个列表")
                else:
                    listbox.insert("end", item_text)
                    # 为新项目设置默认状态
                    index = listbox.size() - 1
                    setattr(listbox, f'item_{index}_status', 'enabled')
                    self.status_label.configure(text=f"已向 {mode_name} 添加项目: {item_text}")
                    # 添加项目后应用反截屏保护（在后台线程中执行）
                    threading.Thread(target=self._apply_anti_screenshot_protection_thread, args=(listbox,), daemon=True).start()
                    # 自动保存配置
                    self.save_data(show_status=False)
            
    def clear_list(self, listbox, mode_name):
        """清空列表"""
        # 在清空列表前，先为列表中的所有进程取消反截屏保护
        process_names = []
        for i in range(listbox.size()):
            text = listbox.get(i)
            # 获取项目状态
            item_status = getattr(listbox, f'item_{i}_status', 'enabled')
            
            # 只处理启用状态的项目
            if item_status != 'disabled':
                # 处理状态指示器
                if text.startswith("●"):
                    text = text[2:]
                    
                # 处理多种格式:
                if " [" in text and text.endswith("]"):
                    # 窗口列表格式: "窗口标题 [进程名]"
                    process_name = text.split(" [")[-1][:-1]
                    process_names.append(process_name)
                elif " (" in text and text.endswith(")"):
                    # 进程列表格式: "进程名 (PID: 1234)"
                    process_name = text.split(" (")[0]
                    process_names.append(process_name)
                else:
                    # 自定义添加的项目格式，直接作为进程名处理
                    process_names.append(text)
                
        # 为这些进程移除反截屏保护（注入AffinityUnhide.dll）
        if process_names:
            # 在后台线程中执行耗时操作
            threading.Thread(target=self._clear_list_thread, args=(process_names, mode_name), daemon=True).start()
        else:
            self.status_label.configure(text=f"已清空 {mode_name}")
            
        # 清空列表
        listbox.delete(0, "end")
        # 自动保存配置
        self.save_data(show_status=False)
        
    def remove_selected_item(self, listbox, mode_name):
        """从列表中移除选中的项目"""
        selected_indices = listbox.curselection()
        if not selected_indices:
            return
            
        # 收集将要移除的进程名称
        removed_process_names = []
        for index in reversed(selected_indices):  # 反向遍历以避免索引问题
            text = listbox.get(index)
            # 获取项目状态
            item_status = getattr(listbox, f'item_{index}_status', 'enabled')
            
            # 只处理启用状态的项目
            if item_status != 'disabled':
                # 处理状态指示器
                if text.startswith("●"):
                    text = text[2:]
                    
                # 处理两种格式:
                if " [" in text and text.endswith("]"):
                    # 窗口列表格式: "窗口标题 [进程名]"
                    process_name = text.split(" [")[-1][:-1]
                    removed_process_names.append(process_name)
                elif " (" in text and text.endswith(")"):
                    # 进程列表格式: "进程名 (PID: 1234)"
                    process_name = text.split(" (")[0]
                    removed_process_names.append(process_name)
                
        # 从列表中移除项目（反向删除以避免索引问题）
        for index in reversed(selected_indices):
            listbox.delete(index)
            
        # 为这些进程移除反截屏保护（注入AffinityUnhide.dll）
        if removed_process_names:
            # 在后台线程中执行耗时操作
            threading.Thread(target=self._remove_selected_item_thread, args=(removed_process_names, mode_name), daemon=True).start()
        else:
            self.status_label.configure(text=f"已从 {mode_name} 中移除选中的项目")
        # 自动保存配置
        self.save_data(show_status=False)
        
    def show_mode_list_context_menu(self, event, listbox, mode_name):
        """显示模式列表右键菜单"""
        # 获取选中项
        selection = listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        
        # 创建右键菜单
        context_menu = tk.Menu(self, tearoff=0)
        
        # 添加开关选项
        context_menu.add_command(
            label="开关", 
            command=lambda: self.toggle_item_status(listbox, index, mode_name)
        )
        
        # 添加转移到另一模式选项
        context_menu.add_command(
            label="转移到另一模式",
            command=lambda: self.switch_item_mode(listbox, index)
        )
        
        # 添加检查状态选项
        context_menu.add_command(
            label="检查状态",
            command=lambda: self.check_item_status(listbox, index)
        )
        
        # 显示菜单
        context_menu.post(event.x_root, event.y_root)
        
    def check_item_status(self, listbox, index):
        """检查项目状态"""
        # 获取项目文本
        item_text = listbox.get(index)
        
        # 处理状态指示器
        if item_text.startswith("●"):
            clean_text = item_text[2:]
        else:
            clean_text = item_text
            
        # 从项目文本中提取进程名
        process_name = None
        if " [" in clean_text and clean_text.endswith("]"):
            # 窗口列表格式: "窗口标题 [进程名]"
            process_name = clean_text.split(" [")[-1][:-1]
        elif " (" in clean_text and clean_text.endswith(")"):
            # 进程列表格式: "进程名 (PID: 1234)"
            process_name = clean_text.split(" (")[0]
        else:
            # 自定义添加的项目格式，直接作为进程名处理
            process_name = clean_text
            
        if not process_name:
            self.status_label.configure(text="无法提取进程名")
            return
            
        # 查找进程ID
        import psutil
        target_pid = None
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] == process_name:
                    target_pid = proc.info['pid']
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        if not target_pid:
            self.status_label.configure(text=f"未找到进程: {process_name}")
            return
            
        # 注入状态检查DLL
        dll_injector = DLLInjector()
        success = dll_injector.inject_affinity_status_dll(target_pid)
        if success:
            self.status_label.configure(text=f"已向进程 {process_name} 注入状态检查DLL")
            # 这里应该读取DLL返回的状态信息并更新UI
        else:
            self.status_label.configure(text=f"向进程 {process_name} 注入状态检查DLL失败")
            
    def switch_item_mode(self, source_listbox, index):
        """将项目转移到另一模式"""
        # 获取项目文本
        item_text = source_listbox.get(index)
        # 获取项目状态
        item_status = getattr(source_listbox, f'item_{index}_status', 'enabled')
        
        # 确定源列表和目标列表
        if source_listbox == self.mode1_listbox:
            target_listbox = self.mode2_listbox
            source_name = "模式一"
            target_name = "模式二"
            # 源模式是模式一，目标模式是模式二
            from_mode = "mode1"
            to_mode = "mode2"
        else:
            target_listbox = self.mode1_listbox
            source_name = "模式二"
            target_name = "模式一"
            # 源模式是模式二，目标模式是模式一
            from_mode = "mode2"
            to_mode = "mode1"
            
        # 检查目标列表中是否已存在相同项目
        exists = False
        for i in range(target_listbox.size()):
            existing_item = target_listbox.get(i)
            # 去除状态指示器前缀进行比较
            clean_existing = existing_item[2:] if existing_item.startswith("●") else existing_item
            clean_item_text = item_text[2:] if item_text.startswith("●") else item_text
            if clean_existing == clean_item_text:
                exists = True
                break
                
        if exists:
            clean_item_text = item_text[2:] if item_text.startswith("●") else item_text
            self.status_label.configure(text=f"项目 '{clean_item_text}' 已存在于 {target_name} 中")
            return
            
        # 从源列表移除项目
        source_listbox.delete(index)
        
        # 添加到目标列表
        target_index = target_listbox.size()
        target_listbox.insert(target_index, item_text)
        # 保持项目状态
        setattr(target_listbox, f'item_{target_index}_status', item_status)
        
        # 更新状态栏
        clean_text = item_text[2:] if item_text.startswith("●") else item_text
        self.status_label.configure(text=f"已将 '{clean_text}' 从 {source_name} 转移到 {target_name}")
        
        # 如果项目是启用状态，则需要先取消反截屏保护，然后重新应用新模式的反截屏保护
        if item_status != 'disabled':
            # 在后台线程中执行耗时操作
            threading.Thread(target=self._switch_item_mode_thread, args=(clean_text, from_mode, to_mode), daemon=True).start()
        
        # 自动保存配置
        self.save_data(show_status=False)
        
    def _switch_item_mode_thread(self, clean_text, from_mode, to_mode):
        """在后台线程中执行模式切换的DLL操作"""
        # 提取进程信息
        process_name = None
        is_window_item = False
        pid = None
        if " [" in clean_text and clean_text.endswith("]"):
            # 窗口列表格式: "窗口标题 [进程名]"
            process_name = clean_text.split(" [")[-1][:-1]
            is_window_item = True
        elif " (" in clean_text and clean_text.endswith(")"):
            # 进程列表格式: "进程名 (PID: 1234)"
            process_name = clean_text.split(" (")[0]
            # 提取PID
            try:
                pid_str = clean_text.split("(PID: ")[1].split(")")[0]
                pid = int(pid_str)
            except (IndexError, ValueError):
                pass
        else:
            # 自定义添加的项目格式，直接作为进程名处理
            process_name = clean_text
            
        if process_name:
            # 查找进程ID
            import psutil
            target_pids = []
            if pid is not None:
                # 如果有明确的PID，只针对该PID
                target_pids = [pid]
            elif is_window_item:
                # 对于窗口项目，我们需要更精确地匹配
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] == process_name:
                            target_pids.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            else:
                # 对于进程项目，查找所有同名进程
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] == process_name:
                            target_pids.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                    
            if target_pids:
                # 先注入AffinityUnhide.dll取消反截屏保护
                dll_injector = DLLInjector()
                unhide_success_count = 0
                processed_pids = set()  # 防止重复注入
                
                for target_pid in target_pids:
                    if target_pid not in processed_pids:
                        unhide_success = dll_injector.inject_affinity_unhide_dll(target_pid)
                        if unhide_success:
                            unhide_success_count += 1
                            processed_pids.add(target_pid)
                
                if unhide_success_count > 0:
                    # 更新状态（在主线程中执行）
                    self.after(0, lambda: self.status_label.configure(text=f"已向 {unhide_success_count} 个进程注入AffinityUnhide.dll取消反截屏保护"))
                
                # 然后注入新模式对应的DLL
                success_count = 0
                processed_pids = set()  # 重新初始化防止重复注入
                
                if to_mode == "mode1":
                    # 转移到模式一，使用AffinityTrans.dll
                    for target_pid in target_pids:
                        if target_pid not in processed_pids:
                            success = dll_injector.inject_affinity_trans_dll(target_pid)
                            if success:
                                success_count += 1
                                processed_pids.add(target_pid)
                    if success_count > 0:
                        # 更新状态（在主线程中执行）
                        self.after(0, lambda: self.status_label.configure(text=f"已将 '{clean_text}' 转移并注入AffinityTrans.dll到 {success_count} 个进程"))
                else:
                    # 转移到模式二，使用AffinityHide.dll
                    for target_pid in target_pids:
                        if target_pid not in processed_pids:
                            success = dll_injector.inject_affinity_hide_dll(target_pid)
                            if success:
                                success_count += 1
                                processed_pids.add(target_pid)
                    if success_count > 0:
                        # 更新状态（在主线程中执行）
                        self.after(0, lambda: self.status_label.configure(text=f"已将 '{clean_text}' 转移并注入AffinityHide.dll到 {success_count} 个进程"))
                
                # 如果启用了子进程注入，则也对子进程执行相同操作（仅对进程项目）
                if not is_window_item and hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
                    child_processes = self._get_child_processes(process_name)
                    processed_pids = set()  # 防止重复注入
                    
                    for child_process_name in child_processes:
                        for child_proc in psutil.process_iter(['pid', 'name']):
                            try:
                                if child_proc.info['name'] == child_process_name and child_proc.info['pid'] not in processed_pids:
                                    child_pid = child_proc.info['pid']
                                    
                                    # 先取消子进程的反截屏保护
                                    dll_injector.inject_affinity_unhide_dll(child_pid)
                                    
                                    # 然后根据新模式注入对应的DLL
                                    if to_mode == "mode1":
                                        dll_injector.inject_affinity_trans_dll(child_pid)
                                    else:
                                        dll_injector.inject_affinity_hide_dll(child_pid)
                                        
                                    processed_pids.add(child_pid)
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                                pass

    def toggle_item_status(self, listbox, index, mode_name):
        """切换项目状态（开启/关闭）"""
        # 获取项目文本
        item_text = listbox.get(index)
        
        # 检查项目当前是否为开启状态（是否有状态指示器）
        is_enabled = not item_text.startswith("●") or (item_text.startswith("●") and getattr(listbox, f'item_{index}_status', 'enabled') == 'enabled')

        if item_text.startswith("●"):
            # 移除现有的状态指示器
            clean_text = item_text[2:]
        else:
            clean_text = item_text
            
        listbox.delete(index)
            
        if is_enabled:
            # 切换到关闭状态（红点）
            new_text = "● " + clean_text
            listbox.insert(index, new_text)
            setattr(listbox, f'item_{index}_status', 'disabled')
            self.status_label.configure(text=f"'{clean_text}' 在 {mode_name} 中已关闭")
            
            # 在后台线程中取消进程的反截屏保护
            threading.Thread(target=self._unhide_process_thread, args=(clean_text,), daemon=True).start()
        else:
            # 切换到开启状态（绿点）
            new_text = "● " + clean_text
            listbox.insert(index, new_text)
            setattr(listbox, f'item_{index}_status', 'enabled')
            self.status_label.configure(text=f"'{clean_text}' 在 {mode_name} 中已开启")
            
            # 在后台线程中重新应用反截屏保护
            threading.Thread(target=self._rehide_process_thread, args=(clean_text, listbox), daemon=True).start()
            
        # 重新应用反截屏保护
        if listbox == self.mode1_listbox:
            self.apply_anti_screenshot_protection(self.mode1_listbox)
        elif listbox == self.mode2_listbox:
            self.apply_anti_screenshot_protection(self.mode2_listbox)
        # 自动保存配置
        self.save_data(show_status=False)
        
    def _unhide_process_thread(self, process_text):
        """在后台线程中取消进程的反截屏保护"""
        # 提取进程信息
        process_name = None
        is_window_item = False
        pid = None
        if " [" in process_text and process_text.endswith("]"):
            # 窗口列表格式: "窗口标题 [进程名]"
            process_name = process_text.split(" [")[-1][:-1]
            is_window_item = True
        elif " (" in process_text and process_text.endswith(")"):
            # 进程列表格式: "进程名 (PID: 1234)"
            process_name = process_text.split(" (")[0]
            # 提取PID
            try:
                pid_str = process_text.split("(PID: ")[1].split(")")[0]
                pid = int(pid_str)
            except (IndexError, ValueError):
                pass
        else:
            # 自定义添加的项目格式，直接作为进程名处理
            process_name = process_text
            
        if not process_name:
            return
            
        # 查找进程ID
        import psutil
        target_pids = []
        if pid is not None:
            # 如果有明确的PID，只针对该PID
            target_pids = [pid]
        else:
            # 对于窗口项目，仍然查找所有同名进程（在实际应用中可以优化）
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] == process_name:
                        target_pids.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                
        if not target_pids:
            return
            
        # 注入AffinityUnhide.dll取消反截屏保护
        dll_injector = DLLInjector()
        success_count = 0
        processed_pids = set()  # 防止重复注入
        
        for target_pid in target_pids:
            if target_pid not in processed_pids:
                success = dll_injector.inject_affinity_unhide_dll(target_pid)
                if success:
                    success_count += 1
                    processed_pids.add(target_pid)
        
        if success_count > 0:
            # 更新状态（在主线程中执行）
            self.after(0, lambda: self.status_label.configure(text=f"已向 {success_count} 个进程注入AffinityUnhide.dll取消反截屏保护"))
            
        # 如果启用了子进程注入，且不是窗口项目，则也对子进程执行相同操作
        if not is_window_item and hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
            child_processes = self._get_child_processes(process_name)
            processed_pids = set()  # 防止重复注入
            
            for child_process_name in child_processes:
                for child_proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if child_proc.info['name'] == child_process_name and child_proc.info['pid'] not in processed_pids:
                            child_pid = child_proc.info['pid']
                            dll_injector.inject_affinity_unhide_dll(child_pid)
                            processed_pids.add(child_pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

    def _rehide_process_thread(self, process_text, listbox):
        """在后台线程中重新应用进程的反截屏保护"""
        # 提取进程信息
        process_name = None
        is_window_item = False
        pid = None
        if " [" in process_text and process_text.endswith("]"):
            # 窗口列表格式: "窗口标题 [进程名]"
            process_name = process_text.split(" [")[-1][:-1]
            is_window_item = True
        elif " (" in process_text and process_text.endswith(")"):
            # 进程列表格式: "进程名 (PID: 1234)"
            process_name = process_text.split(" (")[0]
            # 提取PID
            try:
                pid_str = process_text.split("(PID: ")[1].split(")")[0]
                pid = int(pid_str)
            except (IndexError, ValueError):
                pass
        else:
            # 自定义添加的项目格式，直接作为进程名处理
            process_name = process_text
            
        if not process_name:
            return
            
        # 查找进程ID
        import psutil
        target_pids = []
        if pid is not None:
            # 如果有明确的PID，只针对该PID
            target_pids = [pid]
        else:
            # 对于窗口项目，仍然查找所有同名进程（在实际应用中可以优化）
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] == process_name:
                        target_pids.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                
        if not target_pids:
            return
            
        # 确定当前是哪个列表（模式一还是模式二）
        is_mode1 = (listbox == self.mode1_listbox)
            
        # 注入对应的DLL重新应用反截屏保护
        dll_injector = DLLInjector()
        success_count = 0
        processed_pids = set()  # 防止重复注入
        
        if is_mode1:
            # 模式一使用AffinityTrans.dll
            for target_pid in target_pids:
                if target_pid not in processed_pids:
                    success = dll_injector.inject_affinity_trans_dll(target_pid)
                    if success:
                        success_count += 1
                        processed_pids.add(target_pid)
            if success_count > 0:
                # 更新状态（在主线程中执行）
                self.after(0, lambda: self.status_label.configure(text=f"已向 {success_count} 个进程注入AffinityTrans.dll重新应用反截屏保护"))
        else:
            # 模式二使用AffinityHide.dll
            for target_pid in target_pids:
                if target_pid not in processed_pids:
                    success = dll_injector.inject_affinity_hide_dll(target_pid)
                    if success:
                        success_count += 1
                        processed_pids.add(target_pid)
            if success_count > 0:
                # 更新状态（在主线程中执行）
                self.after(0, lambda: self.status_label.configure(text=f"已向 {success_count} 个进程注入AffinityHide.dll重新应用反截屏保护"))
                
        # 如果启用了子进程注入，且不是窗口项目，则也对子进程执行相同操作
        if not is_window_item and hasattr(self, 'child_process_injection_var') and self.child_process_injection_var.get():
            child_processes = self._get_child_processes(process_name)
            processed_pids = set()  # 防止重复注入
            
            for child_process_name in child_processes:
                for child_proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if child_proc.info['name'] == child_process_name and child_proc.info['pid'] not in processed_pids:
                            child_pid = child_proc.info['pid']
                            
                            # 根据模式注入对应的DLL
                            if is_mode1:
                                dll_injector.inject_affinity_trans_dll(child_pid)
                            else:
                                dll_injector.inject_affinity_hide_dll(child_pid)
                                
                            processed_pids.add(child_pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

    def add_to_current_mode_from_list(self, listbox):
        """将列表中的项目添加到当前模式"""
        selected_indices = listbox.curselection()
        added_count = 0
        
        for index in selected_indices:
            item_text = listbox.get(index)
            
            # 确定目标列表框
            if self.current_mode == 1:
                target_listbox = self.mode1_listbox
                target_name = "模式一"
            elif self.current_mode == 2:
                target_listbox = self.mode2_listbox
                target_name = "模式二"
            
            # 检查是否已存在相同项目（去除状态指示器前缀后比较）
            exists = False
            for i in range(target_listbox.size()):
                existing_item = target_listbox.get(i)
                # 去除状态指示器前缀进行比较
                clean_existing = existing_item[2:] if existing_item.startswith("● ") else existing_item
                if clean_existing == item_text:
                    exists = True
                    break
            
            # 如果不存在，则检查是否已经在另一个列表中
            if not exists:
                # 确定另一个列表框
                other_listbox = self.mode2_listbox if target_listbox == self.mode1_listbox else self.mode1_listbox
                other_mode_name = "模式二" if target_name == "模式一" else "模式一"
                already_exists_in_other = False
                
                for i in range(other_listbox.size()):
                    existing_item = other_listbox.get(i)
                    clean_existing = existing_item[2:] if existing_item.startswith("● ") else existing_item
                    if clean_existing == item_text:
                        already_exists_in_other = True
                        break
                        
                if already_exists_in_other:
                    self.status_label.configure(text=f"项目 '{item_text}' 已存在于 {other_mode_name} 中，无法同时添加到两个列表")
                    continue  # 跳过这个项目
            
            # 如果不存在，则添加
            if not exists:
                target_index = target_listbox.size()
                target_listbox.insert(target_index, item_text)
                # 设置默认状态为启用
                setattr(target_listbox, f'item_{target_index}_status', 'enabled')
                added_count += 1
                
        if added_count > 0:
            # 在后台线程中应用反截屏保护
            threading.Thread(target=self._apply_anti_screenshot_protection_thread, args=(target_listbox,), daemon=True).start()
            # 自动保存配置
            self.save_data(show_status=False)
            self.status_label.configure(text=f"已向 {target_name} 添加 {added_count} 个项目")
        else:
            self.status_label.configure(text="所选项目已存在于当前模式中或已在另一模式中")
            
    # 已移除白名单功能
    pass

    def toggle_mode(self):
        """切换模式"""
        if self.current_mode == 1:
            self.current_mode = 2
            self.toggle_button.configure(text="当前模式: 模式二")
        else:
            self.current_mode = 1
            self.toggle_button.configure(text="当前模式: 模式一")
        # 自动保存配置
        self.save_data(show_status=False)

    def change_theme(self):
        """改变主题"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        # 更改主题
        theme = self.theme_var.get()
        if theme == "Dark":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")
            
        # 自动保存配置
        self._schedule_auto_save()
        
    def is_auto_start_enabled(self):
        """检查开机自启动是否已启用"""
        try:
            import winreg
            # 打开注册表项
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            )
            # 尝试读取值
            winreg.QueryValueEx(key, "AntiScreenshotManager")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            # 键不存在，说明未启用开机自启动
            return False
        except Exception as e:
            # 其他错误
            print(f"检查开机自启动状态时出错: {e}")
            return False

    def toggle_auto_start(self):
        """切换开机自启动功能的启用状态"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            # 根据开关状态启用或禁用开机自启动
            if self.auto_start_var.get():
                self.enable_auto_start()
            else:
                self.disable_auto_start()
                
            # 自动保存配置
            self._schedule_auto_save()
        except Exception as e:
            self.status_label.configure(text=f"切换开机自启动时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def refresh_processes_list(self):
        """刷新进程列表"""
        if self.process_loading:
            return
            
        self.process_loading = True
        self.progress_bar.pack(side="right", padx=5, pady=5)  # 显示进度条
        self.status_label.configure(text="正在获取进程列表...")
        self.refresh_processes_btn.configure(state="disabled")
        
        # 创建并启动进程加载线程
        def load_processes():
            loader = ProcessLoader(self.on_processes_loaded)
            loader.run()
            
        thread = threading.Thread(target=load_processes)
        thread.daemon = True
        thread.start()
        
    def on_processes_loaded(self, processes):
        """进程加载完成回调"""
        # 在主线程中更新UI
        self.after(0, lambda: self._update_process_list(processes))
        
    def _update_process_list(self, processes):
        self.process_listbox.delete(0, "end")
        
        # 逐个添加进程到列表（懒加载）
        for display_text, process_name in processes:
            self.process_listbox.insert("end", display_text)
            
        self.status_label.configure(text=f"已刷新进程列表，共找到 {len(processes)} 个不同的进程")
        self.progress_bar.pack_forget()  # 隐藏进度条
        self.refresh_processes_btn.configure(state="normal")
        self.process_loading = False
        
    def refresh_windows_list(self):
        """刷新窗口列表"""
        if self.window_loading:
            return
            
        self.window_loading = True
        self.progress_bar.pack(side="right", padx=5, pady=5)  # 显示进度条
        self.status_label.configure(text="正在获取窗口列表...")
        self.refresh_windows_btn.configure(state="disabled")
        
        # 创建并启动窗口加载线程
        def load_windows():
            loader = WindowLoader(self.on_windows_loaded)
            loader.run()
            
        thread = threading.Thread(target=load_windows)
        thread.daemon = True
        thread.start()
        
    def on_windows_loaded(self, windows):
        """窗口加载完成回调"""
        # 在主线程中更新UI
        self.after(0, lambda: self._update_window_list(windows))
        
    def _update_window_list(self, windows):
        self.window_listbox.delete(0, "end")
        
        # 逐个添加窗口到列表（懒加载）
        for display_text, process_name in windows:
            self.window_listbox.insert("end", display_text)
            
        self.status_label.configure(text=f"已刷新窗口列表，共找到 {len(windows)} 个不同的窗口")
        self.progress_bar.pack_forget()  # 隐藏进度条
        self.refresh_windows_btn.configure(state="normal")
        self.window_loading = False
        
    def refresh_current_tab(self):
        """刷新当前标签页"""
        current_tab = self.tab_view.get()
        if current_tab == "控制":
            self.refresh_processes_list()
            self.refresh_windows_list()
        elif current_tab == "设置":
            pass
        elif current_tab == "关于":
            pass
            
    def auto_refresh(self):
        """自动刷新"""
        if self.show_lists_refresh:
            self.refresh_processes_list()
            self.refresh_windows_list()
            self.show_lists_refresh = False
            
        # 安排下一次自动刷新
        self.after(10000, self.auto_refresh)
        
    def initial_refresh(self):
        """初始化刷新"""
        # 尝试加载配置文件
        self.load_data()
        
        # 刷新进程和窗口列表
        self.refresh_processes_list()
        self.refresh_windows_list()
        self.show_lists_refresh = False



    def edit_mode(self, listbox, mode_name):
        """编辑模式"""
        # 使用CustomTkinter的输入对话框替换Qt的QInputDialog
        new_mode_name = simpledialog.askstring("编辑模式", "请输入新的模式名称:", initialvalue=mode_name)
        if new_mode_name:
            # 注意：在tk.Listbox中，我们需要先删除再插入来实现更新
            current_index = listbox.curselection()[0] if listbox.curselection() else 0
            listbox.delete(current_index)
            listbox.insert(current_index, new_mode_name)
            self.update_mode_list()

    def delete_mode(self, listbox, mode_name):
        """删除模式"""
        listbox.takeItem(listbox.currentRow())
        self.update_mode_list()

    def update_mode_list(self):
        """更新模式列表"""
        self.mode_list.clear()
        for i in range(self.ui_components.mode_listbox.size()):
            mode_name = self.ui_components.mode_listbox.get(i)
            self.mode_list.append(mode_name)

    
    def temporarily_disable_protection(self, process_name):
        """临时禁用指定进程的反截屏保护"""
        # 查找进程ID
        import psutil
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] == process_name:
                    target_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if not target_pids:
            return
        
        # 保存当前保护状态
        self.whitelist_protection_states[process_name] = []
        
        # 注入取消反截屏保护的DLL
        dll_injector = DLLInjector()
        success_count = 0
        for pid in target_pids:
            # 记录当前保护状态
            self.whitelist_protection_states[process_name].append({
                'pid': pid,
                'mode': self.get_process_protection_mode(pid)  # 需要实现这个方法
            })
            
            # 注入取消保护的DLL
            success = dll_injector.inject_affinity_unhide_dll(pid)
            if success:
                success_count += 1
        
    def show_mode_list_context_menu(self, event, listbox, mode_name):
        """显示模式列表右键菜单"""
        # 对于控制列表（窗口列表和进程列表），即使没有选中项目也显示菜单
        if listbox in [self.window_listbox, self.process_listbox]:
            selection = listbox.curselection()
            # 创建右键菜单
            context_menu = tk.Menu(self, tearoff=0)
            
            # 如果有选中项，添加原有的操作选项
            if selection:
                index = selection[0]
                # 添加开关选项
                context_menu.add_command(
                    label="开关", 
                    command=lambda: self.toggle_item_status(listbox, index, mode_name)
                )
                
                # 添加转移到另一模式选项
                context_menu.add_command(
                    label="转移到另一模式",
                    command=lambda: self.switch_item_mode(listbox, index)
                )
                
                # 添加检查状态选项
                context_menu.add_command(
                    label="检查状态",
                    command=lambda: self.check_item_status(listbox, index)
                )
            
            # 添加分隔线
            context_menu.add_separator()
            
            # 添加批量添加到两个模式的选项（移除白名单相关选项）
            context_menu.add_command(
                label="添加到模式一",
                command=lambda: self.add_selected_to_mode(self.mode1_listbox, "模式一")
            )
            
            context_menu.add_command(
                label="添加到模式二",
                command=lambda: self.add_selected_to_mode(self.mode2_listbox, "模式二")
            )
            
            # 显示菜单
            context_menu.post(event.x_root, event.y_root)
        else:
            # 对于其他列表（模式一和模式二），保持原有的行为
            # 获取选中项
            selection = listbox.curselection()
            if not selection:
                return
                
            index = selection[0]
            
            # 创建右键菜单
            context_menu = tk.Menu(self, tearoff=0)
            
            # 添加开关选项
            context_menu.add_command(
                label="开关", 
                command=lambda: self.toggle_item_status(listbox, index, mode_name)
            )
            
            # 添加转移到另一模式选项
            context_menu.add_command(
                label="转移到另一模式",
                command=lambda: self.switch_item_mode(listbox, index)
            )
            
            # 添加检查状态选项
            context_menu.add_command(
                label="检查状态",
                command=lambda: self.check_item_status(listbox, index)
            )
            
            # 显示菜单
            context_menu.post(event.x_root, event.y_root)
        
    def add_selected_to_mode(self, target_listbox, mode_name):
        """将选中的项目添加到指定模式"""
        # 确定源列表框
        focused_widget = self.focus_get()
        if focused_widget == self.window_listbox:
            source_listbox = self.window_listbox
        elif focused_widget == self.process_listbox:
            source_listbox = self.process_listbox
        else:
            return
            
        # 获取选中的项目
        selected_indices = source_listbox.curselection()
        if not selected_indices:
            return
            
        added_count = 0
        for index in selected_indices:
            item_text = source_listbox.get(index)
            
            # 检查是否已存在相同项目
            exists = False
            for i in range(target_listbox.size()):
                existing_item = target_listbox.get(i)
                # 去除状态指示器前缀进行比较
                clean_existing = existing_item[2:] if existing_item.startswith("● ") else existing_item
                if clean_existing == item_text:
                    exists = True
                    break
            
            # 如果不存在，则添加
            if not exists:
                target_index = target_listbox.size()
                target_listbox.insert(target_index, item_text)
                # 设置默认状态为启用
                setattr(target_listbox, f'item_{target_index}_status', 'enabled')
                added_count += 1
                
        if added_count > 0:
            # 在后台线程中应用反截屏保护
            threading.Thread(target=self._apply_anti_screenshot_protection_thread, args=(target_listbox,), daemon=True).start()
            # 自动保存配置
            self.save_data(show_status=False)
            self.status_label.configure(text=f"已向 {mode_name} 添加 {added_count} 个项目")
        else:
            self.status_label.configure(text="所选项目已存在于目标模式中")
            

    def restore_protection(self, process_name):
        """恢复指定进程的反截屏保护"""
        if process_name not in self.whitelist_protection_states:
            return
            
        # 获取之前保存的保护状态
        protection_states = self.whitelist_protection_states[process_name]
        
        # 注入相应的保护DLL
        dll_injector = DLLInjector()
        success_count = 0
        for state in protection_states:
            pid = state['pid']
            mode = state['mode']
            
            # 根据之前的状态重新注入对应的保护DLL
            success = False
            if mode == 'mode1':
                success = dll_injector.inject_affinity_trans_dll(pid)
            elif mode == 'mode2':
                success = dll_injector.inject_affinity_hide_dll(pid)
            
            if success:
                success_count += 1
        
        # 清除保存的状态
        del self.whitelist_protection_states[process_name]
        
        # 更新状态
        if success_count > 0:
            self.after(0, lambda: self.status_label.configure(
                text=f"已为 {process_name} 的 {success_count} 个实例恢复反截屏保护"))
    
    def get_process_protection_mode(self, pid):
        """获取进程的保护模式"""
        # 检查进程是否在模式一列表中
        for i in range(self.mode1_listbox.size()):
            item_text = self.mode1_listbox.get(i)
            # 处理状态指示器
            if item_text.startswith("● "):
                clean_text = item_text[2:]
            else:
                clean_text = item_text
                
            # 检查进程名是否匹配
            process_name = self.extract_process_name(clean_text)
            if self.is_process_match(process_name, pid):
                return 'mode1'
        
        # 检查进程是否在模式二列表中
        for i in range(self.mode2_listbox.size()):
            item_text = self.mode2_listbox.get(i)
            # 处理状态指示器
            if item_text.startswith("● "):
                clean_text = item_text[2:]
            else:
                clean_text = item_text
                
            # 检查进程名是否匹配
            process_name = self.extract_process_name(clean_text)
            if self.is_process_match(process_name, pid):
                return 'mode2'
        
        return None
    
    def extract_process_name(self, item_text):
        """从列表项文本中提取进程名"""
        if " [" in item_text and item_text.endswith("]"):
            # 窗口列表格式: "窗口标题 [进程名]"
            return item_text.split(" [")[1][:-1]
        elif " (" in item_text and item_text.endswith(")"):
            # 进程列表格式: "进程名 (PID: 1234)"
            return item_text.split(" (")[0]
        else:
            # 自定义添加的项目格式，直接作为进程名处理
            return item_text
    
    def is_process_match(self, target_process_name, pid):
        """检查进程是否匹配"""
        import psutil
        try:
            proc = psutil.Process(pid)
            return proc.name() == target_process_name
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
    
    # 全屏反截屏功能相关方法
    def toggle_fullscreen_antiscreenshot(self):
        """切换全屏反截屏保护的启用状态"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            if self.fullscreen_antiscreenshot_var.get():
                # 启用全屏反截屏保护
                # 导入全屏反截屏模块
                if not hasattr(self, 'fullscreen_antiscreenshot'):
                    from fullscreen_antiscreenshot import FullScreenAntiScreenshot
                    # 获取设置的间隔值
                    try:
                        interval = float(self.fullscreen_interval_var.get())
                    except ValueError:
                        interval = 0.1  # 默认值
                    
                    # 获取连续保护设置
                    continuous = self.continuous_protection_var.get() if hasattr(self, 'continuous_protection_var') else True
                    
                    self.fullscreen_antiscreenshot = FullScreenAntiScreenshot(
                        protection_interval=interval,
                        protection_enabled=True,  # 默认启用
                        continuous_protection=continuous
                    )
                
                # 启用保护
                self.fullscreen_antiscreenshot.set_protection_enabled(True)
                # 如果还没有启动，则启动
                if not hasattr(self.fullscreen_antiscreenshot, '_thread_started'):
                    import threading
                    thread = threading.Thread(target=self.fullscreen_antiscreenshot.start, daemon=True)
                    thread.start()
                    self.fullscreen_antiscreenshot._thread_started = True
                self.status_label.configure(text="全屏反截屏保护已启用")
            else:
                # 禁用全屏反截屏保护
                if hasattr(self, 'fullscreen_antiscreenshot'):
                    # 先禁用保护
                    self.fullscreen_antiscreenshot.set_protection_enabled(False)
                    # 然后停止并销毁窗口（确保在主线程中执行）
                    self.after(0, lambda: self._safe_stop_fullscreen_antiscreenshot())
                self.status_label.configure(text="全屏反截屏保护已禁用")
                
            # 自动保存配置
            self._schedule_auto_save()
        except Exception as e:
            self.status_label.configure(text=f"切换全屏反截屏保护时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _safe_stop_fullscreen_antiscreenshot(self):
        """安全地停止全屏反截屏保护"""
        try:
            if hasattr(self, 'fullscreen_antiscreenshot'):
                self.fullscreen_antiscreenshot.stop()
                # 移除引用以便重新创建
                delattr(self, 'fullscreen_antiscreenshot')
        except Exception as e:
            print(f"停止全屏反截屏保护时出错: {e}")
    
    def toggle_continuous_protection(self):
        """切换连续保护功能的启用状态"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            if hasattr(self, 'fullscreen_antiscreenshot'):
                continuous = self.continuous_protection_var.get()
                self.fullscreen_antiscreenshot.set_continuous_protection(continuous)
                status = "启用" if continuous else "禁用"
                self.status_label.configure(text=f"连续保护已{status}")
            else:
                self.status_label.configure(text="请先启用全屏反截屏保护")
                
            # 自动保存配置
            self._schedule_auto_save()
        except Exception as e:
            self.status_label.configure(text=f"切换连续保护时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def toggle_child_process_injection(self):
        """切换子进程注入功能的启用状态"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            pass  # 子进程注入开关的操作已经在其他地方处理
            
            # 自动保存配置
            self._schedule_auto_save()
        except Exception as e:
            self.status_label.configure(text=f"切换子进程注入时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def apply_fullscreen_interval(self):
        """应用全屏反截屏保护的间隔设置"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            if hasattr(self, 'fullscreen_antiscreenshot'):
                interval = float(self.fullscreen_interval_var.get())
                self.fullscreen_antiscreenshot.set_protection_interval(interval)
                self.status_label.configure(text=f"全屏反截屏保护间隔已设置为 {interval} 秒")
            else:
                self.status_label.configure(text="请先启用全屏反截屏保护")
                
            # 自动保存配置
            self._schedule_auto_save()
        except ValueError:
            self.status_label.configure(text="请输入有效的数字作为间隔")
        except Exception as e:
            self.status_label.configure(text=f"应用间隔设置时出错: {str(e)}")
            import traceback
            traceback.print_exc()

        
        try:
            # 根据开关状态启用或禁用开机自启动
            if self.auto_start_var.get():
                self.enable_auto_start()
            else:
                self.disable_auto_start()
        except Exception as e:
            self.status_label.configure(text=f"切换开机自启动时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def apply_fullscreen_interval(self):
        """应用全屏反截屏保护的间隔设置"""
        import time
        current_time = time.time()
        
        # 移除速率限制，允许即时切换
        # if current_time - self._last_setting_toggle_time < 1.0:
        #     return
            
        self._last_setting_toggle_time = current_time
        
        try:
            if hasattr(self, 'fullscreen_antiscreenshot'):
                interval = float(self.fullscreen_interval_var.get())
                self.fullscreen_antiscreenshot.set_protection_interval(interval)
                self.status_label.configure(text=f"全屏反截屏保护间隔已设置为 {interval} 秒")
            else:
                self.status_label.configure(text="请先启用全屏反截屏保护")
        except ValueError:
            self.status_label.configure(text="请输入有效的数字作为间隔")
        except Exception as e:
            self.status_label.configure(text=f"应用间隔设置时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _schedule_auto_save(self):
        """安排自动保存，防抖动"""
        if not self._pending_save:
            self._pending_save = True
            self.after(500, self._perform_auto_save)  # 延迟500ms保存
    
    def _perform_auto_save(self):
        """执行自动保存"""
        if self._pending_save:
            self._pending_save = False
            try:
                self.save_data(show_status=False)  # 静默保存，不显示状态信息
            except Exception as e:
                print(f"自动保存配置失败: {e}")