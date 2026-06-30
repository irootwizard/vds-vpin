// Tauri bridge → Python vpin_client or Rust ahe-cli (L4). Streams progress via events.

use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex, MutexGuard};

static INFER_SUBPROCESS_LOCK: Mutex<()> = Mutex::new(());

use serde::Deserialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter};

fn repo_root() -> PathBuf {
    if let Ok(r) = std::env::var("VPIN_REPO_ROOT") {
        let p = PathBuf::from(r);
        if p.is_dir() {
            return p;
        }
    }
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
        .nth(2)
        .unwrap_or(&PathBuf::from("."))
        .to_path_buf()
}

fn with_python_path(cmd: &mut Command, repo: &Path) {
    let client = repo.join("vpin-client");
    let client_str = client.to_str().unwrap_or("");
    let sep = if cfg!(windows) { ";" } else { ":" };
    let pythonpath = match std::env::var("PYTHONPATH") {
        Ok(p) if !p.is_empty() => format!("{client_str}{sep}{p}"),
        _ => client_str.to_string(),
    };
    cmd.env("PYTHONPATH", pythonpath)
       .env("PYTHONIOENCODING", "utf-8")
       .env("PYTHONUTF8", "1");
}

fn apply_python_env(cmd: &mut Command, repo: &Path) {
    cmd.env("VPIN_REPO_ROOT", repo);
    cmd.env("VPIN_AHE_PARALLEL", "0");
    with_python_path(cmd, repo);
}

fn write_infer_fail_log(exit_code: i32, stderr_all: &str, stdout: &str) {
    let path = std::env::temp_dir().join(format!(
        "vpin_infer_fail_{}.log",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    ));
    let body = format!(
        "exit_code={exit_code}\n\n--- stderr ---\n{stderr_all}\n\n--- stdout ---\n{stdout}\n"
    );
    let _ = std::fs::write(&path, body);
    eprintln!("vpin infer failure log: {}", path.display());
}

fn acquire_infer_lock() -> Result<MutexGuard<'static, ()>, String> {
    INFER_SUBPROCESS_LOCK
        .try_lock()
        .map_err(|_| "推理正在进行中，请等待当前任务完成后再试".to_string())
}

fn client_root(repo: &Path) -> PathBuf {
    if let Ok(p) = std::env::var("VPIN_CLIENT_ROOT") {
        return PathBuf::from(p);
    }
    if let Ok(p) = std::env::var("VPIN_PLATFORM_ROOT") {
        return PathBuf::from(p);
    }
    repo.join("vpin-client")
}

fn ahe_cli_bin(client: &Path) -> PathBuf {
    for profile in ["release", "debug"] {
        let win = client.join("target").join(profile).join("ahe-cli.exe");
        if win.is_file() {
            return win;
        }
        let unix = client.join("target").join(profile).join("ahe-cli");
        if unix.is_file() {
            return unix;
        }
    }
    client.join("target").join("release").join("ahe-cli.exe")
}

fn run_ahe_cli_json(repo: &Path, client: &Path, args: &[&str]) -> Result<Value, String> {
    let cli = ahe_cli_bin(client);
    if !cli.is_file() {
        return Err(format!(
            "ahe-cli not found at {} — run: cd vpin-client && cargo build -p ahe-cli",
            cli.display()
        ));
    }
    let out = Command::new(&cli)
        .args(args)
        .env("VPIN_REPO_ROOT", repo)
        .current_dir(client)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

#[tauri::command]
fn ahe_preprocess_rust(mnist_index: u32) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    run_ahe_cli_json(
        &repo,
        &client,
        &["preprocess", "--mnist-index", &mnist_index.to_string()],
    )
}

#[tauri::command]
fn ahe_preprocess_batch_rust(start: u32, count: u32) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    run_ahe_cli_json(
        &repo,
        &client,
        &[
            "preprocess-batch",
            "--start",
            &start.to_string(),
            "--count",
            &count.to_string(),
        ],
    )
}

