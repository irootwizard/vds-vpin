use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tauri::State;
use tokio::sync::Mutex;

#[derive(Clone, Serialize, Deserialize)]
struct ServerConfig {
    url: String,
}

#[derive(Clone)]
struct AppState {
    server_config: Arc<Mutex<ServerConfig>>,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            server_config: Arc::new(Mutex::new(ServerConfig {
                url: "http://127.0.0.1:8000".to_string(),
            })),
        })
        .invoke_handler(tauri::generate_handler![
            health_check,
            set_server_url,
            get_server_url
        ])
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
