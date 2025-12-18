import psutil
import win32gui
import win32process


class ProcessLoader:
    """进程列表加载线程"""
    def __init__(self, callback):
        self.callback = callback
        self.process_dict = {}
        
    def run(self):
        try:
            # 收集所有进程信息
            for proc in psutil.process_iter():
                try:
                    pid = proc.pid
                    name = proc.name()
                    
                    try:
                        ppid = proc.ppid()
                    except:
                        ppid = 0
                    
                    if name not in self.process_dict:
                        self.process_dict[name] = {
                            'pids': [pid],
                            'ppids': [ppid],
                            'count': 1
                        }
                    else:
                        self.process_dict[name]['pids'].append(pid)
                        self.process_dict[name]['ppids'].append(ppid)
                        self.process_dict[name]['count'] += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # 格式化输出
            processes = []
            for name, info in self.process_dict.items():
                if info['count'] == 1:
                    process_info = f"{name} (PID: {info['pids'][0]})"
                else:
                    process_info = f"{name} ({info['count']} 个实例)"
                processes.append((process_info, name))
                
            # 调用回调函数传递结果
            self.callback(sorted(processes, key=lambda x: x[0]))
        except Exception as e:
            self.callback([])


class WindowLoader:
    """窗口列表加载线程"""
    def __init__(self, callback):
        self.callback = callback
        
    def run(self):
        windows = []
        
        def enum_windows_callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                try:
                    window_text = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = "unknown"
                    try:
                        process = psutil.Process(pid)
                        process_name = process.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    # 使用标准格式: "窗口标题 [进程名]"
                    window_info = f"{window_text} [{process_name}]"
                    windows_list.append((window_info, process_name))
                except Exception:
                    pass
            return True
            
        try:
            win32gui.EnumWindows(enum_windows_callback, windows)
            self.callback(sorted(windows, key=lambda x: x[0]))
        except Exception as e:
            self.callback([])