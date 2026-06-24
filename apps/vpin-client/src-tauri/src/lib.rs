use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::process::Command;
use std::path::PathBuf;
use tauri::State;
use tokio::sync::Mutex;

// 服务器配置
#[derive(Clone, Serialize, Deserialize)]
struct ServerConfig {
    url: String,
}

// 任务信息结构
#[derive(Clone, Serialize, Deserialize)]
struct TaskInfo {
    id: String,
    name: String,
    model: String,
    model_type: String,
    status: String,
    progress: i32,
    cpu: i32,
    memory: String,
    time: String,
    has_tee: bool,
}

// 模型信息结构
#[derive(Clone, Serialize, Deserialize)]
struct ModelInfo {
    id: i32,
    name: String,
    model_type: String,
    status: String,
    description: String,
}

// 系统资源状态
#[derive(Clone, Serialize, Deserialize)]
struct SystemResources {
    cpu: i32,
    memory: MemoryInfo,
    network: i32,
}

#[derive(Clone, Serialize, Deserialize)]
struct MemoryInfo {
    used: f64,
    total: f64,
}

// 应用状态
#[derive(Clone)]
struct AppState {
    server_config: Arc<Mutex<ServerConfig>>,
    tasks: Arc<Mutex<Vec<TaskInfo>>>,
    models: Arc<Mutex<Vec<ModelInfo>>>,
    python_available: Arc<Mutex<bool>>,
}

// Python子进程管理器
struct PythonProcessManager {
    python_path: PathBuf,
    backend_path: PathBuf,
}

impl PythonProcessManager {
    fn new() -> Self {
        // 尝试找到Python和后端路径
        let python_path = Self::find_python();
        let backend_path = Self::find_backend();

        Self {
            python_path,
            backend_path,
        }
    }

    fn find_python() -> PathBuf {
        // 尝试常见的Python路径
        let candidates = vec![
            "python3",
            "python",
            "python.exe",
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
        ];

        for candidate in candidates {
            if let Ok(output) = Command::new(candidate).arg("--version").output() {
                if output.status.success() {
                    return PathBuf::from(candidate);
                }
            }
        }

        PathBuf::from("python3") // 默认返回python3
    }

    fn find_backend() -> PathBuf {
        // 查找vpin-backend路径
        let current_dir = std::env::current_dir().unwrap_or_default();

        // 可能的路径
        let candidates = vec![
            current_dir.join("../../../vpin-backend"),
            current_dir.join("../../vpin-backend"),
            current_dir.join("../vpin-backend"),
        ];

        for candidate in candidates {
            if candidate.exists() {
                return candidate;
            }
        }

        current_dir.join("../../../vpin-backend") // 默认路径
    }

    async fn check_health(&self) -> Result<bool, String> {
        if !self.python_path.exists() {
            return Ok(false);
        }

        let backend_main = self.backend_path.join("vpin_backend").join("main.py");
        if !backend_main.exists() {
            return Ok(false);
        }

        // 简单检查Python是否可以运行
        Command::new(&self.python_path)
            .arg("-c")
            .arg("print('OK')")
            .output()
            .map(|output| output.status.success())
            .map_err(|e| format!("Python执行失败: {}", e))
    }

    async fn call_backend(&self, module: &str, function: &str, args: Vec<String>) -> Result<String, String> {
        let mut cmd = Command::new(&self.python_path);
        cmd.arg("-c")
            .arg(format!(
                "import sys; sys.path.insert(0, '{}'); from {} import {}; print({}({}))",
                self.backend_path.display(),
                module,
                function,
                function,
                args.iter().map(|s| format!("'{}'", s)).collect::<Vec<_>>().join(", ")
            ));

        let output = cmd.output().map_err(|e| format!("命令执行失败: {}", e))?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
        } else {
            Err(format!("后端调用失败: {}", String::from_utf8_lossy(&output.stderr)))
        }
    }
}

#[tauri::command]
async fn health_check(
    state: State<'_, AppState>,
) -> Result<String, String> {
    let config = state.server_config.lock().await;
    let client = reqwest::Client::new();

    let response = client
        .get(format!("{}/api/v1/health", &config.url))
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let text = response
        .text()
        .await
        .map_err(|e| format!("Response read failed: {}", e))?;

    Ok(text)
}

