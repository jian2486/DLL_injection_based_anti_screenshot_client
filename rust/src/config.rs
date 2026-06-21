use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub theme: String,
    #[serde(default)]
    pub mode1_items: Vec<ConfigItem>,
    #[serde(default)]
    pub mode2_items: Vec<ConfigItem>,
    #[serde(default = "default_current_mode")]
    pub current_mode: i32,
    #[serde(default)]
    pub child_process_injection_enabled: bool,
    #[serde(default)]
    pub auto_start_enabled: bool,
    #[serde(default)]
    pub fullscreen_anti_screenshot_enabled: bool,
    #[serde(default = "default_fullscreen_interval")]
    pub fullscreen_anti_screenshot_interval: String,
    #[serde(default = "default_continuous_protection")]
    pub continuous_protection_enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigItem {
    pub text: String,
    #[serde(default)]
    pub process_path: String,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_current_mode() -> i32 {
    1
}

fn default_enabled() -> bool {
    true
}

fn default_fullscreen_interval() -> String {
    "0.1".to_string()
}

fn default_continuous_protection() -> bool {
    true
}

impl Default for Config {
    fn default() -> Self {
        Self {
            theme: "Dark".to_string(),
            mode1_items: Vec::new(),
            mode2_items: Vec::new(),
            current_mode: 1,
            child_process_injection_enabled: false,
            auto_start_enabled: false,
            fullscreen_anti_screenshot_enabled: false,
            fullscreen_anti_screenshot_interval: "0.1".to_string(),
            continuous_protection_enabled: false,
        }
    }
}

pub struct DataManager {
    config_path: PathBuf,
}

impl DataManager {
    pub fn new() -> Result<Self> {
        let config_path = std::env::current_exe()?
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("config.json");

        Ok(Self { config_path })
    }

    pub fn save(&self, config: &Config) -> Result<()> {
        let json = serde_json::to_string_pretty(config)
            .context("序列化配置失败")?;

        fs::write(&self.config_path, json)
            .context("写入配置文件失败")?;

        println!("配置已保存到 {:?}", self.config_path);
        Ok(())
    }

    pub fn load(&self) -> Result<Config> {
        if !self.config_path.exists() {
            println!("配置文件不存在，使用默认配置");
            return Ok(Config::default());
        }

        let content = fs::read_to_string(&self.config_path)
            .context("读取配置文件失败")?;

        let config: Config = serde_json::from_str(&content)
            .context("解析配置文件失败")?;

        println!("配置加载成功");
        Ok(config)
    }
}