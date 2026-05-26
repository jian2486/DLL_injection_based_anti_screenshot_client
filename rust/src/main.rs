#![windows_subsystem = "windows"]

mod config;
mod dll_injector;
mod loader;
mod system;

use config::{Config, ConfigItem, DataManager};
use dll_injector::DLLInjector;
use loader::{ProcessLoader, WindowLoader, get_child_processes};
use system::{AutoStartManager, FullscreenAntiScreenshot};
use eframe::egui;
use std::sync::{Arc, Mutex};
use std::collections::HashSet;
use std::fs;

struct AntiScreenshotApp {
    config: Config,
    data_manager: DataManager,
    dll_injector: Arc<DLLInjector>,
    fullscreen_protection: Arc<Mutex<FullscreenAntiScreenshot>>,
    
    mode1_items: Vec<ListItem>,
    mode2_items: Vec<ListItem>,
    current_mode: i32,
    current_tab: i32,
    
    processes: Vec<String>,
    windows: Vec<String>,
    
    child_process_injection_enabled: bool,
    auto_start_enabled: bool,
    fullscreen_anti_screenshot_enabled: bool,
    fullscreen_interval: String,
    continuous_protection_enabled: bool,
    
    theme: Theme,
    status_message: String,
    
    show_add_dialog: bool,
    add_dialog_text: String,
    add_dialog_target_mode: i32,
}

#[derive(Clone, Debug)]
struct ListItem {
    text: String,
    enabled: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum Theme {
    Light,
    Dark,
}

impl Default for AntiScreenshotApp {
    fn default() -> Self {
        let data_manager = DataManager::new().expect("创建数据管理器失败");
        let config = data_manager.load().unwrap_or_default();

        let mode1_items: Vec<ListItem> = config.mode1_items.iter()
            .map(|item| ListItem {
                text: item.text.clone(),
                enabled: item.enabled,
            })
            .collect();

        let mode2_items: Vec<ListItem> = config.mode2_items.iter()
            .map(|item| ListItem {
                text: item.text.clone(),
                enabled: item.enabled,
            })
            .collect();

        let theme = match config.theme.as_str() {
            "Light" => Theme::Light,
            "Dark" => Theme::Dark,
            _ => Theme::Dark,
        };

        let fullscreen_protection = Arc::new(Mutex::new(FullscreenAntiScreenshot::new()));

        if config.fullscreen_anti_screenshot_enabled {
            let _ = fullscreen_protection.lock().unwrap().enable();
        }

        Self {
            config,
            data_manager,
            dll_injector: Arc::new(DLLInjector::new()),
            fullscreen_protection,
            mode1_items,
            mode2_items,
            current_mode: 1,
            current_tab: 0,
            processes: Vec::new(),
            windows: Vec::new(),
            child_process_injection_enabled: false,
            auto_start_enabled: false,
            fullscreen_anti_screenshot_enabled: false,
            fullscreen_interval: "0.1".to_string(),
            continuous_protection_enabled: true,
            theme,
            status_message: "就绪".to_string(),
            show_add_dialog: false,
            add_dialog_text: String::new(),
            add_dialog_target_mode: 1,
        }
    }
}

impl eframe::App for AntiScreenshotApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.apply_theme(ctx);
        
        egui::TopBottomPanel::top("top_panel").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("反截屏管理程序");
                ui.separator();
                
                if ui.button(if self.current_mode == 1 { "当前模式: 模式一" } else { "当前模式: 模式二" }).clicked() {
                    self.current_mode = if self.current_mode == 1 { 2 } else { 1 };
                    self.status_message = format!("切换到模式{}", self.current_mode);
                }
                
                if ui.button("刷新窗口列表").clicked() {
                    self.refresh_windows();
                }
                