#[tauri::command]
async fn preprocess_upload_file_rust(path: String) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    let path_arg = path.clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_ahe_cli_json(
            &repo,
            &client,
            &["preprocess-upload", &path_arg],
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

fn bsgs_table(repo: &Path, client: &Path) -> PathBuf {
    let fixture = client.join("tests").join("fixtures").join("table.bin");
    if fixture.is_file() {
        return fixture;
    }
    repo.join("src")
        .join("Pre_computed_table")
        .join("table.bin")
}

fn venv_python(repo: &Path) -> PathBuf {
    repo.join(".venv").join("Scripts").join("python.exe")
}

fn emit_progress(app: &AppHandle, line: &str) {
    if let Ok(v) = serde_json::from_str::<Value>(line) {
        let _ = app.emit("ahe-progress", v);
    }
}

fn tail_lines(text: &str, max_lines: usize) -> String {
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    if lines.is_empty() {
        return String::new();
    }
    let start = lines.len().saturating_sub(max_lines);
    lines[start..].join("\n")
}

fn format_subprocess_failure(exit_code: i32, stderr: &str, stdout: &str, stderr_all: &str) -> String {
    let stderr = stderr.trim();
    if !stderr.is_empty() {
        return stderr.to_string();
    }
    if let Some(hint) = extract_ndjson_error_hint(stderr_all) {
        return hint;
    }
    if let Some(hint) = extract_last_progress_hint(stderr_all) {
        return format!(
            "推理在进度 {hint} 后异常退出 (code {exit_code})。若后端出现 ClientDisconnected，请勿重复点击并等待 15–70s。"
        );
    }
    let stdout = stdout.trim();
    if !stdout.is_empty() {
        if stdout.starts_with('{') {
            let preview: String = stdout.chars().take(800).collect();
            return format!("stdout (JSON preview): {preview}");
        }
        let tail = tail_lines(stdout, 8);
        return format!("stdout tail:\n{tail}");
    }
    format!(
        "子进程异常退出 (code {exit_code})。常见原因：WebSocket 在 ModelSelectAck 前断开、推理进行中重复点击/切换页面、或切换样本/引擎。请查看 vpin-backend 终端是否出现 ClientDisconnected。"
    )
}

fn extract_ndjson_error_hint(stderr_all: &str) -> Option<String> {
    for line in stderr_all.lines().rev() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
            if v.get("phase").and_then(|p| p.as_str()) == Some("error") {
                return v
                    .get("message")
                    .and_then(|m| m.as_str())
                    .map(String::from);
            }
        }
    }
    None
}

fn extract_last_progress_hint(stderr_all: &str) -> Option<String> {
    for line in stderr_all.lines().rev() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
            let phase = v.get("phase").and_then(|p| p.as_str()).unwrap_or("");
            if phase == "trace" {
                if let Some(step) = v.get("step") {
                    let id = step.get("id").and_then(|s| s.as_str()).unwrap_or("?");
                    let title = step.get("title").and_then(|s| s.as_str()).unwrap_or("");
                    return Some(format!("trace/{id} ({title})"));
                }
            }
            if !phase.is_empty() && phase != "progress" {
                return Some(phase.to_string());
            }
        }
    }
    None
}

