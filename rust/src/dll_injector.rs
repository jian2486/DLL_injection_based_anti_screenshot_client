use anyhow::Result;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use windows::Win32::Foundation::*;
use windows::Win32::System::Diagnostics::Debug::*;
use windows::Win32::System::LibraryLoader::*;
use windows::Win32::System::Memory::*;
use windows::Win32::System::Threading::*;

pub struct DLLInjector {
    injection_locks: Mutex<std::collections::HashSet<u32>>,
}

impl DLLInjector {
    pub fn new() -> Self {
        Self {
            injection_locks: Mutex::new(std::collections::HashSet::new()),
        }
    }

    pub fn inject_affinity_hide_dll(&self, process_id: u32) -> Result<bool> {
        let dll_path = self.get_architecture_specific_dll_path("AffinityHide.dll", process_id)?;
        self.inject_dll(process_id, &dll_path)
    }

    pub fn inject_affinity_trans_dll(&self, process_id: u32) -> Result<bool> {
        let dll_path = self.get_architecture_specific_dll_path("AffinityTrans.dll", process_id)?;
        self.inject_dll(process_id, &dll_path)
    }

    pub fn inject_affinity_unhide_dll(&self, process_id: u32) -> Result<bool> {
        let dll_path = self.get_architecture_specific_dll_path("AffinityUnhide.dll", process_id)?;
        self.inject_dll(process_id, &dll_path)
    }

    fn inject_dll(&self, process_id: u32, dll_path: &Path) -> Result<bool> {
        let mut locks = self.injection_locks.lock().unwrap();
        if locks.contains(&process_id) {
            println!("进程 {} 正在注入中，跳过重复注入", process_id);
            return Ok(false);
        }
        locks.insert(process_id);
        drop(locks);

        let result = self.inject_dll_internal(process_id, dll_path);

        let mut locks = self.injection_locks.lock().unwrap();
        locks.remove(&process_id);

        result
    }

    fn inject_dll_internal(&self, process_id: u32, dll_path: &Path) -> Result<bool> {
        if !dll_path.exists() {
            println!("DLL文件不存在: {:?}", dll_path);
            return Ok(false);
        }

        unsafe {
            let process_handle = match OpenProcess(PROCESS_ALL_ACCESS, false, process_id) {
                Ok(handle) => handle,
                Err(_) => {
                    println!("无法打开进程 {}", process_id);
                    return Ok(false);
                }
            };

            if process_handle.is_invalid() {
                println!("无法打开进程 {}", process_id);
                return Ok(false);
            }

            let dll_path_wide: Vec<u16> = dll_path
                .to_string_lossy()
                .encode_utf16()
                .chain(std::iter::once(0))
                .collect();

            let path_size = dll_path_wide.len() * 2;

            let allocated_memory = VirtualAllocEx(
                process_handle,
                None,
                path_size,
                MEM_COMMIT | MEM_RESERVE,
                PAGE_READWRITE,
            );

            if allocated_memory.is_null() {
                println!("无法在目标进程中分配内存");
                let _ = CloseHandle(process_handle);
                return Ok(false);
            }

            let mut bytes_written = 0usize;
            let write_result = WriteProcessMemory(
                process_handle,
                allocated_memory,
                dll_path_wide.as_ptr() as *const _,
                path_size,
                Some(&mut bytes_written),
            );

            if write_result.is_err() {
                println!("无法向目标进程写入DLL路径");
                let _ = VirtualFreeEx(process_handle, allocated_memory, 0, MEM_RELEASE);
                let _ = CloseHandle(process_handle);
                return Ok(false);
            }

            let kernel32_handle = match GetModuleHandleA(windows::core::s!("kernel32.dll")) {
                Ok(handle) => handle,
                Err(_) => {
                    println!("无法获取kernel32.dll句柄");
                    let _ = VirtualFreeEx(process_handle, allocated_memory, 0, MEM_RELEASE);
                    let _ = CloseHandle(process_handle);
                    return Ok(false);
                }
            };

            let load_library_addr = GetProcAddress(kernel32_handle, windows::core::s!("LoadLibraryW"));

            if load_library_addr.is_none() {
                println!("无法获取LoadLibraryW地址");
                let _ = VirtualFreeEx(process_handle, allocated_memory, 0, MEM_RELEASE);
                let _ = CloseHandle(process_handle);
                return Ok(false);
            }

            let thread_handle = match CreateRemoteThread(
                process_handle,
                None,
                0,
                Some(std::mem::transmute(load_library_addr.unwrap())),
                Some(allocated_memory),
                0,
                None,
            ) {
                Ok(handle) => handle,
                Err(_) => {
                    println!("无法创建远程线程");
                    let _ = VirtualFreeEx(process_handle, allocated_memory, 0, MEM_RELEASE);
                    let _ = CloseHandle(process_handle);
                    return Ok(false);
                }
            };

            WaitForSingleObject(thread_handle, 10000);

            let mut exit_code = 0u32;
            let dll_loaded = if GetExitCodeThread(thread_handle, &mut exit_code).is_ok() {
                exit_code != 0
            } else {
                false
            };

            let _ = CloseHandle(thread_handle);
            std::thread::sleep(std::time::Duration::from_millis(100));
            let _ = VirtualFreeEx(process_handle, allocated_memory, 0, MEM_RELEASE);
            let _ = CloseHandle(process_handle);

            if dll_loaded {
                println!("为进程 {} 注入 {:?} 成功", process_id, dll_path.file_name());
                Ok(true)
            } else {
                println!("为进程 {} 注入 {:?} 失败", process_id, dll_path.file_name());
                Ok(false)
            }
        }
    }

    fn get_architecture_specific_dll_path(&self, dll_name: &str, process_id: u32) -> Result<PathBuf> {
        let architecture = self.get_process_architecture(process_id);

        let base_dll_dir = std::env::current_exe()?
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("AntiScreenshot");

        let dll_path = if let Some(arch) = architecture {
            let arch_dll_path = base_dll_dir.join(&arch).join(dll_name);
            if arch_dll_path.exists() {
                println!("为进程 {} 选择 {} 版本的DLL: {:?}", process_id, arch, arch_dll_path);
                return Ok(arch_dll_path);
            }
            println!("未找到 {} 版本的DLL: {:?}", arch, arch_dll_path);
            arch_dll_path
        } else {
            println!("无法确定进程 {} 的架构，使用默认DLL路径", process_id);
            base_dll_dir.join("x64").join(dll_name)
        };

        if dll_path.exists() {
            Ok(dll_path)
        } else {
            Ok(base_dll_dir.join(dll_name))
        }
    }

    fn get_process_architecture(&self, process_id: u32) -> Option<String> {
        unsafe {
            let process_handle = match OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, false, process_id) {
                Ok(handle) => handle,
                Err(_) => return None,
            };

            if process_handle.is_invalid() {
                return None;
            }

            let mut is_wow64 = BOOL::from(false);
            let result = IsWow64Process(process_handle, &mut is_wow64);

            let _ = CloseHandle(process_handle);

            if result.is_ok() {
                if is_wow64 != FALSE {
                    Some("x86".to_string())
                } else {
                    Some("x64".to_string())
                }
            } else {
                None
            }
        }
    }
}