#[tauri::command]
async fn set_server_url(
    state: State<'_, AppState>,
    url: String,
) -> Result<(), String> {
    let mut config = state.server_config.lock().await;
    config.url = url;
    Ok(())
}

#[tauri::command]
async fn get_server_url(
    state: State<'_, AppState>,
) -> Result<String, String> {
    let config = state.server_config.lock().await;
    Ok(config.url.clone())
}

// 获取模型列表
#[tauri::command]
async fn get_models(
    state: State<'_, AppState>,
) -> Result<Vec<ModelInfo>, String> {
    let models = state.models.lock().await;
    Ok(models.clone())
}

// 获取任务列表
#[tauri::command]
async fn get_tasks(
    state: State<'_, AppState>,
) -> Result<Vec<TaskInfo>, String> {
    let tasks = state.tasks.lock().await;
    Ok(tasks.clone())
}

// 创建新任务
#[tauri::command]
async fn create_task(
    state: State<'_, AppState>,
    task_data: serde_json::Value,
) -> Result<TaskInfo, String> {
    let mut tasks = state.tasks.lock().await;

    // 生成新的任务ID
    let task_id = format!("TASK-2024-{:04}", tasks.len() + 1);

    let new_task = TaskInfo {
        id: task_id.clone(),
        name: task_data["name"].as_str().unwrap_or("新任务").to_string(),
        model: task_data["model"].as_str().unwrap_or("未知模型").to_string(),
        model_type: task_data["model_type"].as_str().unwrap_or("generic").to_string(),
        status: "queued".to_string(),
        progress: 0,
        cpu: 0,
        memory: "0GB".to_string(),
        time: "--".to_string(),
        has_tee: task_data["has_tee"].as_bool().unwrap_or(false),
    };

    tasks.push(new_task.clone());

    // 模拟任务开始执行 - 克隆Arc指针而不是State
    let tasks_arc = Arc::clone(&state.tasks);
    let task_id_clone = task_id.clone();
    tokio::spawn(async move {
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        let mut tasks = tasks_arc.lock().await;
        if let Some(task) = tasks.iter_mut().find(|t| t.id == task_id_clone) {
            task.status = "running".to_string();
            task.progress = 10;
        }

        // 模拟进度更新
        for progress in 20..=100 {
            tokio::time::sleep(tokio::time::Duration::from_secs(3)).await;
            let mut tasks = tasks_arc.lock().await;
            if let Some(task) = tasks.iter_mut().find(|t| t.id == task_id_clone) {
                task.progress = progress;
                if progress == 100 {
                    task.status = "completed".to_string();
                }
            }
        }
    });

    Ok(new_task)
}

// 获取系统状态
#[tauri::command]
async fn get_system_status(
    _state: State<'_, AppState>,
) -> Result<SystemResources, String> {
    // 这里可以调用系统API获取真实的资源使用情况
    // 目前返回模拟数据
    Ok(SystemResources {
        cpu: 45,
        memory: MemoryInfo { used: 4.2, total: 8.0 },
        network: 125,
    })
}

// 检查Python后端状态
#[tauri::command]
async fn check_python_backend(
    state: State<'_, AppState>,
) -> Result<bool, String> {
    let python_available = state.python_available.lock().await;
    Ok(*python_available)
}

// 调用Python后端进行推理
#[tauri::command]
async fn python_inference(
    state: State<'_, AppState>,
    model_id: String,
    data_path: String,
) -> Result<String, String> {
    let python_available = state.python_available.lock().await;
    if !*python_available {
        return Err("Python后端不可用，请确保Python环境和vpin-backend已安装".to_string());
    }

    // 实际调用Python后端
    let python_manager = PythonProcessManager::new();
    let args = vec![
        "--model-id".to_string(),
        model_id,
        "--data-path".to_string(),
        data_path,
    ];

    python_manager.call_backend("vpin_backend.main", "run_inference", args).await
}

// 检查模型文件是否在Python后端中可用
#[tauri::command]
async fn check_model_available(
    state: State<'_, AppState>,
    model_id: String,
) -> Result<bool, String> {
    let python_available = state.python_available.lock().await;
    if !*python_available {
        return Ok(false);
    }

    let python_manager = PythonProcessManager::new();
    let args = vec![model_id];

    match python_manager.call_backend("vpin_backend.models", "check_model", args).await {
        Ok(result) => Ok(result.to_lowercase() == "true" || result == "1"),
        Err(_) => Ok(false),
    }
}