fn run_subprocess_with_progress(
    app: AppHandle,
    mut cmd: Command,
) -> Result<String, String> {
    let _infer_guard = acquire_infer_lock()?;
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    let stderr = child.stderr.take().ok_or("no stderr")?;
    let stdout_buf: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
    let stderr_buf: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
    let stderr_all_buf: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));

    let app_reader = app.clone();
    let stderr_log = Arc::clone(&stderr_buf);
    let stderr_all_log = Arc::clone(&stderr_all_buf);
    let stderr_handle = std::thread::spawn(move || {
        use std::io::BufRead;
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            let line = match line {
                Ok(l) => l,
                Err(_) => break,
            };
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            {
                let mut all = stderr_all_log.lock().unwrap();
                if !all.is_empty() {
                    all.push('\n');
                }
                all.push_str(trimmed);
            }
            if serde_json::from_str::<Value>(trimmed).is_ok() {
                emit_progress(&app_reader, trimmed);
            } else {
                let mut buf = stderr_log.lock().unwrap();
                if !buf.is_empty() {
                    buf.push('\n');
                }
                buf.push_str(trimmed);
            }
        }
    });

    if let Some(stdout) = child.stdout.take() {
        let stdout_buf2 = Arc::clone(&stdout_buf);
        let stdout_handle = std::thread::spawn(move || {
            use std::io::Read;
            let mut stdout = stdout;
            let mut buf = Vec::new();
            let _ = stdout.read_to_end(&mut buf);
            if let Ok(s) = String::from_utf8(buf) {
                *stdout_buf2.lock().unwrap() = s;
            }
        });
        let status = child.wait().map_err(|e| e.to_string())?;
        let _ = stderr_handle.join();
        let _ = stdout_handle.join();
        let out = stdout_buf.lock().unwrap().clone();
        if !status.success() {
            let err = stderr_buf.lock().unwrap().clone();
            let all = stderr_all_buf.lock().unwrap().clone();
            write_infer_fail_log(status.code().unwrap_or(-1), &all, &out);
            let msg = format_subprocess_failure(status.code().unwrap_or(-1), &err, &out, &all);
            return Err(format!(
                "inference failed (exit {}): {}",
                status.code().unwrap_or(-1),
                msg.trim()
            ));
        }
        return Ok(out);
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    let _ = stderr_handle.join();
    let stdout = stdout_buf.lock().unwrap().clone();
    if !status.success() {
        let err = stderr_buf.lock().unwrap().clone();
        let all = stderr_all_buf.lock().unwrap().clone();
        write_infer_fail_log(status.code().unwrap_or(-1), &all, &stdout);
        let msg = format_subprocess_failure(status.code().unwrap_or(-1), &err, &stdout, &all);
        return Err(format!(
            "inference failed (exit {}): {}",
            status.code().unwrap_or(-1),
            msg.trim()
        ));
    }
    Ok(stdout)
}

fn parse_json_stdout(stdout: &str) -> Result<Value, String> {
    let trimmed = stdout.trim();
    serde_json::from_str(trimmed).map_err(|e| format!("invalid JSON output: {e}\n{trimmed}"))
}

fn build_python_infer(
    repo: &Path,
    backend_ws: &str,
    model_id: &str,
    mnist_index: Option<u32>,
    upload_id: Option<&str>,
    image_path: Option<&str>,
    infer_engine: &str,
) -> Command {
    let python = venv_python(repo);
    if !python.is_file() {
        eprintln!("warning: venv python not found at {}", python.display());
    }
    let mut cmd = Command::new(&python);
    cmd.current_dir(repo).env("PYTHONUNBUFFERED", "1");
    apply_python_env(&mut cmd, repo);
    cmd.args([
            "-m",
            "vpin_client.cli",
            "ahe-infer",
            "--backend",
            backend_ws,
            "--model",
            model_id,
            "--timing",
            "--trace",
            "--progress-ndjson",
            "--infer-engine",
            infer_engine,
        ]);
    let idx_s = mnist_index.unwrap_or(0).to_string();
    if let Some(path) = image_path {
        cmd.args(["--image", path]);
    } else if let Some(id) = upload_id {
        cmd.args(["--upload-id", id]);
    } else {
        cmd.args(["--mnist-index", &idx_s]);
    }
    cmd
}

fn build_rust_infer(
    client: &Path,
    repo: &Path,
    crypto: &str,
    port: u16,
    model_id: &str,
    mnist_index: u32,
    sample_json: Option<&Path>,
    image_path: Option<&str>,
) -> Command {
    let cli = ahe_cli_bin(client);
    let mut cmd = Command::new(&cli);
    cmd.current_dir(client)
        .env("VPIN_REPO_ROOT", repo)
        .env("VPIN_BSGS_TABLE", bsgs_table(repo, client))
        .env("AHE_SERVER_PORT", port.to_string())
        .args([
            "infer",
            "--model",
            model_id,
            "--mnist-index",
            &mnist_index.to_string(),
            "--crypto-backend",
            crypto,
            "--progress-ndjson",
        ]);
    if let Some(path) = sample_json {
        cmd.args(["--sample-json", path.to_str().unwrap_or("")]);
    }
    if let Some(img) = image_path {
        cmd.args(["--image", img]);
    }
    cmd
}