                if ui.button("刷新进程列表").clicked() {
                    self.refresh_processes();
                }
            });
        });

        let process_infos = ProcessLoader::load_processes();
        
        egui::SidePanel::left("left_panel").show(ctx, |ui| {
            ui.heading("模式一");
            let mode1_items = std::mem::take(&mut self.mode1_items);
            self.show_mode_list(ui, mode1_items, 1, &process_infos);
            
            ui.separator();
            
            ui.heading("模式二");
            let mode2_items = std::mem::take(&mut self.mode2_items);
            self.show_mode_list(ui, mode2_items, 2, &process_infos);
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.selectable_value(&mut self.current_tab, 0, "控制");
                ui.selectable_value(&mut self.current_tab, 1, "设置");
                ui.selectable_value(&mut self.current_tab, 2, "关于");
            });
            
            ui.separator();
            
            match self.current_tab {
                0 => self.show_control_tab(ui),
                1 => self.show_settings_tab(ui),
                2 => self.show_about_tab(ui),
                _ => {}
            }
        });

        egui::TopBottomPanel::bottom("status_panel").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(&self.status_message);
            });
        });

        if self.show_add_dialog {
            self.show_add_dialog(ctx);
        }

        ctx.request_repaint();
    }
}

impl AntiScreenshotApp {
    fn apply_theme(&self, ctx: &egui::Context) {
        match self.theme {
            Theme::Light => {
                ctx.set_visuals(egui::Visuals::light());
            }
            Theme::Dark => {
                ctx.set_visuals(egui::Visuals::dark());
            }
        }
    }

    fn show_mode_list(&mut self, ui: &mut egui::Ui, mut items: Vec<ListItem>, mode: i32, process_infos: &[loader::ProcessInfo]) {
        let mut items_to_remove = Vec::new();
        let mut changed = false;
        
        ui.vertical(|ui| {
            for (idx, item) in items.iter_mut().enumerate() {
                let display_text = if item.enabled {
                    item.text.clone()
                } else {
                    format!("● {}", item.text)
                };
                
                ui.group(|ui| {
                    ui.horizontal_wrapped(|ui| {
                        let mut enabled = item.enabled;
                        if ui.checkbox(&mut enabled, "").changed() {
                            item.enabled = enabled;
                            changed = true;
                        }
                        
                        let display_char_count = display_text.chars().count();
                        let truncated_text = if display_char_count > 15 {
                            let chars: String = display_text.chars().take(15).collect();
                            format!("{}...", chars)
                        } else {
                            display_text.clone()
                        };
                        ui.label(&truncated_text);
                        
                        if ui.small_button("×").clicked() {
                            items_to_remove.push((idx, item.text.clone()));
                        }
                    });
                });
            }
            
            ui.horizontal(|ui| {
                if ui.button("添加").clicked() {
                    self.show_add_dialog = true;
                    self.add_dialog_target_mode = mode;
                }
                
                if ui.button("清空").clicked() {
                    let pids_to_uninject: Vec<u32> = items.iter()
                        .flat_map(|item| {
                            let process_name = Self::extract_process_name(&item.text);
                            process_infos.iter()
                                .filter(|proc_info| proc_info.name == process_name)
                                .flat_map(|proc_info| proc_info.pids.clone())
                                .collect::<Vec<u32>>()
                        })
                        .collect();
                    
                    std::thread::spawn(move || {
                        let injector = DLLInjector::new();
                        for pid in pids_to_uninject {
                            let _ = injector.inject_affinity_unhide_dll(pid);
                        }
                    });
                    
                    items.clear();
                    self.status_message = format!("正在清除模式{}的反截屏保护...", mode);
                    self.save_config();
                }
            });
        });

        items_to_remove.sort();
        for (idx, text) in items_to_remove.into_iter().rev() {
            let pids: Vec<u32> = {
                let process_name = Self::extract_process_name(&text);
                process_infos.iter()
                    .filter(|proc_info| proc_info.name == process_name)
                    .flat_map(|proc_info| proc_info.pids.clone())
                    .collect()
            };
            
            std::thread::spawn(move || {
                let injector = DLLInjector::new();
                for pid in pids {
                    let _ = injector.inject_affinity_unhide_dll(pid);
                }
            });
            
            items.remove(idx);
        }

        if changed {
            self.status_message = "项目状态已更改".to_string();
            self.save_config();
        }

        if mode == 1 {
            self.mode1_items = items;
        } else {
            self.mode2_items = items;
        }
    }

    fn show_control_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("窗口列表 (双击添加)");
        