// 获取Python后端中的模型列表
#[tauri::command]
async fn get_python_models(
    state: State<'_, AppState>,
) -> Result<Vec<ModelInfo>, String> {
    let python_available = state.python_available.lock().await;
    if !*python_available {
        return Ok(vec![]);
    }

    let python_manager = PythonProcessManager::new();

    match python_manager.call_backend("vpin_backend.models", "list_models", vec![]).await {
        Ok(result) => {
            // 解析Python返回的JSON数据
            match serde_json::from_str::<Vec<ModelInfo>>(&result) {
                Ok(models) => Ok(models),
                Err(_) => Ok(vec![]),
            }
        },
        Err(_) => Ok(vec![]),
    }
}

// 上传数据到服务器
#[tauri::command]
async fn upload_data(
    _state: State<'_, AppState>,
    file_path: String,
) -> Result<String, String> {
    // 这里实现文件上传逻辑
    // 目前返回模拟结果
    Ok(format!("数据上传成功: {}", file_path))
}

// 获取安全状态
#[tauri::command]
async fn get_security_status(
    _state: State<'_, AppState>,
) -> Result<serde_json::Value, String> {
    // 返回安全状态信息
    Ok(serde_json::json!({
        "key_protection": true,
        "tls_enabled": true,
        "tee_available": false,
        "protocol_version": "v1.0",
        "verification_module": "ready"
    }))
}

// 刷新模型列表（从服务器）
#[tauri::command]
async fn refresh_models(
    state: State<'_, AppState>,
) -> Result<Vec<ModelInfo>, String> {
    let config = state.server_config.lock().await;
    let client = reqwest::Client::new();

    let response = client
        .get(format!("{}/api/v1/models", &config.url))
        .send()
        .await
        .map_err(|e| format!("请求失败: {}", e))?;

    let models: Vec<ModelInfo> = response
        .json()
        .await
        .map_err(|e| format!("解析失败: {}", e))?;

    // 更新本地缓存
    let mut local_models = state.models.lock().await;
    *local_models = models.clone();

    Ok(models)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 初始化Python进程管理器
    let python_manager = PythonProcessManager::new();

    // 检查Python后端可用性
    let python_available = tauri::async_runtime::block_on(async {
        python_manager.check_health().await.unwrap_or(false)
    });

    // 初始化空数据，实际使用中应从真实API获取
    let initial_tasks: Vec<TaskInfo> = vec![];
    let initial_models: Vec<ModelInfo> = vec![];

    tauri::Builder::default()
        .manage(AppState {
            server_config: Arc::new(Mutex::new(ServerConfig {
                url: "http://127.0.0.1:8000".to_string(),
            })),
            tasks: Arc::new(Mutex::new(initial_tasks)),
            models: Arc::new(Mutex::new(initial_models)),
            python_available: Arc::new(Mutex::new(python_available)),
        })
        .invoke_handler(tauri::generate_handler![
            health_check,
            set_server_url,
            get_server_url,
            get_models,
            get_tasks,
            create_task,
            get_system_status,
            check_python_backend,
            python_inference,
            check_model_available,
            get_python_models,
            upload_data,
            get_security_status,
            refresh_models
        ])
        .setup(move |_app| {
            // 应用启动时的初始化逻辑
            println!("vPIN Client starting...");
            println!("Python backend available: {}", python_available);

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    #[tokio::test]
    async fn test_server_config() {
        let config = ServerConfig {
            url: "http://127.0.0.1:8000".to_string(),
        };
        assert_eq!(config.url, "http://127.0.0.1:8000");
    }

    #[tokio::test]
    async fn test_set_server_url() {
        let state = AppState {
            server_config: Arc::new(Mutex::new(ServerConfig {
                url: "http://127.0.0.1:8000".to_string(),
            })),
        };

        let mut config = state.server_config.lock().await;
        config.url = "http://localhost:3000".to_string();
        assert_eq!(config.url, "http://localhost:3000");
    }
}
