use std::collections::HashMap;
use windows::Win32::Foundation::*;
use windows::Win32::System::Diagnostics::ToolHelp::*;

pub struct ProcessInfo {
    pub name: String,
    pub pids: Vec<u32>,
    pub parent_pids: Vec<u32>,
    pub count: usize,
}

pub struct WindowInfo {
    pub title: String,
    pub process_name: String,
    pub pid: u32,
}

pub struct ProcessLoader;

impl ProcessLoader {
    pub fn load_processes() -> Vec<ProcessInfo> {
        let mut process_dict: HashMap<String, ProcessInfo> = HashMap::new();

        unsafe {
            let mut entry = PROCESSENTRY32W {
                dwSize: size_of::<PROCESSENTRY32W>() as u32,
                ..Default::default()
            };

            let snapshot = match CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) {
                Ok(handle) => handle,
                Err(_) => {
                    println!("创建进程快照失败");
                    return Vec::new();
                }
            };

            if Process32FirstW(snapshot, &mut entry).is_ok() {
                loop {
                    let name = String::from_utf16_lossy(
                        &entry.szExeFile[..entry.szExeFile.iter().position(|&c| c == 0).unwrap_or(0)]
                    );

                    let pid = entry.th32ProcessID;
                    let ppid = entry.th32ParentProcessID;

                    if let Some(info) = process_dict.get_mut(&name) {
                        info.pids.push(pid);
                        info.parent_pids.push(ppid);
                        info.count += 1;
                    } else {
                        process_dict.insert(name.clone(), ProcessInfo {
                            name: name.clone(),
                            pids: vec![pid],
                            parent_pids: vec![ppid],
                            count: 1,
                        });
                    }

                    if !Process32NextW(snapshot, &mut entry).is_ok() {
                        break;
                    }
                }
            }

            let _ = CloseHandle(snapshot);
        }

        let mut processes: Vec<ProcessInfo> = process_dict.into_values().collect();
        processes.sort_by(|a: &ProcessInfo, b: &ProcessInfo| a.name.cmp(&b.name));
        processes
    }

    pub fn format_process_info(info: &ProcessInfo) -> String {
        if info.count == 1 {
            format!("{} (PID: {})", info.name, info.pids[0])
        } else {
            format!("{} ({} 个实例)", info.name, info.count)
        }
    }
}

pub struct WindowLoader;

impl WindowLoader {
    pub fn load_windows() -> Vec<WindowInfo> {
        let mut windows = Vec::new();

        unsafe {
            use windows::Win32::UI::WindowsAndMessaging::*;
            use windows::Win32::Foundation::LPARAM;

            let result = EnumWindows(Some(Self::enum_windows_callback), LPARAM(&mut windows as *mut _ as isize));
            if result.is_err() {
                println!("枚举窗口失败");
            }
        }

        windows.sort_by(|a: &WindowInfo, b: &WindowInfo| a.title.cmp(&b.title));
        windows
    }

    unsafe extern "system" fn enum_windows_callback(window_handle: HWND, param: LPARAM) -> BOOL {
        use windows::Win32::UI::WindowsAndMessaging::*;

        if !IsWindowVisible(window_handle).as_bool() {
            return TRUE;
        }

        let mut text_buffer = [0u16; 512];
        let length = GetWindowTextW(window_handle, &mut text_buffer);

        if length == 0 {
            return TRUE;
        }

        let title = String::from_utf16_lossy(&text_buffer[..length as usize]);

        let mut pid = 0u32;
        GetWindowThreadProcessId(window_handle, Some(&mut pid));

        let process_name = Self::get_process_name(pid);

        let windows = &mut *(param.0 as *mut Vec<WindowInfo>);
        windows.push(WindowInfo {
            title,
            process_name,
            pid,
        });

        TRUE
    }

    unsafe fn get_process_name(pid: u32) -> String {
        use windows::Win32::System::Threading::*;
        use windows::core::PWSTR;

        let process_handle = match OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, false, pid) {
            Ok(handle) => handle,
            Err(_) => return "unknown".to_string(),
        };

        if process_handle.is_invalid() {
            return "unknown".to_string();
        }

        let mut name_buffer = [0u16; 260];
        let mut size = name_buffer.len() as u32;

        let result = QueryFullProcessImageNameW(
            process_handle, 
            PROCESS_NAME_FORMAT(0), 
            PWSTR(name_buffer.as_mut_ptr()), 
            &mut size
        );

        let _ = CloseHandle(process_handle);

        if result.is_ok() {
            let path = String::from_utf16_lossy(&name_buffer[..size as usize]);
            if let Some(name) = path.split('\\').last() {
                return name.to_string();
            }
        }

        "unknown".to_string()
    }

    pub fn format_window_info(info: &WindowInfo) -> String {
        format!("{} [{}]", info.title, info.process_name)
    }
}

pub fn get_child_processes(parent_pid: u32) -> Vec<(String, u32)> {
    let mut child_processes = Vec::new();

    let processes = ProcessLoader::load_processes();

    for process in processes {
        for (i, &ppid) in process.parent_pids.iter().enumerate() {
            if ppid == parent_pid {
                child_processes.push((process.name.clone(), process.pids[i]));
                break;
            }
        }
    }

    child_processes
}