        let windows: Vec<String> = self.windows.clone();
        egui::ScrollArea::vertical()
            .id_source("window_list_scroll")
            .max_height(200.0)
            .show(ui, |ui| {
                for window in &windows {
                    if ui.selectable_label(false, window).double_clicked() {
                        self.add_to_current_mode(window);
                    }
                }
            });

        ui.separator();
        
        ui.heading("进程列表 (双击添加)");
        
        let processes: Vec<String> = self.processes.clone();
        egui::ScrollArea::vertical()
            .id_source("process_list_scroll")
            .max_height(200.0)
            .show(ui, |ui| {
                for process in &processes {
                    if ui.selectable_label(false, process).double_clicked() {
                        self.add_to_current_mode(process);
                    }
                }
            });

        ui.label("说明：双击列表项可添加到当前模式");
    }

    fn show_settings_tab(&mut self, ui: &mut egui::Ui) {
        ui.heading("程序设置");
        
        ui.separator();
        
        ui.heading("主题设置");
        ui.horizontal(|ui| {
            ui.label("选择主题:");
            if ui.radio_value(&mut self.theme, Theme::Light, "浅色主题").changed() {
                self.config.theme = "Light".to_string();
                self.save_config();
            }
            if ui.radio_value(&mut self.theme, Theme::Dark, "深色主题").changed() {
                self.config.theme = "Dark".to_string();
                self.save_config();
            }
        });

        ui.separator();
        
        ui.heading("子进程注入设置");
        ui.label("向指定程序的所有子进程注入反截屏保护");
        ui.horizontal(|ui| {
            ui.label("启用子进程注入:");
            if ui.checkbox(&mut self.child_process_injection_enabled, "").changed() {
                self.config.child_process_injection_enabled = self.child_process_injection_enabled;
                self.save_config();
            }
        });

        ui.separator();
        
        ui.heading("开机自启动设置");
        ui.label("程序将在Windows启动时自动运行");
        ui.horizontal(|ui| {
            ui.label("启用开机自启动:");
            if ui.checkbox(&mut self.auto_start_enabled, "").changed() {
                let result = if self.auto_start_enabled {
                    let exe_path = std::env::current_exe()
                        .unwrap()
                        .to_string_lossy()
                        .to_string();
                    AutoStartManager::enable(&exe_path)
                } else {
                    AutoStartManager::disable()
                };
                
                if let Err(e) = result {
                    self.status_message = format!("设置开机自启动失败: {}", e);
                } else {
                    self.config.auto_start_enabled = self.auto_start_enabled;
                    self.save_config();
                    self.status_message = if self.auto_start_enabled {
                        "开机自启动已启用".to_string()
                    } else {
                        "开机自启动已禁用".to_string()
                    };
                }
            }
        });

        ui.separator();
        
        ui.heading("全屏反截屏设置");
        ui.label("启用全屏反截屏保护，创建一个全屏无边框鼠标穿透窗口防止屏幕录制");
        ui.horizontal(|ui| {
            ui.label("启用全屏反截屏:");
            if ui.checkbox(&mut self.fullscreen_anti_screenshot_enabled, "").changed() {
                let result = if self.fullscreen_anti_screenshot_enabled {
                    self.fullscreen_protection.lock().unwrap().enable()
                } else {
                    self.fullscreen_protection.lock().unwrap().disable()
                };

                match result {
                    Ok(_) => {
                        self.config.fullscreen_anti_screenshot_enabled = self.fullscreen_anti_screenshot_enabled;
                        self.save_config();
                        self.status_message = if self.fullscreen_anti_screenshot_enabled {
                            "全屏反截屏已启用".to_string()
                        } else {
                            "全屏反截屏已禁用".to_string()
                        };
                    }
                    Err(e) => {
                        self.status_message = format!("设置全屏反截屏失败: {}", e);
                        self.fullscreen_anti_screenshot_enabled = !self.fullscreen_anti_screenshot_enabled;
                    }
                }
            }
        });

        ui.horizontal(|ui| {
            ui.label("启用连续保护:");
            if ui.checkbox(&mut self.continuous_protection_enabled, "").changed() {
                self.config.continuous_protection_enabled = self.continuous_protection_enabled;
                self.save_config();
            }
        });

        ui.horizontal(|ui| {
            ui.label("保护间隔(秒):");
            if ui.text_edit_singleline(&mut self.fullscreen_interval).lost_focus() {
                self.config.fullscreen_anti_screenshot_interval = self.fullscreen_interval.clone();
                self.save_config();
            }
        });
    }

    fn show_about_tab(&mut self, ui: &mut egui::Ui) {
        ui.vertical(|ui| {
            ui.heading("反截屏管理程序");
            ui.label("版本: 1.0");
            ui.label("");
            ui.label("基于Windows Display Affinity技术和DLL注入的进程窗口反截屏保护工具");
            ui.separator();
            
            ui.label("核心技术特性:");
            ui.label("• 基于DLL注入技术实现反截屏保护");
            ui.label("• 使用多种Affinity DLL防止屏幕录制");
            ui.label("• 支持进程级和窗口级精细控制");
            ui.label("• 多线程实时监控和更新窗口亲和性");
            ui.label("• 支持配置持久化和主题切换");
            ui.label("• 跨平台兼容（Rust实现）");
            
            ui.separator();
            ui.label("DLL功能说明:");
            ui.label("• AffinityHide.dll: 模式二反截屏保护");
            ui.label("• AffinityTrans.dll: 模式一反截屏保护");
            ui.label("• AffinityUnhide.dll: 取消反截屏保护");
            ui.label("• AffinityStatus.dll: 检查进程保护状态");
            
            ui.separator();
            ui.label("技术说明:");
            ui.label("1. 利用Windows API实现DLL远程注入");
            ui.label("2. 通过DLL中的SetWindowDisplayAffinity API设置窗口属性");
            ui.label("3. 使用EnumWindows遍历系统窗口句柄");
            ui.label("4. 多线程异步处理避免界面卡顿");
            ui.label("5. JSON格式配置文件存储用户设置");
            ui.label("6. 基于egui现代UI框架构建");
            
            ui.separator();
            ui.label("致谢:");
            ui.label("这个工具注入的DLL由icer233的DisplayAffinityManager项目生成，在此感谢icer233");
            ui.label("在此基础上进行了封装和扩展，增加了界面和更多功能");
            ui.label("原项目地址：https://github.com/icer233/AntiScreenshotManager");
        });
    }

    fn show_add_dialog(&mut self, ctx: &egui::Context) {
        egui::Window::new("添加项目")
            .collapsible(false)
            .resizable(false)
            .show(ctx, |ui| {
                ui.label("请输入项目名称:");
                ui.text_edit_singleline(&mut self.add_dialog_text);
                
                ui.horizontal(|ui| {
                    if ui.button("确定").clicked() && !self.add_dialog_text.is_empty() {
                        let target_items = if self.add_dialog_target_mode == 1 {
                            &mut self.mode1_items
                        } else {
                            &mut self.mode2_items
                        };
                        
                        if !target_items.iter().any(|item| item.text == self.add_dialog_text) {
                            target_items.push(ListItem {
                                text: self.add_dialog_text.clone(),
                                enabled: true,
                            });
                            self.status_message = format!("已添加到模式{}", self.add_dialog_target_mode);
                            self.save_config();
                        } else {
                            self.status_message = "项目已存在".to_string();
                        }
                        
                        self.show_add_dialog = false;
                        self.add_dialog_text.clear();
                    }
                    
                    if ui.button("取消").clicked() {
                        self.show_add_dialog = false;
                        self.add_dialog_text.clear();
                    }
                });
            });
    }

    fn add_to_current_mode(&mut self, item_text: &str) {
        let target_items = if self.current_mode == 1 {
            &mut self.mode1_items
        } else {
            &mut self.mode2_items
        };

        if !target_items.iter().any(|item| item.text == item_text) {
            target_items.push(ListItem {
                text: item_text.to_string(),
                enabled: true,
            });
            self.status_message = format!("已添加到模式{}", self.current_mode);
            self.save_config();
            self.apply_anti_screenshot_protection();
        } else {
            self.status_message = "项目已存在".to_string();
        }
    }

    fn refresh_windows(&mut self) {
        let window_infos = WindowLoader::load_windows();
        self.windows = window_infos.iter()
            .map(|info| format!("{} [{}]", info.title, info.process_name))
            .collect();
        self.status_message = format!("已加载 {} 个窗口", self.windows.len());
    }

    fn refresh_processes(&mut self) {
        let process_infos = ProcessLoader::load_processes();
        self.processes = process_infos.iter()
            .map(|info| ProcessLoader::format_process_info(info))
            .collect();
        self.status_message = format!("已加载 {} 个进程", self.processes.len());
    }

    fn apply_anti_screenshot_protection(&mut self) {
        let is_mode1 = self.current_mode == 1;
        let items = if is_mode1 {
            &self.mode1_items
        } else {
            &self.mode2_items
        };

        let injector = self.dll_injector.clone();
        let items_clone = items.clone();
        let child_injection = self.child_process_injection_enabled;

        std::thread::spawn(move || {
            let process_infos = ProcessLoader::load_processes();
            let mut injected_count = 0;
            let mut processed_pids = HashSet::new();

            for item in &items_clone {
                if !item.enabled {
                    continue;
                }

                let process_name = Self::extract_process_name(&item.text);

                for proc_info in &process_infos {
                    if proc_info.name == process_name {
                        for &pid in &proc_info.pids {
                            if processed_pids.contains(&pid) {
                                continue;
                            }

                            let result = if is_mode1 {
                                injector.inject_affinity_trans_dll(pid)
                            } else {
                                injector.inject_affinity_hide_dll(pid)
                            };

                            if result.unwrap_or(false) {
                                injected_count += 1;
                                processed_pids.insert(pid);
                            }

                            if child_injection {
                                let children = get_child_processes(pid);
                                for (_child_name, child_pid) in children {
                                    if processed_pids.contains(&child_pid) {
                                        continue;
                                    }

                                    let result = if is_mode1 {
                                        injector.inject_affinity_trans_dll(child_pid)
                                    } else {
                                        injector.inject_affinity_hide_dll(child_pid)
                                    };

                                    if result.unwrap_or(false) {
                                        injected_count += 1;
                                        processed_pids.insert(child_pid);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            println!("已尝试向 {} 个进程注入反截屏保护", injected_count);
        });
    }

    fn extract_process_name(text: &str) -> String {
        if text.contains(" [") && text.ends_with("]") {
            text.split(" [").last().unwrap().trim_end_matches("]").to_string()
        } else if text.contains(" (PID: ") {
            text.split(" (").next().unwrap().to_string()
        } else {
            text.to_string()
        }
    }

    fn save_config(&mut self) {
        self.config.mode1_items = self.mode1_items.iter()
            .map(|item| ConfigItem {
                text: item.text.clone(),
                enabled: item.enabled,
            })
            .collect();

        self.config.mode2_items = self.mode2_items.iter()
            .map(|item| ConfigItem {
                text: item.text.clone(),
                enabled: item.enabled,
            })
            .collect();

        self.config.current_mode = self.current_mode;
        self.config.theme = if self.theme == Theme::Light { "Light".to_string() } else { "Dark".to_string() };

        if let Err(e) = self.data_manager.save(&self.config) {
            self.status_message = format!("保存配置失败: {}", e);
        }
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1000.0, 700.0])
            .with_title("反截屏管理程序"),
        ..Default::default()
    };

    eframe::run_native(
        "反截屏管理程序",
        options,
        Box::new(|cc| {
            if let Ok(font_data) = fs::read("Alibaba-PuHuiTi-Medium.ttf") {
                cc.egui_ctx.set_fonts({
                    let mut fonts = eframe::egui::FontDefinitions::default();
                    fonts.font_data.insert(
                        "Alibaba-PuHuiTi".to_owned(),
                        eframe::egui::FontData::from_owned(font_data),
                    );
                    fonts
                        .families
                        .entry(eframe::egui::FontFamily::Proportional)
                        .or_default()
                        .insert(0, "Alibaba-PuHuiTi".to_owned());
                    fonts
                        .families
                        .entry(eframe::egui::FontFamily::Monospace)
                        .or_default()
                        .insert(0, "Alibaba-PuHuiTi".to_owned());
                    fonts
                });
            }
            Box::new(AntiScreenshotApp::default())
        }),
    )
}