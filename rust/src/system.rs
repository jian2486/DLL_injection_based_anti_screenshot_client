use anyhow::Result;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use windows::core::PCSTR;
use windows::Win32::Foundation::{BOOL, COLORREF, HWND, WIN32_ERROR};
use windows::Win32::System::LibraryLoader::*;
use windows::Win32::System::Registry::*;
use windows::Win32::UI::WindowsAndMessaging::*;

pub struct AutoStartManager;

impl AutoStartManager {
    const REG_KEY_PATH: PCSTR = windows::core::s!(r"Software\Microsoft\Windows\CurrentVersion\Run");

    pub fn enable(exe_path: &str) -> Result<()> {
        unsafe {
            let mut hkey = HKEY::default();
            let result = RegOpenKeyExA(
                HKEY_CURRENT_USER,
                Self::REG_KEY_PATH,
                0,
                KEY_WRITE,
                &mut hkey,
            );

            if result != WIN32_ERROR(0) {
                anyhow::bail!("无法打开注册表键");
            }

            let result = RegSetValueExA(
                hkey,
                windows::core::s!("AntiScreenshotManager"),
                0,
                REG_SZ,
                Some(exe_path.as_bytes()),
            );

            if result != WIN32_ERROR(0) {
                let _ = RegCloseKey(hkey);
                anyhow::bail!("无法设置注册表值");
            }

            let _ = RegCloseKey(hkey);
            println!("已启用开机自启动");
        }

        Ok(())
    }

    pub fn disable() -> Result<()> {
        unsafe {
            let mut hkey = HKEY::default();
            let result = RegOpenKeyExA(
                HKEY_CURRENT_USER,
                Self::REG_KEY_PATH,
                0,
                KEY_WRITE,
                &mut hkey,
            );

            if result != WIN32_ERROR(0) {
                anyhow::bail!("无法打开注册表键");
            }

            let result = RegDeleteValueA(hkey, windows::core::s!("AntiScreenshotManager"));
            if result != WIN32_ERROR(0) {
                let _ = RegCloseKey(hkey);
                anyhow::bail!("无法删除注册表值");
            }

            let _ = RegCloseKey(hkey);
            println!("已禁用开机自启动");
        }

        Ok(())
    }
}

pub struct FullscreenAntiScreenshot {
    window_handle: Option<isize>,
    enabled: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
    protection_thread: Option<thread::JoinHandle<()>>,
}

impl FullscreenAntiScreenshot {
    pub fn new() -> Self {
        Self {
            window_handle: None,
            enabled: Arc::new(AtomicBool::new(false)),
            running: Arc::new(AtomicBool::new(false)),
            protection_thread: None,
        }
    }

    pub fn enable(&mut self) -> Result<()> {
        if self.enabled.load(Ordering::SeqCst) {
            return Ok(());
        }

        unsafe {
            let module_handle = GetModuleHandleW(None)?;

            let screen_width = GetSystemMetrics(SM_CXSCREEN);
            let screen_height = GetSystemMetrics(SM_CYSCREEN);

            let title: Vec<u16> = "全屏反截屏保护已激活"
                .encode_utf16()
                .chain(std::iter::once(0))
                .collect();

            let hwnd = CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED,
                windows::core::w!("STATIC"),
                windows::core::PCWSTR::from_raw(title.as_ptr()),
                WS_POPUP,
                0,
                0,
                screen_width,
                screen_height,
                None,
                None,
                module_handle,
                None,
            )?;

            if hwnd.is_invalid() {
                anyhow::bail!("创建全屏窗口失败");
            }

            let _ = SetLayeredWindowAttributes(hwnd, COLORREF(0), 1, LWA_ALPHA);

            let mut ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE);
            ex_style |= WS_EX_LAYERED.0 as i32 | WS_EX_TRANSPARENT.0 as i32;
            let _ = SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style);

            let _ = SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            );

            self.window_handle = Some(hwnd.0 as isize);
            self.enabled.store(true, Ordering::SeqCst);

            let enabled_clone = self.enabled.clone();
            let running_clone = self.running.clone();
            let hwnd_raw = hwnd.0 as isize;
            running_clone.store(true, Ordering::SeqCst);

            self.protection_thread = Some(thread::spawn(move || {
                let hwnd = HWND(hwnd_raw as *mut std::ffi::c_void);
                while running_clone.load(Ordering::SeqCst) {
                    if enabled_clone.load(Ordering::SeqCst) {
                        Self::apply_display_affinity_internal(hwnd, true);
                        Self::apply_window_properties_internal(hwnd);
                    }
                    thread::sleep(std::time::Duration::from_millis(100));
                }
            }));

            println!("全屏反截屏保护已启用");
        }

        Ok(())
    }

    fn apply_display_affinity_internal(hwnd: HWND, enable: bool) {
        unsafe {
            let user32 = GetModuleHandleA(windows::core::s!("user32.dll"));
            if user32.is_err() {
                return;
            }
            
            type SetWindowDisplayAffinityFn = unsafe extern "system" fn(HWND, u32) -> BOOL;
            let proc = GetProcAddress(user32.unwrap(), windows::core::s!("SetWindowDisplayAffinity"));
            
            if proc.is_none() {
                return;
            }
            
            let func: SetWindowDisplayAffinityFn = std::mem::transmute(proc.unwrap());
            let affinity = if enable { 0x00000001u32 } else { 0x00000000u32 };
            let _ = func(hwnd, affinity);
        }
    }

    fn apply_window_properties_internal(hwnd: HWND) {
        unsafe {
            let ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE);
            
            let mut style = ex_style;
            style |= WS_EX_TOPMOST.0 as i32 | WS_EX_TRANSPARENT.0 as i32 |
                    WS_EX_TOOLWINDOW.0 as i32 | WS_EX_NOACTIVATE.0 as i32;
            let _ = SetWindowLongW(hwnd, GWL_EXSTYLE, style);
            
            let _ = SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            );
        }
    }

    pub fn disable(&mut self) -> Result<()> {
        if !self.enabled.load(Ordering::SeqCst) {
            return Ok(());
        }

        self.running.store(false, Ordering::SeqCst);

        if let Some(handle) = self.protection_thread.take() {
            let _ = handle.join();
        }

        if let Some(hwnd_raw) = self.window_handle {
            unsafe {
                let hwnd = HWND(hwnd_raw as *mut std::ffi::c_void);
                Self::apply_display_affinity_internal(hwnd, false);
                let _ = DestroyWindow(hwnd);
            }
        }

        self.window_handle = None;
        self.enabled.store(false, Ordering::SeqCst);

        println!("全屏反截屏保护已禁用");
        Ok(())
    }

    pub fn is_enabled(&self) -> bool {
        self.enabled.load(Ordering::SeqCst)
    }
}

impl Drop for FullscreenAntiScreenshot {
    fn drop(&mut self) {
        let _ = self.disable();
    }
}