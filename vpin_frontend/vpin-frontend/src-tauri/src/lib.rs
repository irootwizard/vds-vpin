// Tauri bridge → vpin_client.pipeline (L4). Inference never runs on the backend HTTP layer.

use std::path::PathBuf;
use std::process::{Command as StdCommand, Stdio};
use regex::Regex;
use tauri::Emitter;
use tokio::process::Command;
use tokio::io::{AsyncBufReadExt, BufReader};

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
    let out = StdCommand::new(&python)
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
        "--trace".into(),
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

/// Runs batch AHE inference with streaming progress updates.
#[tauri::command]
async fn run_ahe_batch(
    start_index: u32,
    limit: u32,
    concurrency: u32,
    backend_ws: String,
    model_id: String,
    window: tauri::Window,
) -> Result<serde_json::Value, String> {
    let python = venv_python();
    if !python.is_file() {
        return Err(format!("Python not found: {}", python.display()));
    }

    let mut args = vec![
        "-m".into(),
        "vpin_client".into(),
        "eval-mnist-ahe".into(),
        "--backend".into(),
        backend_ws,
        "--model".into(),
        model_id,
        "--start-index".into(),
        start_index.to_string(),
        "--limit".into(),
        limit.to_string(),
        "--concurrency".into(),
        concurrency.to_string(),
        "--progress".into(),
    ];

    // Spawn child process with piped stdout
    let mut child = Command::new(&python)
        .args(&args)
        .current_dir(repo_root())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn Python process: {}", e))?;

    let stdout = child.stdout.take().ok_or("Failed to capture stdout")?;
    let stderr = child.stderr.take().ok_or("Failed to capture stderr")?;
    let mut reader = BufReader::new(stdout);
    let mut stderr_reader = BufReader::new(stderr);

    // Spawn a task to read stderr and log it
    tauri::async_runtime::spawn(async move {
        let mut lines = String::new();
        let mut line = String::new();
        while let Ok(n) = stderr_reader.read_line(&mut line).await {
            if n == 0 { break; }
            lines.push_str(&line);
            line.clear();
        }
        if !lines.is_empty() {
            eprintln!("stderr from eval-mnist-ahe:\n{}", lines);
        }
    });

    // Read stdout line by line for progress updates
    let mut report_path: Option<String> = None;
    let progress_regex = Regex::new(r"\[\s*(\d+)/(\d+)\s*\]\s*correct=(\d+)\s*acc=([\d.]+)%?\s*elapsed=(\d+)s?\s*eta=(\d+)s?")
        .map_err(|e| format!("Failed to compile regex: {}", e))?;

    let mut line = String::new();
    while let Ok(n) = reader.read_line(&mut line).await {
        if n == 0 { break; }

        // Parse progress line: [ i/N ] correct=n acc=p% elapsed=s eta=s
        if let Some(caps) = progress_regex.captures(&line) {
            if let (Some(idx_str), Some(limit_str), Some(correct_str), Some(acc_str), Some(elapsed_str), Some(eta_str)) = (
                caps.get(1), caps.get(2), caps.get(3), caps.get(4), caps.get(5), caps.get(6)
            ) {
                let idx: u32 = idx_str.as_str().parse().unwrap_or(0);
                let limit_val: u32 = limit_str.as_str().parse().unwrap_or(0);
                let correct: u32 = correct_str.as_str().parse().unwrap_or(0);
                let accuracy: f64 = acc_str.as_str().parse().unwrap_or(0.0) / 100.0;
                let elapsed: u32 = elapsed_str.as_str().parse().unwrap_or(0);
                let eta: u32 = eta_str.as_str().parse().unwrap_or(0);

                let _ = window.emit("ahe-batch-progress", serde_json::json!({
                    "index": idx,
                    "limit": limit_val,
                    "correct": correct,
                    "accuracy": accuracy,
                    "elapsed_s": elapsed,
                    "eta_s": eta
                }));
            }
        }

        // Capture report path: "Wrote reports/batch_....json"
        if line.contains("Wrote reports/batch_") {
            if let Some(path_part) = line.strip_prefix("Wrote ") {
                report_path = Some(path_part.trim().to_string());
            }
        }

        line.clear();
    }

    // Wait for process to complete
    let status = child.wait().await.map_err(|e| format!("Failed to wait for process: {}", e))?;
    if !status.success() {
        return Err(format!("Batch process failed with exit code: {:?}", status.code()));
    }

    // Read and parse the report JSON
    if let Some(path) = report_path {
        let report_file = repo_root().join(&path);
        let content = std::fs::read_to_string(&report_file)
            .map_err(|e| format!("Failed to read report file {}: {}", path, e))?;

        // Parse JSON and return
        serde_json::from_str(&content).map_err(|e| format!("Failed to parse report JSON: {}", e))
    } else {
        Err("No report file path found in output".to_string())
    }
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
            run_ahe_inference,
            run_ahe_batch
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
