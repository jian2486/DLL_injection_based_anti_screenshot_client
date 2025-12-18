import sys
import os
import ctypes
import ctypes.wintypes
from ctypes import wintypes
import shutil

# 添加对injector库的支持
sys.path.append(os.path.join(os.path.dirname(__file__), 'injector'))
try:
    from injector import Injector as DLLInjectorLib
    INJECTOR_AVAILABLE = True
except ImportError:
    INJECTOR_AVAILABLE = False

# Windows API常量
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_EXECUTE_READWRITE = 0x40
PAGE_READWRITE = 0x04  # 添加缺失的常量定义

# 定义缺失的类型
LPSECURITY_ATTRIBUTES = ctypes.c_void_p

# Windows API函数
kernel32 = ctypes.windll.kernel32
OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

VirtualAllocEx = kernel32.VirtualAllocEx
VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
VirtualAllocEx.restype = wintypes.LPVOID

WriteProcessMemory = kernel32.WriteProcessMemory
WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
WriteProcessMemory.restype = wintypes.BOOL

GetModuleHandle = kernel32.GetModuleHandleW
GetModuleHandle.argtypes = [wintypes.LPCWSTR]
GetModuleHandle.restype = wintypes.HANDLE

GetModuleHandleA = kernel32.GetModuleHandleA
GetModuleHandleA.argtypes = [wintypes.LPCSTR]
GetModuleHandleA.restype = wintypes.HANDLE

GetProcAddress = kernel32.GetProcAddress
GetProcAddress.argtypes = [wintypes.HANDLE, wintypes.LPCSTR]
GetProcAddress.restype = wintypes.LPVOID

CreateRemoteThread = kernel32.CreateRemoteThread
CreateRemoteThread.argtypes = [wintypes.HANDLE, LPSECURITY_ATTRIBUTES, ctypes.c_size_t, wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD]
CreateRemoteThread.restype = wintypes.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

GetLastError = kernel32.GetLastError
GetLastError.argtypes = []
GetLastError.restype = wintypes.DWORD