fn build_rust_infer_args(
    repo: &Path,
    client: &Path,
    crypto: &str,
    port: u16,
    model_id: &str,
    mnist_index: Option<u32>,
    image_path: Option<&str>,
) -> Result<Command, String> {
    let idx = mnist_index.unwrap_or(0);
    if image_path.is_some() {
        return Ok(build_rust_infer(
            client,
            repo,
            crypto,
            port,
            model_id,
            idx,
            None,
            image_path,
        ));
    }
    let idx = mnist_index.ok_or("Rust 推理需要 MNIST 序号或本地图片路径")?;
    Ok(build_rust_infer(
        client,
        repo,
        crypto,
        port,
        model_id,
        idx,
        None,
        None,
    ))
}


#[derive(Debug, Deserialize, serde::Serialize)]
struct BatchJobPayload {
    mnist_index: Option<u32>,
    upload_id: Option<String>,
    image_path: Option<String>,
}

fn write_batch_jobs_json(jobs: &[BatchJobPayload]) -> Result<PathBuf, String> {
    let path = std::env::temp_dir().join(format!(
        "vpin_batch_{}.json",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_millis()
    ));
    let body = serde_json::json!({ "jobs": jobs });
    std::fs::write(&path, body.to_string()).map_err(|e| e.to_string())?;
    Ok(path)
}

fn write_mnist_range_jobs_json(start: u32, end: u32) -> Result<PathBuf, String> {
    let limit = end.saturating_sub(start).saturating_add(1);
    let jobs: Vec<BatchJobPayload> = (0..limit)
        .map(|i| BatchJobPayload {
            mnist_index: Some(start + i),
            upload_id: None,
            image_path: None,
        })
        .collect();
    write_batch_jobs_json(&jobs)
}

fn build_python_batch(
    repo: &Path,
    backend_ws: &str,
    model_id: &str,
    jobs_path: Option<&Path>,
    mnist_start: Option<u32>,
    mnist_limit: Option<u32>,
    concurrency: u32,
    trace_mode: &str,
    infer_engine: &str,
) -> Command {
    let python = venv_python(repo);
    let mut cmd = Command::new(&python);
    cmd.current_dir(repo).env("PYTHONUNBUFFERED", "1");
    apply_python_env(&mut cmd, repo);
    cmd.args([
        "-m",
        "vpin_client.cli",
        "eval-mnist-ahe",
        "--backend",
        backend_ws,
        "--model",
        model_id,
        "--concurrency",
        &concurrency.to_string(),
        "--trace-mode",
        trace_mode,
        "--progress-ndjson",
        "--infer-engine",
        infer_engine,
    ]);
    if let (Some(start), Some(limit)) = (mnist_start, mnist_limit) {
        cmd.args(["--start", &start.to_string(), "--limit", &limit.to_string()]);
    } else if let Some(path) = jobs_path {
        cmd.args(["--jobs-json", path.to_str().unwrap_or("")]);
    }
    cmd
}

fn build_rust_batch(
    client: &Path,
    repo: &Path,
    crypto: &str,
    port: u16,
    model_id: &str,
    jobs_path: &Path,
    concurrency: u32,
) -> Command {
    let cli = ahe_cli_bin(client);
    let mut cmd = Command::new(&cli);
    cmd.current_dir(client)
        .env("VPIN_REPO_ROOT", repo)
        .env("VPIN_BSGS_TABLE", bsgs_table(repo, client))
        .env("AHE_SERVER_PORT", port.to_string())
        .args([
            "eval-mnist-ahe",
            "--model",
            model_id,
            "--jobs-json",
            jobs_path.to_str().unwrap_or(""),
            "--concurrency",
            &concurrency.to_string(),
            "--progress-ndjson",
            "--crypto-backend",
            crypto,
        ]);
    cmd
}


