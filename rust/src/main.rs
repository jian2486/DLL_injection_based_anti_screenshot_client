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
use std::sync::{Arc, Mutex, mpsc};
use std::collections::HashSet;
use std::fs;
use std::time::Instant;

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
    injection_receiver: mpsc::Receiver<String>,
    injection_sender: mpsc::Sender<String>,
    last_refresh_time: Instant,
    hover_key: Option<(i32, usize)>,
    hover_start: Option<Instant>,
    hover_tooltip: Option<String>,
}

#[derive(Clone, Debug)]
struct ListItem {
    text: String,
    process_path: String,
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
                process_path: item.process_path.clone(),
                enabled: item.enabled,
            })
            .collect();

        let mode2_items: Vec<ListItem> = config.mode2_items.iter()
            .map(|item| ListItem {
                text: item.text.clone(),
                process_path: item.process_path.clone(),
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

        let (injection_sender, injection_receiver) = mpsc::channel();

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
            injection_receiver,
            injection_sender,
            last_refresh_time: Instant::now(),
            hover_key: None,
            hover_start: None,
            hover_tooltip: None,
        }
    }
}

impl eframe::App for AntiScreenshotApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        while let Ok(msg) = self.injection_receiver.try_recv() {
            self.status_message = msg;
        }
        
        if self.last_refresh_time.elapsed().as_secs() >= 3 {
            self.refresh_windows();
            self.refresh_processes();
            self.last_refresh_time = Instant::now();
        }
        
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
        
        egui::SidePanel::left("left_panel")
            .min_width(180.0)
            .default_width(280.0)
            .show(ctx, |ui| {
            ui.heading("模式一");
            let mode1_items = std::mem::take(&mut self.mode1_items);
            let mode2_items_snapshot = self.mode2_items.clone();
            self.show_mode_list(ui, mode1_items, 1, &process_infos, &mode2_items_snapshot);
            
            ui.separator();
            
            ui.heading("模式二");
            let mode2_items = std::mem::take(&mut self.mode2_items);
            let mode1_items_snapshot = self.mode1_items.clone();
            self.show_mode_list(ui, mode2_items, 2, &process_infos, &mode1_items_snapshot);
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

        if let (Some(start), Some(tooltip)) = (&self.hover_start, &self.hover_tooltip) {
            if start.elapsed().as_millis() >= 200 {
                let pointer = ctx.input(|i| i.pointer.latest_pos());
                if let Some(pos) = pointer {
                    let frame = egui::Frame::popup(&ctx.style());
                    egui::Area::new(egui::Id::new("list_tooltip"))
                        .pivot(egui::Align2::LEFT_TOP)
                        .fixed_pos(pos + egui::vec2(12.0, 12.0))
                        .order(egui::Order::Tooltip)
                        .show(ctx, |ui| {
                            frame.show(ui, |ui| {
                                for line in tooltip.split('\n') {
                                    ui.label(line);
                                }
                            });
                        });
                }
            }
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

    fn show_mode_list(&mut self, ui: &mut egui::Ui, mut items: Vec<ListItem>, mode: i32, process_infos: &[loader::ProcessInfo], other_items: &[ListItem]) {
        let mut items_to_remove = Vec::new();
        let mut toggled_item: Option<(String, String, bool)> = None;
        
        ui.vertical(|ui| {
            for (idx, item) in items.iter_mut().enumerate() {
                let process_name = &item.text;
                let process_path = &item.process_path;
                let matched_info = process_infos.iter().find(|proc_info| {
                    proc_info.name == process_name.as_str() && Self::paths_match(process_path, &proc_info.path)
                });
                let running_count = matched_info.map(|proc_info| proc_info.count).unwrap_or(0);

                let dir_name = if process_path.is_empty() {
                    String::new()
                } else if let Some(pos) = process_path.rfind('\\') {
                    let dir = &process_path[..pos];
                    if let Some(dir_pos) = dir.rfind('\\') {
                        dir[dir_pos + 1..].to_string()
                    } else {
                        dir.to_string()
                    }
                } else {
                    String::new()
                };

                let other_enabled = other_items.iter().any(|oi| {
                    oi.text == *process_name && Self::paths_match(process_path, &oi.process_path) && oi.enabled
                });
                let other_mode = if mode == 1 { 2 } else { 1 };
                let blocked_by_other = other_enabled && other_mode < mode;

                let status_text = if running_count > 0 {
                    format!("{} 个实例", running_count)
                } else {
                    "未运行".to_string()
                };

                let display_text = if blocked_by_other {
                    if dir_name.is_empty() {
                        format!("● {} (模式{}已启用)", process_name, other_mode)
                    } else {
                        format!("● {} [{}] (模式{}已启用)", process_name, dir_name, other_mode)
                    }
                } else if item.enabled {
                    if dir_name.is_empty() {
                        format!("{} ({})", process_name, status_text)
                    } else {
                        format!("{} [{}] ({})", process_name, dir_name, status_text)
                    }
                } else {
                    if dir_name.is_empty() {
                        format!("● {} ({})", process_name, status_text)
                    } else {
                        format!("● {} [{}] ({})", process_name, dir_name, status_text)
                    }
                };

                let tooltip_text = {
                    let mut lines = vec![format!("进程名: {}", process_name)];
                    if !process_path.is_empty() {
                        lines.push(format!("完整路径: {}", process_path));
                    }
                    lines.push(format!("状态: {}", if running_count > 0 { format!("运行中 ({} 个实例)", running_count) } else { "未运行".to_string() }));
                    lines.push(format!("模式: 模式{}", mode));
                    if other_enabled {
                        lines.push(format!("启用: 被模式{}占用", other_mode));
                    } else {
                        lines.push(format!("启用: {}", if item.enabled { "是" } else { "否" }));
                    }
                    if let Some(info) = matched_info {
                        if !info.pids.is_empty() {
                            lines.push(format!("PID: {}", info.pids.iter().map(|p| p.to_string()).collect::<Vec<_>>().join(", ")));
                        }
                    }
                    lines.join("\n")
                };
                
                ui.group(|ui| {
                    ui.horizontal(|ui| {
                        if other_enabled {
                            item.enabled = false;
                            ui.add_enabled(false, egui::Checkbox::new(&mut false, ""));
                        } else {
                            let mut enabled = item.enabled;
                            if ui.checkbox(&mut enabled, "").changed() {
                                item.enabled = enabled;
                                toggled_item = Some((item.text.clone(), item.process_path.clone(), enabled));
                            }
                        }

                        let delete_button_width = 28.0;
                        let available = ui.available_width() - delete_button_width;
                        let font_id = egui::TextStyle::Body.resolve(ui.style());
                        let truncated = Self::truncate_text_to_width(ui, &display_text, available, &font_id);
                        
                        let label_response = if running_count > 0 {
                            ui.colored_label(egui::Color32::from_rgb(100, 200, 100), &truncated)
                        } else {
                            ui.colored_label(egui::Color32::from_rgb(200, 100, 100), &truncated)
                        };

                        if label_response.hovered() {
                            let key = (mode, idx);
                            if self.hover_key != Some(key) {
                                self.hover_key = Some(key);
                                self.hover_start = Some(Instant::now());
                            }
                            self.hover_tooltip = Some(tooltip_text.clone());
                        } else if self.hover_key == Some((mode, idx)) {
                            self.hover_key = None;
                            self.hover_start = None;
                            self.hover_tooltip = None;
                        }
                        
                        if ui.small_button("×").clicked() {
                            items_to_remove.push((idx, item.text.clone(), item.process_path.clone()));
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
                    let other_mode = if mode == 1 { 2 } else { 1 };
                    let pids_to_uninject: Vec<u32> = items.iter()
                        .flat_map(|item| {
                            let item_path = item.process_path.clone();
                            let item_name = item.text.clone();
                            let has_other = other_items.iter().any(|oi| oi.text == item_name && Self::paths_match(&item_path, &oi.process_path) && oi.enabled);
                            if has_other {
                                Vec::new()
                            } else {
                                process_infos.iter()
                                    .filter(move |proc_info| proc_info.name == item_name && Self::paths_match(&item_path, &proc_info.path))
                                    .flat_map(|proc_info| proc_info.pids.clone())
                                    .collect::<Vec<u32>>()
                            }
                        })
                        .collect();
                    
                    let pids_to_switch: Vec<u32> = items.iter()
                        .flat_map(|item| {
                            let item_path = item.process_path.clone();
                            let item_name = item.text.clone();
                            let has_other = other_items.iter().any(|oi| oi.text == item_name && Self::paths_match(&item_path, &oi.process_path) && oi.enabled);
                            if has_other {
                                process_infos.iter()
                                    .filter(move |proc_info| proc_info.name == item_name && Self::paths_match(&item_path, &proc_info.path))
                                    .flat_map(|proc_info| proc_info.pids.clone())
                                    .collect::<Vec<u32>>()
                            } else {
                                Vec::new()
                            }
                        })
                        .collect();

                    let sender = self.injection_sender.clone();
                    std::thread::spawn(move || {
                        let injector = DLLInjector::new();
                        let mut count = 0u32;
                        for pid in pids_to_uninject {
                            if injector.inject_affinity_unhide_dll(pid).unwrap_or(false) {
                                count += 1;
                            }
                        }
                        for pid in pids_to_switch {
                            let result = if other_mode == 1 {
                                injector.inject_affinity_trans_dll(pid)
                            } else {
                                injector.inject_affinity_hide_dll(pid)
                            };
                            if result.unwrap_or(false) {
                                count += 1;
                            }
                        }
                        let _ = sender.send(format!("已处理 {} 个进程", count));
                    });
                    
                    items.clear();
                    self.status_message = format!("正在清除模式{}的反截屏保护...", mode);
                    self.save_config();
                }
            });
        });

        items_to_remove.sort_by(|a, b| b.0.cmp(&a.0));
        for (idx, name, path) in items_to_remove.into_iter() {
            let other_mode = if mode == 1 { 2 } else { 1 };
            let has_other = other_items.iter().any(|oi| oi.text == name && Self::paths_match(&path, &oi.process_path) && oi.enabled);
            let pids: Vec<u32> = process_infos.iter()
                .filter(|proc_info| proc_info.name == name && Self::paths_match(&path, &proc_info.path))
                .flat_map(|proc_info| proc_info.pids.clone())
                .collect();
            
            let sender = self.injection_sender.clone();
            std::thread::spawn(move || {
                let injector = DLLInjector::new();
                let mut count = 0u32;
                for pid in pids {
                    let result = if has_other {
                        if other_mode == 1 {
                            injector.inject_affinity_trans_dll(pid)
                        } else {
                            injector.inject_affinity_hide_dll(pid)
                        }
                    } else {
                        injector.inject_affinity_unhide_dll(pid)
                    };
                    if result.unwrap_or(false) {
                        count += 1;
                    }
                }
                if has_other {
                    let _ = sender.send(format!("已从模式{}移除，模式{}保护仍生效（{} 个进程）", other_mode, other_mode, count));
                } else {
                    let _ = sender.send(format!("已取消 {} 个进程的反截屏保护", count));
                }
            });
            
            items.remove(idx);
        }

        if let Some((item_name, item_path, enabled)) = toggled_item {
            let pids: Vec<u32> = process_infos.iter()
                .filter(|proc_info| proc_info.name == item_name && Self::paths_match(&item_path, &proc_info.path))
                .flat_map(|proc_info| proc_info.pids.clone())
                .collect();

            let other_enabled = other_items.iter().any(|item| {
                item.text == item_name && Self::paths_match(&item_path, &item.process_path) && item.enabled
            });
            let other_mode = if mode == 1 { 2 } else { 1 };

            let injector = self.dll_injector.clone();
            let sender = self.injection_sender.clone();
            let mode_val = mode;
            let child_injection = self.child_process_injection_enabled;
            let process_name = item_name.clone();

            std::thread::spawn(move || {
                let mut all_pids = pids.clone();
                if child_injection {
                    for &pid in &pids {
                        let children = get_child_processes(pid);
                        for (_, child_pid) in children {
                            if !all_pids.contains(&child_pid) {
                                all_pids.push(child_pid);
                            }
                        }
                    }
                }

                let mut count = 0u32;
                let total_pids = all_pids.len();
                for pid in all_pids {
                    let result = if enabled {
                        if other_enabled && other_mode == 2 {
                            injector.inject_affinity_hide_dll(pid)
                        } else if mode_val == 1 {
                            injector.inject_affinity_trans_dll(pid)
                        } else {
                            injector.inject_affinity_hide_dll(pid)
                        }
                    } else if other_enabled {
                        if other_mode == 1 {
                            injector.inject_affinity_trans_dll(pid)
                        } else {
                            injector.inject_affinity_hide_dll(pid)
                        }
                    } else {
                        injector.inject_affinity_unhide_dll(pid)
                    };
                    if result.unwrap_or(false) {
                        count += 1;
                    }
                }

                let msg = if enabled {
                    if count > 0 {
                        if other_enabled {
                            format!("模式{}：已为 {} 个进程启用反截屏保护（模式{}同时生效）", mode_val, count, other_mode)
                        } else {
                            format!("模式{}：已为 {} 个进程启用反截屏保护", mode_val, count)
                        }
                    } else if total_pids == 0 {
                        format!("模式{}：未找到运行中的进程 {}", mode_val, process_name)
                    } else {
                        format!("模式{}：向 {} 注入DLL失败（共{}个进程）", mode_val, process_name, total_pids)
                    }
                } else {
                    if count > 0 {
                        if other_enabled {
                            format!("模式{}：已取消，模式{}保护仍生效（{} 个进程）", mode_val, other_mode, count)
                        } else {
                            format!("模式{}：已为 {} 个进程取消反截屏保护", mode_val, count)
                        }
                    } else if total_pids == 0 {
                        format!("模式{}：未找到运行中的进程 {}", mode_val, process_name)
                    } else {
                        format!("模式{}：向 {} 取消注入DLL失败（共{}个进程）", mode_val, process_name, total_pids)
                    }
                };
                let _ = sender.send(msg);
            });

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
                        let (process_name, process_path) = Self::extract_process_name_and_path(&self.add_dialog_text);
                        let target_items = if self.add_dialog_target_mode == 1 {
                            &mut self.mode1_items
                        } else {
                            &mut self.mode2_items
                        };
                        
                        if !target_items.iter().any(|item| item.text == process_name && item.process_path == process_path) {
                            target_items.push(ListItem {
                                text: process_name.clone(),
                                process_path: process_path.clone(),
                                enabled: true,
                            });
                            self.status_message = format!("已添加 {} 到模式{}", process_name, self.add_dialog_target_mode);
                            self.save_config();
                            self.apply_anti_screenshot_protection();
                        } else {
                            self.status_message = format!("{} 已存在于模式{}", process_name, self.add_dialog_target_mode);
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
        let (process_name, process_path) = Self::extract_process_name_and_path(item_text);

        let target_items = if self.current_mode == 1 {
            &mut self.mode1_items
        } else {
            &mut self.mode2_items
        };

        if !target_items.iter().any(|item| item.text == process_name && item.process_path == process_path) {
            target_items.push(ListItem {
                text: process_name.clone(),
                process_path: process_path.clone(),
                enabled: true,
            });
            self.status_message = format!("已添加 {} 到模式{}", process_name, self.current_mode);
            self.save_config();
            self.apply_anti_screenshot_protection();
        } else {
            self.status_message = format!("{} 已存在于模式{}", process_name, self.current_mode);
        }
    }

    fn refresh_windows(&mut self) {
        let window_infos = WindowLoader::load_windows();
        self.windows = window_infos.iter()
            .map(|info| WindowLoader::format_window_info(info))
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
        let other_items = if is_mode1 {
            &self.mode2_items
        } else {
            &self.mode1_items
        };

        let injector = self.dll_injector.clone();
        let items_clone = items.clone();
        let other_clone = other_items.clone();
        let child_injection = self.child_process_injection_enabled;
        let sender = self.injection_sender.clone();
        let mode = self.current_mode;

        std::thread::spawn(move || {
            let process_infos = ProcessLoader::load_processes();
            let mut injected_count = 0;
            let mut processed_pids = HashSet::new();

            for item in &items_clone {
                if !item.enabled {
                    continue;
                }

                let process_name = &item.text;
                let process_path = &item.process_path;

                let other_enabled = other_clone.iter().any(|oi| {
                    oi.text == *process_name && Self::paths_match(&oi.process_path, process_path) && oi.enabled
                });

                for proc_info in &process_infos {
                    if proc_info.name == *process_name && Self::paths_match(process_path, &proc_info.path) {
                        for &pid in &proc_info.pids {
                            if processed_pids.contains(&pid) {
                                continue;
                            }

                            let result = if other_enabled && !is_mode1 {
                                injector.inject_affinity_hide_dll(pid)
                            } else if is_mode1 {
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

                                    let result = if other_enabled && !is_mode1 {
                                        injector.inject_affinity_hide_dll(child_pid)
                                    } else if is_mode1 {
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

            let msg = if injected_count > 0 {
                format!("模式{}：成功向 {} 个进程注入反截屏保护", mode, injected_count)
            } else {
                format!("模式{}：未找到匹配的运行中进程，注入失败", mode)
            };
            let _ = sender.send(msg);
        });
    }

    fn paths_match(stored_path: &str, actual_path: &str) -> bool {
        if stored_path.is_empty() {
            return true;
        }
        stored_path.eq_ignore_ascii_case(actual_path)
    }

    fn extract_process_name_and_path(text: &str) -> (String, String) {
        let mut path = String::new();

        if text.contains(" {") && text.ends_with("}") {
            let brace_start = text.rfind(" {").unwrap();
            path = text[brace_start + 2..text.len() - 1].to_string();
            let remaining = &text[..brace_start];

            if remaining.contains(" [") && remaining.ends_with("]") {
                let name = remaining.split(" [").last().unwrap().trim_end_matches("]").to_string();
                return (name, path);
            }
            return (remaining.to_string(), path);
        }

        if text.contains(" [") && text.ends_with("]") {
            let bracket_pos = text.rfind(" [").unwrap();
            path = text[bracket_pos + 2..text.len() - 1].to_string();
            let remaining = &text[..bracket_pos];

            if remaining.contains(" (") {
                let name = remaining.split(" (").next().unwrap().to_string();
                return (name, path);
            }
            let name = text.split(" [").last().unwrap().trim_end_matches("]").to_string();
            return (name, path);
        }

        if text.contains(" [") && text.contains("]") {
            let bracket_start = text.find(" [").unwrap();
            let bracket_end = text.find("]").unwrap();
            if bracket_end > bracket_start {
                let name = text[bracket_start + 2..bracket_end].to_string();
                return (name, path);
            }
        }

        if text.contains(" (PID: ") || text.contains(" (") && text.contains(" 个实例)") {
            let name = text.split(" (").next().unwrap().to_string();
            return (name, path);
        }

        (text.to_string(), String::new())
    }

    fn truncate_text_to_width(ui: &egui::Ui, text: &str, max_width: f32, font_id: &egui::FontId) -> String {
        if max_width <= 0.0 {
            return "…".to_string();
        }

        let ellipsis_width = ui.fonts(|f| f.glyph_width(font_id, '…'));

        let mut total_width = 0.0f32;
        let mut char_count = 0;

        for ch in text.chars() {
            let char_width = ui.fonts(|f| f.glyph_width(font_id, ch));
            if total_width + char_width + ellipsis_width > max_width {
                let truncated: String = text.chars().take(char_count).collect();
                return format!("{}…", truncated);
            }
            total_width += char_width;
            char_count += 1;
        }

        text.to_string()
    }

    fn extract_process_name(text: &str) -> String {
        Self::extract_process_name_and_path(text).0
    }

    fn save_config(&mut self) {
        self.config.mode1_items = self.mode1_items.iter()
            .map(|item| ConfigItem {
                text: item.text.clone(),
                process_path: item.process_path.clone(),
                enabled: item.enabled,
            })
            .collect();

        self.config.mode2_items = self.mode2_items.iter()
            .map(|item| ConfigItem {
                text: item.text.clone(),
                process_path: item.process_path.clone(),
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
    let icon = fs::read("favicon.ico").ok().and_then(|data| {
        let icon_dir = ico::IconDir::read(std::io::Cursor::new(data)).ok()?;
        let entry = icon_dir.entries().first()?;
        let size = entry.width();
        let rgba = entry.decode().ok()?.rgba_data().to_vec();
        Some(egui::IconData {
            rgba,
            width: size as u32,
            height: size as u32,
        })
    });

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1000.0, 700.0])
            .with_title("反截屏管理程序")
            .with_icon(icon.unwrap_or_else(|| egui::IconData::default())),
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