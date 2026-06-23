// Tauri bridge → vpin_client.pipeline (L4). Inference never runs on the backend HTTP layer.

use std::path::PathBuf;
use std::process::Command;

fn repo_root() -> PathBuf {
    let mut dir = std::env::current_dir().expect("cwd");
    for _ in 0..6 {
        if dir.join("vpin-client").is_dir() && dir.join(".venv").is_dir() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .unwrap_or(&PathBuf::from("."))
        .to_path_buf()
}

fn venv_python() -> PathBuf {
    repo_root().join(".venv").join("Scripts").join("python.exe")
}

fn run_python_json(args: &[&str]) -> Result<String, String> {
    let python = venv_python();
    if !python.is_file() {
        return Err(format!("venv python not found: {}", python.display()));
    }
    let out = Command::new(&python)
        .args(args)
        .current_dir(repo_root())
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!(
            "python failed: {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

#[tauri::command]
fn ahe_preprocess(mnist_index: u32) -> Result<serde_json::Value, String> {
    let script = format!(
        "import json; from vpin_client.data.official import load_official_test; from vpin_client.data.core import preprocess_result_to_dict; print(json.dumps(preprocess_result_to_dict(load_official_test({}))))",
        mnist_index
    );
    let out = run_python_json(&["-c", &script])?;
    serde_json::from_str(&out).map_err(|e| e.to_string())
}

#[tauri::command]
async fn preprocess_upload_file(path: String) -> Result<serde_json::Value, String> {
    let script = format!(
        "import json; from pathlib import Path; from vpin_client.data.upload import preprocess_upload_path; from vpin_client.data.core import preprocess_result_to_dict; print(json.dumps(preprocess_result_to_dict(preprocess_upload_path(Path(r'{}')))))",
        path.replace('\'', "''")
    );
    let out = tauri::async_runtime::spawn_blocking(move || run_python_json(&["-c", &script]))
        .await
        .map_err(|e| e.to_string())??;
    serde_json::from_str(&out).map_err(|e| e.to_string())
}

fn build_ahe_infer_args(
    mnist_index: Option<u32>,
    upload_id: Option<String>,
    image_path: Option<String>,
    backend_ws: String,
    model_id: String,
) -> Vec<String> {
    let idx_s = mnist_index
        .map(|idx| idx.to_string())
        .unwrap_or_else(|| "0".to_string());
    let mut args = vec![
        "-m".into(),
        "vpin_client".into(),
        "ahe-infer".into(),
        "--backend".into(),
        backend_ws,
        "--model".into(),
        model_id,
        "--timing".into(),
    ];
    if let Some(path) = image_path {
        args.push("--image".into());
        args.push(path);
    } else if let Some(id) = upload_id {
        args.push("--upload-id".into());
        args.push(id);
    } else {
        args.push("--mnist-index".into());
        args.push(idx_s);
    }
    args
}

/// Runs vpin_client.pipeline via CLI (`ahe-infer` → `run_ahe_inference`).
#[tauri::command]
async fn run_ahe_inference(
    mnist_index: Option<u32>,
    upload_id: Option<String>,
    image_path: Option<String>,
    backend_ws: String,
    model_id: String,
) -> Result<serde_json::Value, String> {
    let args = build_ahe_infer_args(
        mnist_index,
        upload_id,
        image_path,
        backend_ws,
        model_id,
    );
    let out = tauri::async_runtime::spawn_blocking(move || {
        let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
        run_python_json(&arg_refs)
    })
    .await
    .map_err(|e| e.to_string())??;
    serde_json::from_str(&out).map_err(|e| e.to_string())
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            ahe_preprocess,
            preprocess_upload_file,
            run_ahe_inference
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