#[tauri::command]
fn ahe_preprocess(mnist_index: u32) -> Result<Value, String> {
    let repo = repo_root();
    let python = venv_python(&repo);
    let script = format!(
        "import json; from vpin_client.data.official import load_official_test; from vpin_client.data.core import preprocess_result_to_dict; print(json.dumps(preprocess_result_to_dict(load_official_test({}))))",
        mnist_index
    );
    let mut cmd = Command::new(&python);
    with_python_path(&mut cmd, &repo);
    let out = cmd.args(["-c", &script])
        .current_dir(&repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}




#[tauri::command]
fn ahe_preprocess_batch(start: u32, count: u32) -> Result<Value, String> {
    let repo = repo_root();
    let python = venv_python(&repo);
    let script = format!(
        r#"import json
from vpin_client.data.official import load_official_batch
from vpin_client.data.core import preprocess_result_to_dict
items = [preprocess_result_to_dict(r) for r in load_official_batch({}, {})]
print(json.dumps({{"items": items}}))"#,
        start, count
    );
    let mut cmd = Command::new(&python);
    with_python_path(&mut cmd, &repo);
    let out = cmd.args(["-c", &script])
        .current_dir(&repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

#[tauri::command]
async fn preprocess_upload_file(path: String) -> Result<Value, String> {
    let repo = repo_root();
    let python = venv_python(&repo);
    let script = format!(
        "import json; from pathlib import Path; from vpin_client.data.upload import preprocess_upload_path; from vpin_client.data.core import preprocess_result_to_dict; print(json.dumps(preprocess_result_to_dict(preprocess_upload_path(Path(r'{}')))))",
        path.replace('\'', "''")
    );
    let out = tauri::async_runtime::spawn_blocking(move || {
        let mut cmd = Command::new(&python);
        with_python_path(&mut cmd, &repo);
        cmd.args(["-c", &script])
           .current_dir(&repo)
           .output()
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

/// Run AHE inference with live progress events (`ahe-progress`).
#[tauri::command]
async fn run_ahe_inference(
    app: AppHandle,
    infer_engine: String,
    mnist_index: Option<u32>,
    upload_id: Option<String>,
    image_path: Option<String>,
    backend_ws: Option<String>,
    model_id: String,
) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    let engine = infer_engine.as_str();

    let cmd = match engine {
        "python" => {
            let ws = backend_ws.unwrap_or_else(|| {
                "ws://127.0.0.1:8000/api/v1/session/ws".to_string()
            });
            build_python_infer(
                &repo,
                &ws,
                &model_id,
                mnist_index,
                upload_id.as_deref(),
                image_path.as_deref(),
                "python",
            )
        }
        "rust-ark" => build_rust_infer_args(
            &repo,
            &client,
            "ark",
            8001,
            &model_id,
            mnist_index,
            image_path.as_deref(),
        )?,
        "rust-ec" => build_rust_infer_args(
            &repo,
            &client,
            "ec",
            8002,
            &model_id,
            mnist_index,
            image_path.as_deref(),
        )?,
        other => return Err(format!("unknown infer_engine: {other}")),
    };

    let app2 = app.clone();
    let stdout = tauri::async_runtime::spawn_blocking(move || run_subprocess_with_progress(app2, cmd))
        .await
        .map_err(|e| e.to_string())??;

    let mut result = parse_json_stdout(&stdout)?;
    if let Some(obj) = result.as_object_mut() {
        obj.entry("infer_engine")
            .or_insert(Value::String(infer_engine));
    }
    let _ = app.emit("ahe-progress", serde_json::json!({
        "kind": "progress",
        "phase": "session_done",
        "result": result.clone(),
    }));
    Ok(result)
}


/// Run batch AHE inference with live progress events (`ahe-progress`).
#[tauri::command]
async fn run_ahe_batch_inference(
    app: AppHandle,
    infer_engine: String,
    model_id: String,
    jobs: Option<Vec<BatchJobPayload>>,
    mnist_start: Option<u32>,
    mnist_end: Option<u32>,
    concurrency: u32,
    trace_mode: String,
    backend_ws: Option<String>,
) -> Result<Value, String> {
    let use_range = mnist_start.is_some() && mnist_end.is_some();
    let jobs = jobs.unwrap_or_default();
    if !use_range && jobs.is_empty() {
        return Err("batch jobs list is empty".into());
    }
    if use_range {
        let start = mnist_start.unwrap();
        let end = mnist_end.unwrap();
        if end < start {
            return Err("mnist_end must be >= mnist_start".into());
        }
    }

    let repo = repo_root();
    let client = client_root(&repo);
    let trace_arg: String = if trace_mode.is_empty() {
        "none".into()
    } else {
        trace_mode.clone()
    };
    let infer_engine2 = infer_engine.clone();
    let model_id2 = model_id.clone();
    let backend_ws2 = backend_ws.clone();
    let client2 = client.clone();

    let app2 = app.clone();
    let stdout = tauri::async_runtime::spawn_blocking(move || {
        let trace = trace_arg.as_str();
        let cmd = if use_range {
            let start = mnist_start.unwrap();
            let end = mnist_end.unwrap();
            let limit = end.saturating_sub(start).saturating_add(1);
            match infer_engine2.as_str() {
                "python" => {
                    let ws = backend_ws2
                        .unwrap_or_else(|| "ws://127.0.0.1:8000/api/v1/session/ws".into());
                    build_python_batch(
                        &repo,
                        &ws,
                        &model_id2,
                        None,
                        Some(start),
                        Some(limit),
                        concurrency,
                        trace,
                        "python",
                    )
                }
                "rust-ark" => {
                    let jobs_path = write_mnist_range_jobs_json(start, end)?;
                    build_rust_batch(
                        &client2,
                        &repo,
                        "ark",
                        8001,
                        &model_id2,
                        &jobs_path,
                        concurrency,
                    )
                }
                "rust-ec" => {
                    let jobs_path = write_mnist_range_jobs_json(start, end)?;
                    build_rust_batch(
                        &client2,
                        &repo,
                        "ec",
                        8002,
                        &model_id2,
                        &jobs_path,
                        concurrency,
                    )
                }
                other => return Err(format!("unknown infer_engine: {other}")),
            }
        } else {
            let jobs_path = write_batch_jobs_json(&jobs)?;
            match infer_engine2.as_str() {
                "python" => {
                    let ws = backend_ws2
                        .unwrap_or_else(|| "ws://127.0.0.1:8000/api/v1/session/ws".into());
                    build_python_batch(
                        &repo,
                        &ws,
                        &model_id2,
                        Some(&jobs_path),
                        None,
                        None,
                        concurrency,
                        trace,
                        "python",
                    )
                }
                "rust-ark" => build_rust_batch(
                    &client2,
                    &repo,
                    "ark",
                    8001,
                    &model_id2,
                    &jobs_path,
                    concurrency,
                ),
                "rust-ec" => build_rust_batch(
                    &client2,
                    &repo,
                    "ec",
                    8002,
                    &model_id2,
                    &jobs_path,
                    concurrency,
                ),
                other => return Err(format!("unknown infer_engine: {other}")),
            }
        };
        run_subprocess_with_progress(app2, cmd)
    })
    .await
    .map_err(|e| e.to_string())??;

    let mut result = parse_json_stdout(&stdout)?;
    if let Some(obj) = result.as_object_mut() {
        obj.entry("infer_engine")
            .or_insert(Value::String(infer_engine.clone()));
    }
    let _ = app.emit(
        "ahe-progress",
        serde_json::json!({
            "kind": "progress",
            "phase": "batch_done",
            "report": result.clone(),
        }),
    );
    Ok(result)
}


fn write_temp_upload(data: &[u8], filename: &str) -> Result<PathBuf, String> {
    let ext = Path::new(filename)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("png");
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let tmp = std::env::temp_dir().join(format!("vpin_upload_{}.{}", ts, ext));
    std::fs::write(&tmp, data).map_err(|e| e.to_string())?;
    Ok(tmp)
}

/// Preprocess uploaded image bytes (Python lane) — avoids Tauri File.path reliability issues.
#[tauri::command]
async fn preprocess_upload_bytes(data: Vec<u8>, filename: String) -> Result<Value, String> {
    let repo = repo_root();
    let tmp_path = write_temp_upload(&data, &filename)?;
    let path_str = tmp_path.to_str().unwrap_or("").replace('\\', "/");
    let fn_safe = filename.replace('"', "_");
    let script = format!(
        r#"import json; from pathlib import Path; from vpin_client.data.upload import preprocess_upload_path; from vpin_client.data.core import preprocess_result_to_dict; r=preprocess_result_to_dict(preprocess_upload_path(Path("{}"))); r["filename"]="{}"; r["_temp_path"]="{}"; print(json.dumps(r))"#,
        path_str, fn_safe, path_str
    );
    let python = venv_python(&repo);
    let mut cmd = Command::new(&python);
    with_python_path(&mut cmd, &repo);
    let out = cmd.args(["-c", &script])
        .current_dir(&repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        let _ = std::fs::remove_file(&tmp_path);
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

/// Preprocess uploaded image bytes (Rust ahe-cli lane).
#[tauri::command]
async fn preprocess_upload_bytes_rust(data: Vec<u8>, filename: String) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    let tmp_path = write_temp_upload(&data, &filename)?;
    let tmp_str = tmp_path.to_str().unwrap_or("").to_string();
    let tmp_str2 = tmp_str.clone();
    let filename2 = filename.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let args = ["preprocess-upload", tmp_str2.as_str()];
        run_ahe_cli_json(&repo, &client, &args)
    })
    .await
    .map_err(|e| e.to_string())?;
    let mut v = result?;
    if let Some(obj) = v.as_object_mut() {
        obj.entry("_temp_path").or_insert(Value::String(tmp_str));
        obj.entry("filename").or_insert(Value::String(filename2));
        obj.insert("source".to_string(), Value::String("upload".to_string()));
    }
    Ok(v)
}

/// Load the 7 test images from model_training/test_images/ as a gallery (Python preprocessing).
#[tauri::command]
fn load_test_gallery() -> Result<Value, String> {
    let repo = repo_root();
    let dir = repo.join("model_training").join("test_images");
    if !dir.is_dir() {
        return Err(format!("test_images not found: {}", dir.display()));
    }
    let dir_str = dir.to_str().unwrap_or("").replace('\\', "/");
    let script = format!(
        "import json\nfrom pathlib import Path\nfrom vpin_client.data.upload import preprocess_upload_path\nfrom vpin_client.data.core import preprocess_result_to_dict\nd=Path(\"{}\")\nitems=[]\nfor p in sorted(d.glob(\"*.png\")):\n    try:\n        r=preprocess_upload_path(p)\n        item=preprocess_result_to_dict(r)\n        item[\"filename\"]=p.name\n        item[\"source\"]=\"upload\"\n        item[\"_source_path\"]=str(p).replace(\"\\\\\",\"/\")\n        items.append(item)\n    except Exception as e:\n        pass\nprint(json.dumps({{\"items\":items}}))\n",
        dir_str
    );
    let python = venv_python(&repo);
    let mut cmd = Command::new(&python);
    with_python_path(&mut cmd, &repo);
    let out = cmd.args(["-c", &script])
        .current_dir(&repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
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
            ahe_preprocess_batch,
            preprocess_upload_file,
            ahe_preprocess_rust,
            ahe_preprocess_batch_rust,
            preprocess_upload_file_rust,
            preprocess_upload_bytes,
            preprocess_upload_bytes_rust,
            load_test_gallery,
            run_ahe_inference,
            run_ahe_batch_inference
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
