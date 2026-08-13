// Tauri bridge → Python vpin_client or Rust ahe-cli (L4). Streams progress via events.

mod communication;

use std::io::{BufReader, Read, Write};
use std::time::Duration;
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
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if dir.join("data").join("bsgs").join("table.bin").is_file() {
                return dir.to_path_buf();
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("data").join("bsgs").join("table.bin").is_file() {
            return cwd;
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

fn apply_python_env(cmd: &mut Command, repo: &Path) {
    cmd.env("VPIN_REPO_ROOT", repo);
    cmd.env("VPIN_AHE_PARALLEL", "0");
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");
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
    if repo.join("bin").join("ahe-cli.exe").is_file() {
        return repo.to_path_buf();
    }
    repo.join("vpin-client")
}

fn ahe_cli_bin(client: &Path) -> PathBuf {
    let repo = repo_root();
    let bundled = repo.join("bin").join("ahe-cli.exe");
    if bundled.is_file() {
        return bundled;
    }
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

fn release_weights_dir(repo: &Path) -> Option<PathBuf> {
    let p = repo.join("data").join("weights").join("cnn-mnist-trained");
    if p.is_dir() {
        Some(p)
    } else {
        None
    }
}

fn apply_release_env(cmd: &mut Command, repo: &Path, bsgs: &Path) {
    cmd.env("VPIN_REPO_ROOT", repo);
    cmd.env("VPIN_BSGS_TABLE", bsgs);
    if let Some(w) = release_weights_dir(repo) {
        cmd.env("VPIN_WEIGHTS_DIR", w);
    }
}

fn run_ahe_cli_json(repo: &Path, client: &Path, args: &[&str]) -> Result<Value, String> {
    let cli = ahe_cli_bin(client);
    if !cli.is_file() {
        return Err(format!(
            "ahe-cli not found at {} — run: cd vpin-client && cargo build -p ahe-cli",
            cli.display()
        ));
    }
    let bsgs = bsgs_table(repo, client);
    let mut cmd = Command::new(&cli);
    cmd.args(args);
    apply_release_env(&mut cmd, repo, &bsgs);
    cmd.current_dir(client);
    let out = cmd.output().map_err(|e| e.to_string())?;
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

fn data_root() -> PathBuf {
    if let Ok(d) = std::env::var("VPIN_DATA_DIR") {
        let p = PathBuf::from(d);
        if p.is_dir() || p.parent().is_some() {
            return p;
        }
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(local).join("vpin-console");
    }
    repo_root()
}

fn bsgs_table(repo: &Path, client: &Path) -> PathBuf {
    if let Ok(p) = std::env::var("VPIN_BSGS_TABLE") {
        let path = PathBuf::from(p);
        if path.is_file() {
            return path;
        }
    }
    let cached = data_root().join("artifacts").join("table.bin");
    if cached.is_file() {
        return cached;
    }
    let release = repo.join("data").join("bsgs").join("table.bin");
    if release.is_file() {
        return release;
    }
    let fixture = client.join("tests").join("fixtures").join("table.bin");
    if fixture.is_file() {
        return fixture;
    }
    let repo_bin = repo
        .join("src")
        .join("Pre_computed_table")
        .join("table.bin");
    if repo_bin.is_file() {
        return repo_bin;
    }
    cached
}

fn sha256_file(path: &Path) -> Result<String, String> {
    use sha2::{Digest, Sha256};
    let mut file = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    loop {
        let n = std::io::Read::read(&mut file, &mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

fn download_artifact(
    url: &str,
    dest: &Path,
    expected_sha: Option<&str>,
    expected_size: Option<u64>,
) -> Result<(), String> {
    dest.parent()
        .map(std::fs::create_dir_all)
        .transpose()
        .map_err(|e| e.to_string())?;
    let tmp = dest.with_extension("part");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(3600))
        .build()
        .map_err(|e| e.to_string())?;
    let mut resp = client.get(url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {} for {url}", resp.status()));
    }
    let mut out = std::fs::File::create(&tmp).map_err(|e| e.to_string())?;
    let mut done: u64 = 0;
    let mut buf = [0u8; 1024 * 1024];
    loop {
        let n = resp.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        std::io::Write::write_all(&mut out, &buf[..n]).map_err(|e| e.to_string())?;
        done += n as u64;
        if let Some(total) = expected_size {
            if total > 0 && done % (32 * 1024 * 1024) < n as u64 {
                eprintln!("download {url}: {done}/{total} bytes");
            }
        }
    }
    drop(out);
    if let Some(size) = expected_size {
        let got = std::fs::metadata(&tmp).map_err(|e| e.to_string())?.len();
        if got != size {
            let _ = std::fs::remove_file(&tmp);
            return Err(format!("size mismatch: got {got}, expected {size}"));
        }
    }
    if let Some(expected) = expected_sha {
        let got = sha256_file(&tmp)?;
        if got.to_lowercase() != expected.to_lowercase() {
            let _ = std::fs::remove_file(&tmp);
            return Err("sha256 mismatch".into());
        }
    }
    std::fs::rename(&tmp, dest).map_err(|e| e.to_string())
}

fn ensure_remote_artifacts_rust(repo: &Path) -> Result<Value, String> {
    let manifest_path = repo.join("config").join("runtime-artifacts.manifest.json");
    if !manifest_path.is_file() {
        return Ok(serde_json::json!({
            "ok": true,
            "skipped": true,
            "reason": "manifest missing"
        }));
    }
    let raw = std::fs::read_to_string(&manifest_path).map_err(|e| e.to_string())?;
    let doc: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    let base_env = doc
        .get("base_url_env")
        .and_then(|v| v.as_str())
        .unwrap_or("VPIN_ARTIFACTS_BASE_URL");
    let base = std::env::var(base_env).ok().filter(|s| !s.is_empty());
    let Some(base) = base else {
        return Ok(serde_json::json!({
            "ok": true,
            "skipped": true,
            "reason": format!("{base_env} not set")
        }));
    };
    let base = format!("{}/", base.trim_end_matches('/'));
    let mut pulled = Vec::new();
    let mut already = Vec::new();
    let mut errors = Vec::new();

    let entries = doc
        .get("remote")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    for entry in entries {
        let required = entry
            .get("required_for")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str()).any(|s| s == "rust_ahe"))
            .unwrap_or(false);
        if !required {
            continue;
        }
        let id = entry
            .get("id")
            .and_then(|v| v.as_str())
            .unwrap_or("?")
            .to_string();
        let rel_dest = entry
            .get("dest")
            .and_then(|v| v.as_str())
            .ok_or_else(|| format!("missing dest for {id}"))?;
        let dest = if rel_dest == "vpin-client/tests/fixtures/table.bin" {
            data_root().join("artifacts").join("table.bin")
        } else {
            repo.join(rel_dest)
        };
        let sha = entry.get("sha256").and_then(|v| v.as_str());
        let size = entry.get("size_bytes").and_then(|v| v.as_u64());
        if dest.is_file() {
            if let (Some(expected), Some(sz)) = (sha, size) {
                if let Ok(got) = sha256_file(&dest) {
                    if got.eq_ignore_ascii_case(expected)
                        && dest.metadata().map(|m| m.len()).unwrap_or(0) == sz
                    {
                        already.push(id);
                        continue;
                    }
                }
            } else if dest.is_file() {
                already.push(id);
                continue;
            }
        }
        let url_path = entry
            .get("url_path")
            .and_then(|v| v.as_str())
            .unwrap_or("table.bin");
        let url = format!("{base}{url_path}");
        match download_artifact(&url, &dest, sha, size) {
            Ok(()) => pulled.push(id),
            Err(e) => errors.push(format!("{id}: {e}")),
        }
    }

    Ok(serde_json::json!({
        "ok": errors.is_empty(),
        "skipped": false,
        "pulled": pulled,
        "already_present": already,
        "errors": errors,
    }))
}

/// Pull BSGS table.bin etc. on first init when VPIN_ARTIFACTS_BASE_URL is set.
fn ensure_runtime_artifacts_blocking() -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    let remote = ensure_remote_artifacts_rust(&repo)?;
    let bsgs = bsgs_table(&repo, &client);
    Ok(serde_json::json!({
        "repo_root": repo.to_string_lossy(),
        "data_root": data_root().to_string_lossy(),
        "bsgs_table": bsgs.to_string_lossy(),
        "bsgs_present": bsgs.is_file(),
        "remote": remote,
    }))
}

#[tauri::command]
async fn ensure_runtime_artifacts() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(ensure_runtime_artifacts_blocking)
        .await
        .map_err(|e| e.to_string())?
}

fn ahe_server_bin(repo: &Path) -> PathBuf {
    let bundled = repo.join("bin").join("ahe-server.exe");
    if bundled.is_file() {
        return bundled;
    }
    for profile in ["release", "debug"] {
        let p = repo
            .join("vpin-backend")
            .join("target")
            .join(profile)
            .join("ahe-server.exe");
        if p.is_file() {
            return p;
        }
        let p2 = repo
            .join("vpin-platform")
            .join("target")
            .join(profile)
            .join("ahe-server.exe");
        if p2.is_file() {
            return p2;
        }
    }
    repo.join("vpin-backend")
        .join("target")
        .join("release")
        .join("ahe-server.exe")
}

fn ahe_server_workdir(repo: &Path, bin: &Path) -> PathBuf {
    let s = bin.to_string_lossy();
    if s.contains("vpin-backend") {
        return repo.join("vpin-backend");
    }
    if s.contains("vpin-platform") {
        return repo.join("vpin-platform");
    }
    bin.parent()
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| repo.to_path_buf())
}

/// Start Rust ahe-server if not already healthy (单体包默认本地；分包设 VPIN_SKIP_LOCAL_AHE=1 仅探活远程).
fn ensure_ahe_server_blocking(port: u16) -> Result<Value, String> {
    if communication::should_skip_local_ahe() {
        return communication::ensure_ahe_skip_local_result(port);
    }
    if let Some(v) = communication::ensure_ahe_already_running(port) {
        return Ok(v);
    }
    let repo = repo_root();
    let client = client_root(&repo);
    let _ = ensure_remote_artifacts_rust(&repo)?;
    let bin = ahe_server_bin(&repo);
    if !bin.is_file() {
        return Err(format!(
            "ahe-server not found at {} — run .\\scripts\\build-rust-ahe.ps1",
            bin.display()
        ));
    }
    let bsgs = bsgs_table(&repo, &client);
    if !bsgs.is_file() {
        return Err(format!(
            "BSGS table missing: {} — set VPIN_ARTIFACTS_BASE_URL and restart, or run scripts\\pull-runtime-artifacts.ps1",
            bsgs.display()
        ));
    }
    let workdir = ahe_server_workdir(&repo, &bin);
    let ep = communication::ahe_target(port);
    let mut child = Command::new(&bin);
    child
        .current_dir(&workdir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    communication::apply_ahe_env(&mut child, port);
    apply_release_env(&mut child, &repo, &bsgs);
    child.spawn().map_err(|e| e.to_string())?;

    for _ in 0..180 {
        std::thread::sleep(Duration::from_millis(500));
        if communication::http_health_ok(&ep.host, ep.port) {
            return Ok(serde_json::json!({
                "started": true,
                "port": ep.port,
                "host": ep.host,
                "status": "ok"
            }));
        }
    }
    Err(format!(
        "ahe-server on {}:{} did not become healthy within 90s",
        ep.host, ep.port
    ))
}

#[tauri::command]
async fn ensure_ahe_server(port: u16) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || ensure_ahe_server_blocking(port))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn ping_ahe_server_health(port: u16) -> Result<Value, String> {
    Ok(communication::ping_ahe_health(port))
}

#[tauri::command]
fn get_communication_profile() -> Result<communication::CommunicationProfile, String> {
    Ok(communication::load_profile(&repo_root()))
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
    run_subprocess_with_progress_locked(app, cmd, true)
}

fn run_subprocess_with_progress_no_lock(
    app: AppHandle,
    cmd: Command,
) -> Result<String, String> {
    run_subprocess_with_progress_locked(app, cmd, false)
}

fn run_subprocess_with_progress_locked(
    app: AppHandle,
    mut cmd: Command,
    use_infer_lock: bool,
) -> Result<String, String> {
    let _infer_guard = if use_infer_lock {
        Some(acquire_infer_lock()?)
    } else {
        None
    };
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
    let bsgs = bsgs_table(repo, client);
    let mut cmd = Command::new(&cli);
    cmd.current_dir(client);
    communication::apply_ahe_env(&mut cmd, port);
    apply_release_env(&mut cmd, repo, &bsgs);
    cmd.args([
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
    let bsgs = bsgs_table(repo, client);
    let mut cmd = Command::new(&cli);
    cmd.current_dir(client);
    communication::apply_ahe_env(&mut cmd, port);
    apply_release_env(&mut cmd, repo, &bsgs);
    cmd.args([
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
    let out = Command::new(&python)
        .args(["-c", &script])
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
    let out = Command::new(&python)
        .args(["-c", &script])
        .current_dir(&repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

#[tauri::command]
fn preprocess_dataset_single(dataset_id: String, index: u32) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    if let Ok(json) = run_ahe_cli_json(
        &repo,
        &client,
        &[
            "preprocess",
            "--dataset-id",
            &dataset_id,
            "--index",
            &index.to_string(),
        ],
    ) {
        return Ok(json);
    }
    preprocess_dataset_single_python(&repo, &dataset_id, index)
}

#[tauri::command]
fn preprocess_dataset_batch(dataset_id: String, start: u32, count: u32) -> Result<Value, String> {
    let repo = repo_root();
    let client = client_root(&repo);
    if let Ok(json) = run_ahe_cli_json(
        &repo,
        &client,
        &[
            "preprocess-batch",
            "--dataset-id",
            &dataset_id,
            "--start",
            &start.to_string(),
            "--count",
            &count.to_string(),
        ],
    ) {
        return Ok(json);
    }
    preprocess_dataset_batch_python(&repo, &dataset_id, start, count)
}

fn preprocess_dataset_single_python(repo: &Path, dataset_id: &str, index: u32) -> Result<Value, String> {
    let python = venv_python(repo);
    let script = format!(
        r#"import json
from vpin_client.data.dataset_preview import load_dataset_preview
print(json.dumps(load_dataset_preview("{}", {})))"#,
        dataset_id.replace('"', "\\\""),
        index
    );
    let out = Command::new(&python)
        .args(["-c", &script])
        .current_dir(repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    parse_json_stdout(&String::from_utf8_lossy(&out.stdout))
}

fn preprocess_dataset_batch_python(
    repo: &Path,
    dataset_id: &str,
    start: u32,
    count: u32,
) -> Result<Value, String> {
    let python = venv_python(repo);
    let script = format!(
        r#"import json
from vpin_client.data.dataset_preview import load_dataset_batch
print(json.dumps(load_dataset_batch("{}", {}, {})))"#,
        dataset_id.replace('"', "\\\""),
        start,
        count
    );
    let out = Command::new(&python)
        .args(["-c", &script])
        .current_dir(repo)
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
        Command::new(&python)
            .args(["-c", &script])
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


fn build_computation_proof(
    repo: &Path,
    backend_http: &str,
    model_id: &str,
    network_id: &str,
    session_id: &str,
) -> Command {
    let python = venv_python(repo);
    let mut cmd = Command::new(&python);
    cmd.current_dir(repo).env("PYTHONUNBUFFERED", "1");
    apply_python_env(&mut cmd, repo);
    cmd.args([
        "-m",
        "vpin_client.cli",
        "computation-proof",
        "--backend-http",
        backend_http,
        "--model",
        model_id,
        "--network",
        network_id,
        "--session-id",
        session_id,
        "--progress-ndjson",
    ]);
    cmd
}

/// Network A computation proof — does NOT use INFER_SUBPROCESS_LOCK (non-blocking after AHE).
#[tauri::command]
async fn run_computation_proof(
    app: AppHandle,
    model_id: String,
    session_id: String,
    network_id: Option<String>,
    backend_http: Option<String>,
) -> Result<Value, String> {
    let repo = repo_root();
    let net = network_id.unwrap_or_else(|| "A".to_string());
    let sid = if session_id.is_empty() {
        format!("tauri-proof-{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0))
    } else {
        session_id
    };
    let backend = backend_http.unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
    let cmd = build_computation_proof(&repo, &backend, &model_id, &net, &sid);
    let app2 = app.clone();
    let stdout = tauri::async_runtime::spawn_blocking(move || {
        run_subprocess_with_progress_no_lock(app2, cmd)
    })
    .await
    .map_err(|e| e.to_string())??;
    let result = parse_json_stdout(&stdout)?;
    let _ = app.emit(
        "proof-progress",
        serde_json::json!({
            "kind": "progress",
            "phase": "proof_done",
            "result": result.clone(),
        }),
    );
    Ok(result)
}

fn build_computation_proof_verify(
    repo: &Path,
    backend_http: &str,
    network_id: &str,
) -> Command {
    let python = venv_python(repo);
    let mut cmd = Command::new(&python);
    cmd.current_dir(repo).env("PYTHONUNBUFFERED", "1");
    apply_python_env(&mut cmd, repo);
    cmd.args([
        "-m",
        "vpin_client.cli",
        "computation-proof-verify",
        "--backend-http",
        backend_http,
        "--network",
        network_id,
    ]);
    cmd
}

fn build_computation_proof_save(
    repo: &Path,
    backend_http: &str,
    network_id: &str,
    dest_path: &str,
    source_path: Option<&str>,
) -> Command {
    let python = venv_python(repo);
    let mut cmd = Command::new(&python);
    cmd.current_dir(repo).env("PYTHONUNBUFFERED", "1");
    apply_python_env(&mut cmd, repo);
    cmd.args([
        "-m",
        "vpin_client.cli",
        "computation-proof-save",
        "--backend-http",
        backend_http,
        "--network",
        network_id,
        "--dest",
        dest_path,
    ]);
    if let Some(src) = source_path {
        if !src.is_empty() {
            cmd.args(["--source", src]);
        }
    }
    cmd
}

fn run_python_json_cmd(mut cmd: Command) -> Result<Value, String> {
    let output = cmd.output().map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "command failed (exit {}): {stderr}\n{stdout}",
            output.status.code().unwrap_or(-1)
        ));
    }
    parse_json_stdout(&stdout)
}

/// P6 verify — calls vpin-backend /proof/verify (no infer lock).
#[tauri::command]
async fn verify_computation_proof(
    network_id: Option<String>,
    backend_http: Option<String>,
) -> Result<Value, String> {
    let repo = repo_root();
    let net = network_id.unwrap_or_else(|| "A".to_string());
    let backend = backend_http.unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
    let cmd = build_computation_proof_verify(&repo, &backend, &net);
    tauri::async_runtime::spawn_blocking(move || run_python_json_cmd(cmd))
        .await
        .map_err(|e| e.to_string())?
}

/// Save protocol.json to a user-specified local path.
#[tauri::command]
async fn save_proof_artifact(
    dest_path: String,
    source_path: Option<String>,
    network_id: Option<String>,
    backend_http: Option<String>,
) -> Result<Value, String> {
    let repo = repo_root();
    let net = network_id.unwrap_or_else(|| "A".to_string());
    let backend = backend_http.unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
    let src = source_path.filter(|s| !s.trim().is_empty());
    let cmd = build_computation_proof_save(
        &repo,
        &backend,
        &net,
        dest_path.trim(),
        src.as_deref(),
    );
    tauri::async_runtime::spawn_blocking(move || run_python_json_cmd(cmd))
        .await
        .map_err(|e| e.to_string())?
}


fn dataset_entry_available(repo: &Path, entry: &Value) -> bool {
    if entry.get("dynamic").and_then(|v| v.as_bool()).unwrap_or(false) {
        return true;
    }
    let Some(hint) = entry.get("cache_path_hint").and_then(|v| v.as_str()) else {
        return true;
    };
    let rel = hint.replace('/', std::path::MAIN_SEPARATOR_STR);
    repo.join(rel).is_dir()
}

#[tauri::command]
fn read_datasets_catalog() -> Result<Value, String> {
    let repo = repo_root();
    let path = repo.join("config").join("datasets-catalog.json");
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {}: {}", path.display(), e))?;
    let mut catalog: Value =
        serde_json::from_str(&raw).map_err(|e| format!("parse datasets-catalog.json: {e}"))?;
    if let Some(local) = catalog.get_mut("local").and_then(|v| v.as_array_mut()) {
        local.retain(|entry| dataset_entry_available(&repo, entry));
    }
    if catalog.get("remote").is_none() {
        catalog["remote"] = Value::Array(vec![]);
    }
    Ok(catalog)
}

fn model_registry_entry_available(repo: &Path, entry: &Value) -> bool {
    let Some(id) = entry.get("id").and_then(|v| v.as_str()) else {
        return false;
    };
    if let Some(rel) = entry.get("weights_dir").and_then(|v| v.as_str()) {
        let p = PathBuf::from(rel);
        let dir = if p.is_absolute() { p } else { repo.join(p) };
        return dir.is_dir();
    }
    release_weights_dir(repo).is_some() && id.contains("cnn-mnist")
}

#[tauri::command]
fn read_models_registry() -> Result<Value, String> {
    let repo = repo_root();
    let path = repo.join("config").join("models-registry.json");
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {}: {}", path.display(), e))?;
    let mut doc: Value =
        serde_json::from_str(&raw).map_err(|e| format!("parse models-registry.json: {e}"))?;
    if let Some(models) = doc.get_mut("models").and_then(|v| v.as_array_mut()) {
        models.retain(|entry| model_registry_entry_available(&repo, entry));
    }
    Ok(doc)
}

fn cp_snark_bin(repo: &Path) -> PathBuf {
    let bundled = repo.join("bin").join("cp-snark-full.exe");
    if bundled.is_file() {
        return bundled;
    }
    for base in [
        repo.join("src").join("proof_generation").join("vPIN_proof_generation"),
        repo.join("src").join("cp-snark-full"),
    ] {
        for profile in ["release", "debug"] {
            let win = base.join("target").join(profile).join("cp-snark-full.exe");
            if win.is_file() {
                return win;
            }
        }
    }
    bundled
}

fn cp_snark_root(repo: &Path) -> PathBuf {
    let bundled = repo.join("data").join("cp-snark");
    if bundled.join("artifacts").is_dir() || repo.join("bin").join("cp-snark-full.exe").is_file() {
        return bundled;
    }
    repo.join("src").join("cp-snark-full")
}

fn proof_registry_path(repo: &Path) -> PathBuf {
    repo.join("config").join("proof-registry.json")
}

fn resolve_proof_run_dir(repo: &Path, model_id: &str) -> Result<(PathBuf, Value), String> {
    let reg_path = proof_registry_path(repo);
    if reg_path.is_file() {
        let raw = std::fs::read_to_string(&reg_path)
            .map_err(|e| format!("read {}: {}", reg_path.display(), e))?;
        let doc: Value =
            serde_json::from_str(&raw).map_err(|e| format!("parse proof-registry.json: {e}"))?;
        if let Some(models) = doc.get("models").and_then(|v| v.as_array()) {
            for entry in models {
                if entry.get("id").and_then(|v| v.as_str()) == Some(model_id) {
                    let rel = entry
                        .get("run_dir")
                        .and_then(|v| v.as_str())
                        .ok_or_else(|| format!("proof-registry missing run_dir for {model_id}"))?;
                    let run_dir = repo.join(rel.replace('/', std::path::MAIN_SEPARATOR_STR));
                    if run_dir.is_dir() {
                        return Ok((run_dir, entry.clone()));
                    }
                }
            }
        }
    }
    if model_id == "cnn-mnist-trained" || model_id == "A" {
        let dev = repo
            .join("model_training")
            .join("outputs")
            .join("20260622_184254");
        if dev.is_dir() {
            return Ok((
                dev,
                serde_json::json!({
                    "id": model_id,
                    "network_id": "A",
                    "schedule_mode": "paper_proof",
                    "total_pt_mul": 178,
                    "total_pt_add": 2144,
                    "n_w": 1219
                }),
            ));
        }
    }
    Err(format!("no proof run_dir for model_id={model_id}"))
}

fn apply_proof_env(cmd: &mut Command, repo: &Path, run_dir: &Path) {
    let trace = run_dir.join("proof_artifacts");
    let witness = trace.join("ec_witness");
    cmd.env("VPIN_REPO_ROOT", repo);
    cmd.env("VPIN_CP_SNARK_ROOT", cp_snark_root(repo));
    cmd.env("VPIN_RUN_DIR", run_dir);
    cmd.env("VPIN_EC_WITNESS_ROOT", &witness);
    cmd.env("VPIN_TRACE_ROOT", &trace);
}

fn run_cp_snark(repo: &Path, run_dir: &Path, args: &[&str]) -> Result<std::process::Output, String> {
    let bin = cp_snark_bin(repo);
    if !bin.is_file() {
        return Err(format!(
            "cp-snark-full not found at {} — build cp-snark-full first",
            bin.display()
        ));
    }
    let mut cmd = Command::new(&bin);
    apply_proof_env(&mut cmd, repo, run_dir);
    cmd.args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd.output().map_err(|e| format!("spawn cp-snark-full: {e}"))
}

fn proof_n_w(run_dir: &Path) -> u32 {
    let manifest = run_dir.join("proof_artifacts").join("proof_manifest.json");
    if let Ok(raw) = std::fs::read_to_string(&manifest) {
        if let Ok(v) = serde_json::from_str::<Value>(&raw) {
            if let Some(n) = v.get("n_w").and_then(|x| x.as_u64()) {
                return n as u32;
            }
        }
    }
    let fw = run_dir.join("proof_artifacts").join("full_weights.json");
    if let Ok(raw) = std::fs::read_to_string(&fw) {
        if let Ok(v) = serde_json::from_str::<Value>(&raw) {
            if let Some(n) = v.get("num_weights").and_then(|x| x.as_u64()) {
                return n as u32;
            }
        }
    }
    1219
}

fn curve_embed_from_registry(repo: &Path) -> Value {
    let reg_path = proof_registry_path(repo);
    if let Ok(raw) = std::fs::read_to_string(&reg_path) {
        if let Ok(doc) = serde_json::from_str::<Value>(&raw) {
            if let Some(ce) = doc.get("curve_embed") {
                return ce.clone();
            }
        }
    }
    serde_json::json!({
        "n2": "7237005577332262213973186563042994240857116359379907606001950938285454250989",
        "q1": "7237005577332262213973186563042994240857116359379907606001950938285454250989",
        "q2": "7237005577332262213973186563042994240704759454384003648147593987722918659549",
        "n2_eq_q1": true
    })
}

#[tauri::command]
fn read_proof_plan(model_id: String) -> Result<Value, String> {
    let repo = repo_root();
    let (run_dir, entry) = resolve_proof_run_dir(&repo, model_id.trim())?;
    let artifacts = run_dir.join("proof_artifacts");
    let witness = artifacts.join("ec_witness");
    let weight_witness = witness.join("pointMult").join("weight.json");
    let files_ok = witness.is_dir() && weight_witness.is_file();
    let total_pt_mul = entry
        .get("total_pt_mul")
        .and_then(|v| v.as_u64())
        .unwrap_or(178) as u32;
    let total_pt_add = entry
        .get("total_pt_add")
        .and_then(|v| v.as_u64())
        .unwrap_or(2144) as u32;
    let n_w = entry
        .get("n_w")
        .and_then(|v| v.as_u64())
        .map(|n| n as u32)
        .unwrap_or_else(|| proof_n_w(&run_dir));
    let schedule_mode = entry
        .get("schedule_mode")
        .and_then(|v| v.as_str())
        .unwrap_or("paper_proof");
    let fw_path = artifacts.join("full_weights.json");
    Ok(serde_json::json!({
        "model_id": model_id,
        "run_dir": run_dir.to_string_lossy(),
        "schedule_mode": schedule_mode,
        "topology": { "network": "A", "pool_k": 4, "n_w": n_w },
        "schedule": { "total_pt_mul": total_pt_mul, "total_pt_add": total_pt_add },
        "witness": {
            "root": witness.to_string_lossy(),
            "files_ok": files_ok
        },
        "w_star": {
            "num_weights": n_w,
            "weights_path": if fw_path.is_file() { Some(fw_path.to_string_lossy().to_string()) } else { None::<String> }
        },
        "curve_embed": curve_embed_from_registry(&repo),
        "proof_artifacts": artifacts.to_string_lossy()
    }))
}

#[derive(Deserialize)]
struct ProofChallengeIn {
    gamma: String,
    gamma_add: String,
    gamma_mult: String,
    num_pt_add: u32,
    num_pt_mult: u32,
}

fn challenge_json_for_rust(ch: &ProofChallengeIn) -> String {
    serde_json::json!({
        "gamma": ch.gamma,
        "gamma_add": ch.gamma_add,
        "gamma_mult": ch.gamma_mult,
        "num_point_adds": ch.num_pt_add,
        "num_point_mults": ch.num_pt_mult,
    })
    .to_string()
}

fn commitments_from_artifact(artifact: &Value) -> Value {
    let mc = artifact.get("model_commitment").unwrap_or(&Value::Null);
    let cm_w = mc.get("cm_weights").unwrap_or(&Value::Null);
    let ic = artifact.get("input_commitment").unwrap_or(&Value::Null);
    let cm_x = ic.get("cm_public").unwrap_or(&Value::Null);
    let cps = artifact.get("cps_commitment").unwrap_or(&Value::Null);
    serde_json::json!({
        "cm_w_hex": cm_w.get("point_hex"),
        "cm_w_digest_hex": cm_w.get("digest_hex"),
        "cm_x_hex": cm_x.get("point_hex"),
        "cm_x_digest_hex": cm_x.get("digest_hex"),
        "cps_cm_hex": cps.get("poly_comm_hex").or_else(|| cps.get("cm_hex"))
    })
}

fn challenge_wire_from_artifact(artifact: &Value) -> Option<Value> {
    let ch = artifact.get("client_challenge")?;
    Some(serde_json::json!({
        "gamma": ch.get("gamma").and_then(|v| v.as_str()).unwrap_or(""),
        "gamma_add": ch.get("gamma_add").and_then(|v| v.as_str()).unwrap_or(""),
        "gamma_mult": ch.get("gamma_mult").and_then(|v| v.as_str()).unwrap_or(""),
        "num_pt_add": ch.get("num_pt_add").or_else(|| ch.get("num_point_adds")).and_then(|v| v.as_u64()).unwrap_or(0),
        "num_pt_mult": ch.get("num_pt_mult").or_else(|| ch.get("num_point_mults")).and_then(|v| v.as_u64()).unwrap_or(0)
    }))
}

fn prove_summary_from_artifact(artifact: &Value) -> Value {
    let mc = artifact.get("model_commitment").unwrap_or(&Value::Null);
    let cm_w = mc.get("cm_weights").unwrap_or(&Value::Null);
    let ic = artifact.get("input_commitment").unwrap_or(&Value::Null);
    let cm_x = ic.get("cm_public").unwrap_or(&Value::Null);
    serde_json::json!({
        "cm_w": cm_w.get("point_hex"),
        "cm_x": cm_x.get("point_hex"),
        "proof_coverage": artifact.get("proof_coverage"),
        "l1_binding_ok": artifact.get("l1_binding_ok"),
        "num_weights": mc.get("num_weights"),
        "prove_ms": artifact.get("prove_time_ms"),
        "verify_ms": artifact.get("verify_time_ms"),
        "has_model_opening": artifact.get("model_opening").map(|v| !v.is_null()).unwrap_or(false)
    })
}

#[tauri::command]
async fn proof_prove(
    session_id: String,
    model_id: String,
    network_id: String,
    challenge: ProofChallengeIn,
) -> Result<Value, String> {
    let _session = session_id;
    let model = model_id;
    let network = network_id;
    let ch = challenge;
    tauri::async_runtime::spawn_blocking(move || {
        let repo = repo_root();
        let (run_dir, _) = resolve_proof_run_dir(&repo, &model)?;
        if ch.gamma.trim().is_empty() {
            return Err("missing client gamma".to_string());
        }
        let art_dir = cp_snark_root(&repo).join("artifacts").join(&network);
        std::fs::create_dir_all(&art_dir).map_err(|e| e.to_string())?;
        let ch_path = art_dir.join("client_challenge.json");
        std::fs::write(&ch_path, challenge_json_for_rust(&ch)).map_err(|e| e.to_string())?;
        let out = run_cp_snark(
            &repo,
            &run_dir,
            &[
                "prove-with-challenge",
                network.as_str(),
                ch_path.to_str().ok_or("challenge path")?,
            ],
        )?;
        if !out.status.success() {
            let stderr = String::from_utf8_lossy(&out.stderr);
            let stdout = String::from_utf8_lossy(&out.stdout);
            return Err(format!("prove failed: {stderr}\n{stdout}"));
        }
        let artifact_path = art_dir.join("protocol.json");
        if !artifact_path.is_file() {
            return Err(format!("missing artifact {}", artifact_path.display()));
        }
        let raw = std::fs::read_to_string(&artifact_path).map_err(|e| e.to_string())?;
        let artifact: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
        Ok(serde_json::json!({
            "ok": true,
            "artifact_path": artifact_path.to_string_lossy(),
            "summary": prove_summary_from_artifact(&artifact),
            "proof_coverage": artifact.get("proof_coverage"),
            "scalar_trace_digest_hex": artifact.get("scalar_trace_digest_hex"),
            "cps_commitment": artifact.get("cps_commitment"),
            "client_challenge": challenge_wire_from_artifact(&artifact),
            "commitments": commitments_from_artifact(&artifact)
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn read_proof_artifact(network: String) -> Result<Value, String> {
    let repo = repo_root();
    let net = network.trim();
    let artifact = cp_snark_root(&repo)
        .join("artifacts")
        .join(net)
        .join("protocol.json");
    if !artifact.is_file() {
        return Err(format!("missing {}", artifact.display()));
    }
    let raw = std::fs::read_to_string(&artifact).map_err(|e| e.to_string())?;
    let mut data: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    if let Value::Object(ref mut map) = data {
        map.insert(
            "artifact_path".to_string(),
            Value::String(artifact.to_string_lossy().to_string()),
        );
    }
    Ok(data)
}

#[tauri::command]
fn proof_verify(network: String) -> Result<Value, String> {
    let repo = repo_root();
    let net = network.trim();
    let artifact = cp_snark_root(&repo)
        .join("artifacts")
        .join(net)
        .join("protocol.json");
    if !artifact.is_file() {
        return Err(format!("missing {}", artifact.display()));
    }
    let (run_dir, _) = resolve_proof_run_dir(&repo, "cnn-mnist-trained")
        .or_else(|_| resolve_proof_run_dir(&repo, "A"))?;
    let out = run_cp_snark(
        &repo,
        &run_dir,
        &["verify-file", artifact.to_str().ok_or("artifact path")?],
    )?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        let stdout = String::from_utf8_lossy(&out.stdout);
        return Err(format!("verify failed: {stderr}\n{stdout}"));
    }
    Ok(serde_json::json!({
        "ok": true,
        "artifact_path": artifact.to_string_lossy(),
        "message": "cp-snark-full verify-file PASSED"
    }))
}

#[tauri::command]
fn write_text_file(path: String, contents: String) -> Result<(), String> {
    let p = Path::new(path.trim());
    if let Some(parent) = p.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
    }
    std::fs::write(p, contents).map_err(|e| e.to_string())
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
            ensure_runtime_artifacts,
            ensure_ahe_server,
            ping_ahe_server_health,
            get_communication_profile,
            ahe_preprocess,
            ahe_preprocess_batch,
            preprocess_dataset_single,
            preprocess_dataset_batch,
            preprocess_upload_file,
            ahe_preprocess_rust,
            ahe_preprocess_batch_rust,
            preprocess_upload_file_rust,
            run_ahe_inference,
            run_ahe_batch_inference,
            read_datasets_catalog,
            read_models_registry,
            read_proof_plan,
            proof_prove,
            read_proof_artifact,
            proof_verify,
            write_text_file
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