class DLLInjector:
    """DLL注入器类，用于向目标进程注入DLL"""
    
    _instance = None
    _initialized = False
    _injection_locks = set()  # 用于防止对同一进程的重复注入
    
    def __new__(cls):
        """单例模式，确保只创建一个实例"""
        if cls._instance is None:
            cls._instance = super(DLLInjector, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化DLL注入器"""
        # 确保只初始化一次
        if not DLLInjector._initialized:
            print("初始化DLL注入器")
            DLLInjector._initialized = True
        
    def _get_process_architecture(self, process_id):
        """
        获取进程的架构类型（32位或64位）
        
        Args:
            process_id (int): 进程ID
            
        Returns:
            str: "x86" 表示32位进程, "x64" 表示64位进程, None 表示无法确定
        """
        try:
            import win32file
        except ImportError:
            print("无法导入win32file模块，将无法自动检测进程架构")
            return None
            
        try:
            # 获取进程句柄
            process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, process_id)
            if not process_handle:
                print(f"无法打开进程 {process_id} 来检测架构")
                return None
                
            # 获取进程映像文件路径
            import win32process
            process_path = win32process.GetModuleFileNameEx(process_handle, 0)
            CloseHandle(process_handle)
            
            print(f"检测进程 {process_id} 的可执行文件路径: {process_path}")
            
            # 使用win32file.GetBinaryType检测架构
            binary_type = win32file.GetBinaryType(process_path)
            print(f"进程 {process_id} 的二进制类型: {binary_type}")
            
            if binary_type == win32file.SCS_32BIT_BINARY:
                print(f"进程 {process_id} 是32位程序")
                return "x86"
            else:
                # 如果不是32位，则认为是64位
                print(f"进程 {process_id} 是64位程序")
                return "x64"
        except Exception as e:
            print(f"检测进程 {process_id} 架构时出错: {e}")
            return None
    
    def _get_architecture_specific_dll_path(self, dll_name, process_id):
        """
        根据进程架构获取相应的DLL路径
        
        Args:
            dll_name (str): DLL文件名
            process_id (int): 目标进程ID
            
        Returns:
            str: 对应架构的DLL文件路径，如果无法确定则返回默认路径
        """
        # 获取进程架构
        architecture = self._get_process_architecture(process_id)
        
        # 基础DLL目录
        # 处理PyInstaller打包环境 - 使用程序同目录
        if hasattr(sys, '_MEIPASS'):
            # 在打包环境中，使用程序同目录
            base_dll_dir = os.path.join(os.path.dirname(sys.executable), "dll")
        else:
            # 在开发环境中
            base_dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dll")
        
        print(f"基础DLL目录: {base_dll_dir}")
        
        if architecture:
            # 根据架构选择对应的DLL目录
            arch_dll_dir = os.path.join(base_dll_dir, architecture)
            arch_dll_path = os.path.join(arch_dll_dir, dll_name)
            
            # 检查架构特定的DLL是否存在
            if os.path.exists(arch_dll_path):
                print(f"为进程 {process_id} 选择 {architecture} 版本的DLL: {arch_dll_path}")
                return arch_dll_path
            else:
                print(f"未找到 {architecture} 版本的DLL: {arch_dll_path}")
        else:
            print(f"无法确定进程 {process_id} 的架构，使用默认DLL路径")
        
        # 如果无法确定架构或对应DLL不存在，使用默认路径
        # 默认使用x64版本DLL（大多数现代系统都是64位）
        default_arch = "x64"
        default_dll_path = os.path.join(base_dll_dir, default_arch, dll_name)
        if os.path.exists(default_dll_path):
            print(f"使用默认架构({default_arch})的DLL路径: {default_dll_path}")
            return default_dll_path
            
        # 最后的备选方案
        fallback_path = os.path.join(base_dll_dir, dll_name)
        print(f"使用最终备选DLL路径: {fallback_path}")
        return fallback_path

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
            
    def inject_dll(self, process_id, dll_path):
        """
        向指定进程注入DLL
        
        Args:
            process_id (int): 目标进程ID
            dll_path (str): DLL文件的完整路径
            
        Returns:
            bool: 注入是否成功
        """
        # 检查是否正在对同一进程进行注入
        if process_id in DLLInjector._injection_locks:
            print(f"进程 {process_id} 正在注入中，跳过重复注入")
            return False
            
        # 设置注入锁
        DLLInjector._injection_locks.add(process_id)
        
        try:
            # 导入os模块以使用path相关函数
            import os
            
            # 检查DLL文件是否存在
            if not os.path.exists(dll_path):
                print(f"DLL文件不存在: {dll_path}")
                return False

            # 如果injector库可用，则使用它进行注入
            if INJECTOR_AVAILABLE:
                try:
                    # 创建injector实例
                    injector = DLLInjectorLib()
                    # 加载进程
                    injector.load_from_pid(process_id)
                    # 注入DLL
                    injector.inject_dll(dll_path)
                    # 卸载以关闭进程句柄
                    injector.unload()
                    print(f"为进程 {process_id} 注入 {os.path.basename(dll_path)} 成功")
                    return True
                except Exception as e:
                    print(f"使用injector库注入DLL时发生异常: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                # 使用原有的注入方法
                # 打开目标进程
                process_handle = OpenProcess(PROCESS_ALL_ACCESS, False, process_id)
                if not process_handle:
                    error_code = GetLastError()
                    print(f"无法打开进程 {process_id}，错误码: {error_code}")
                    return False

                # 检查进程是否仍处于活动状态
                exit_code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
                    if exit_code.value != 259:  # STILL_ACTIVE = 259
                        print(f"进程 {process_id} 已经退出，无法注入DLL")
                        CloseHandle(process_handle)
                        return False

                # 尝试提升当前进程权限
                try:
                    import win32api
                    import win32security
                    import ntsecuritycon as con
                    
                    # 获取当前进程令牌
                    token = win32security.OpenProcessToken(
                        win32api.GetCurrentProcess(),
                        0x000F01FF  # TOKEN_ALL_ACCESS的值
                    )
                    
                    # 启用调试权限
                    win32security.AdjustTokenPrivileges(
                        token,
                        False,
                        [(win32security.LookupPrivilegeValue(None, "SeDebugPrivilege"), con.SE_PRIVILEGE_ENABLED)]
                    )
                    print("已尝试提升调试权限")
                except Exception as e:
                    print(f"无法提升调试权限: {e}")

                # 在目标进程中分配内存用于存储DLL路径
                # 使用UTF-16编码路径（宽字符串）
                dll_path_bytes = dll_path.encode('utf-16le') + b'\x00\x00'  # UTF-16 LE with null terminator
                path_size = len(dll_path_bytes)

                allocated_memory = VirtualAllocEx(
                    process_handle,
                    None,
                    path_size,
                    MEM_COMMIT | MEM_RESERVE,
                    PAGE_READWRITE
                )

                if not allocated_memory:
                    error_code = GetLastError()
                    print(f"无法在目标进程中分配内存，错误码: {error_code}")
                    CloseHandle(process_handle)
                    return False

                # 将DLL路径写入目标进程内存
                written_bytes = ctypes.c_size_t(0)
                if not WriteProcessMemory(
                    process_handle,
                    allocated_memory,
                    dll_path_bytes,
                    path_size,
                    ctypes.byref(written_bytes)
                ):
                    error_code = GetLastError()
                    print(f"无法向目标进程写入DLL路径，错误码: {error_code}")
                    # 释放已分配的内存
                    kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                    CloseHandle(process_handle)
                    return False

                # 检查实际写入的字节数
                if written_bytes.value != path_size:
                    print(f"写入DLL路径大小不匹配: 期望 {path_size} 字节, 实际 {written_bytes.value} 字节")
                    # 释放已分配的内存
                    kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                    CloseHandle(process_handle)
                    return False

                # 获取LoadLibraryW函数地址 (使用宽字符串版本)
                kernel32_handle = GetModuleHandle("kernel32.dll")
                if not kernel32_handle:
                    error_code = GetLastError()
                    print(f"无法获取kernel32.dll句柄，错误码: {error_code}")
                    # 释放已分配的内存
                    kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                    CloseHandle(process_handle)
                    return False

                load_library_addr = GetProcAddress(kernel32_handle, b"LoadLibraryW")
                if not load_library_addr:
                    error_code = GetLastError()
                    print(f"无法获取LoadLibraryW地址，错误码: {error_code}")
                    # 释放已分配的内存
                    kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                    CloseHandle(process_handle)
                    return False

                # 创建远程线程执行LoadLibraryW加载DLL
                thread_handle = CreateRemoteThread(
                    process_handle,
                    None,
                    0,
                    load_library_addr,
                    allocated_memory,
                    0,
                    None
                )

                if not thread_handle:
                    error_code = GetLastError()
                    print(f"无法创建远程线程，错误码: {error_code}")
                    # 释放已分配的内存
                    kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                    CloseHandle(process_handle)
                    return False

                # 等待线程执行完成（最多等待10秒）
                result = kernel32.WaitForSingleObject(thread_handle, 10000)
                if result == 0xFFFFFFFF:  # WAIT_FAILED
                    print(f"等待线程完成时出错，进程 {process_id}")
                elif result == 0x00000102:  # WAIT_TIMEOUT
                    print(f"等待线程完成超时，进程 {process_id}")
                else:
                    print(f"线程执行完成，进程 {process_id}")

                # 获取线程退出码来检查DLL是否成功加载
                exit_code = wintypes.DWORD()
                dll_loaded = False
                if kernel32.GetExitCodeThread(thread_handle, ctypes.byref(exit_code)):
                    print(f"DLL加载线程退出码: {exit_code.value}")
                    # 如果退出码为非零值，表示DLL加载成功（返回加载模块的句柄）
                    dll_loaded = (exit_code.value != 0)
                    
                    # 如果退出码为0，尝试获取更多错误信息
                    if not dll_loaded:
                        last_error = GetLastError()
                        print(f"LoadLibraryW执行失败，错误码: {last_error}")
                        
                        # 检查DLL文件是否存在且可访问
                        import os
                        if not os.path.exists(dll_path):
                            print(f"DLL文件不存在或无法访问: {dll_path}")
                        else:
                            print(f"DLL文件存在且可访问: {dll_path}")

                # 清理资源
                CloseHandle(thread_handle)
                # 延迟释放内存，确保LoadLibrary执行完成
                import time
                time.sleep(0.1)
                kernel32.VirtualFreeEx(process_handle, allocated_memory, 0, 0x8000)  # MEM_RELEASE
                CloseHandle(process_handle)

                # 根据退出码判断注入是否成功
                if not dll_loaded:
                    print(f"为进程 {process_id} 注入 {os.path.basename(dll_path)} 失败")
                    return False
                    
                print(f"为进程 {process_id} 注入 {os.path.basename(dll_path)} 成功")
                return True

        except Exception as e:
            print(f"注入DLL时发生异常: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清除注入锁
            if process_id in DLLInjector._injection_locks:
                DLLInjector._injection_locks.remove(process_id)

    def inject_affinity_hide_dll(self, process_id):
        """
        向指定进程注入AffinityHide.dll (模式二)

        Args:
            process_id (int): 目标进程ID

        Returns:
            bool: 注入是否成功
        """
        dll_path = self._get_architecture_specific_dll_path("AffinityHide.dll", process_id)
        return self.inject_dll(process_id, dll_path)

    def inject_affinity_trans_dll(self, process_id):
        """
        向指定进程注入AffinityTrans.dll (模式一)
        
        Args:
            process_id (int): 目标进程ID
            
        Returns:
            bool: 注入是否成功
        """
        dll_path = self._get_architecture_specific_dll_path("AffinityTrans.dll", process_id)
        return self.inject_dll(process_id, dll_path)

    def inject_affinity_unhide_dll(self, process_id):
        """
        向指定进程注入AffinityUnhide.dll (取消反截屏)
        
        Args:
            process_id (int): 目标进程ID
            
        Returns:
            bool: 注入是否成功
        """
        dll_path = self._get_architecture_specific_dll_path("AffinityUnhide.dll", process_id)
        return self.inject_dll(process_id, dll_path)

    def inject_affinity_status_dll(self, process_id):
        """
        向指定进程注入AffinityStatus.dll (检查状态)
        
        Args:
            process_id (int): 目标进程ID
            
        Returns:
            bool: 注入是否成功
        """
        dll_path = self._get_architecture_specific_dll_path("AffinityStatus.dll", process_id)
        return self.inject_dll(process_id, dll_path)