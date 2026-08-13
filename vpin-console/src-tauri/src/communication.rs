//! 通信端点解析与 AHE 推理服探活（与 lib.rs 进程/路径逻辑解耦）。

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::Path;
use std::process::Command;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HttpEndpoint {
    pub http_base: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AheEndpoint {
    pub host: String,
    pub port: u16,
    pub http_base: String,
    pub ws_session: String,
    pub skip_local_server: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommunicationProfile {
    pub backend: HttpEndpoint,
    pub ahe: AheEndpoint,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ovds: Option<HttpEndpoint>,
}

#[derive(Debug, Deserialize)]
struct ClientEndpointsFile {
    backend: Option<FileHttpEndpoint>,
    ahe: Option<FileAheEndpoint>,
    ovds: Option<FileHttpEndpoint>,
}

#[derive(Debug, Deserialize)]
struct FileHttpEndpoint {
    http_base: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FileAheEndpoint {
    host: Option<String>,
    port: Option<u16>,
    http_base: Option<String>,
    skip_local_server: Option<bool>,
}

fn env_truthy(name: &str) -> bool {
    std::env::var(name)
        .map(|v| {
            let s = v.trim().to_ascii_lowercase();
            matches!(s.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

fn normalize_base(raw: &str) -> String {
    raw.trim_end_matches('/').to_string()
}

fn default_backend_base() -> String {
    std::env::var("VITE_BACKEND_URL")
        .map(|s| normalize_base(&s))
        .unwrap_or_else(|_| "http://127.0.0.1:8000/api/v1".into())
}

fn default_ahe_host() -> String {
    std::env::var("AHE_SERVER_HOST").unwrap_or_else(|_| "127.0.0.1".into())
}

fn default_ahe_port() -> u16 {
    std::env::var("AHE_SERVER_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(8001)
}

fn ahe_http_base(host: &str, port: u16) -> String {
    std::env::var("VITE_AHE_SERVER_URL")
        .map(|s| normalize_base(&s))
        .unwrap_or_else(|_| format!("http://{host}:{port}/api/v1"))
}

fn ws_session_url(host: &str, port: u16) -> String {
    format!("ws://{host}:{port}/api/v1/session/ws")
}

fn read_client_endpoints_file(repo: &Path) -> Option<ClientEndpointsFile> {
    let path = repo.join("config").join("client-endpoints.json");
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn load_profile(repo: &Path) -> CommunicationProfile {
    let mut backend_base = default_backend_base();
    let mut ahe_host = default_ahe_host();
    let mut ahe_port = default_ahe_port();
    let mut skip_local = env_truthy("VPIN_SKIP_LOCAL_AHE");
    let mut ovds: Option<HttpEndpoint> = None;

    if let Some(file) = read_client_endpoints_file(repo) {
        if let Some(b) = file.backend.and_then(|x| x.http_base) {
            backend_base = normalize_base(&b);
        }
        if let Some(a) = file.ahe {
            if let Some(h) = a.host {
                ahe_host = h;
            }
            if let Some(p) = a.port {
                ahe_port = p;
            }
            if let Some(s) = a.skip_local_server {
                skip_local = s;
            }
        }
        if let Some(o) = file.ovds.and_then(|x| x.http_base) {
            ovds = Some(HttpEndpoint {
                http_base: normalize_base(&o),
            });
        }
    }

    let ahe_base = read_client_endpoints_file(repo)
        .and_then(|f| f.ahe)
        .and_then(|a| a.http_base)
        .map(|s| normalize_base(&s))
        .unwrap_or_else(|| ahe_http_base(&ahe_host, ahe_port));
    CommunicationProfile {
        backend: HttpEndpoint {
            http_base: backend_base,
        },
        ahe: AheEndpoint {
            host: ahe_host.clone(),
            port: ahe_port,
            http_base: ahe_base,
            ws_session: ws_session_url(&ahe_host, ahe_port),
            skip_local_server: skip_local,
        },
        ovds,
    }
}

/// 指定引擎端口（8001/8002）的 AHE 目标；host 来自环境/配置文件。
pub fn ahe_target(port: u16) -> AheEndpoint {
    let host = default_ahe_host();
    let skip_local = env_truthy("VPIN_SKIP_LOCAL_AHE");
    let http_base = ahe_http_base(&host, port);
    AheEndpoint {
        host: host.clone(),
        port,
        http_base,
        ws_session: ws_session_url(&host, port),
        skip_local_server: skip_local,
    }
}

pub fn apply_ahe_env(cmd: &mut Command, port: u16) {
    let ep = ahe_target(port);
    cmd.env("AHE_SERVER_HOST", &ep.host)
        .env("AHE_SERVER_PORT", ep.port.to_string());
}

pub fn http_health_ok(host: &str, port: u16) -> bool {
    let Ok(mut stream) = TcpStream::connect(format!("{host}:{port}")) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let req = format!(
        "GET /api/v1/health HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = Vec::new();
    let mut chunk = [0u8; 1024];
    loop {
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(_) => break,
        }
    }
    let body = String::from_utf8_lossy(&buf);
    body.contains("200 OK") && body.contains("ok")
}

pub fn ping_ahe_health(port: u16) -> Value {
    let ep = ahe_target(port);
    if !http_health_ok(&ep.host, ep.port) {
        return json!({ "ok": false, "host": ep.host, "port": ep.port });
    }
    json!({
        "ok": true,
        "runtime": "vpin-backend-ahe-server",
        "host": ep.host,
        "port": ep.port
    })
}

pub fn ensure_ahe_skip_local_result(port: u16) -> Result<Value, String> {
    let ep = ahe_target(port);
    if http_health_ok(&ep.host, ep.port) {
        return Ok(json!({
            "started": false,
            "port": ep.port,
            "host": ep.host,
            "status": "remote_ok",
            "skip_local": true
        }));
    }
    Err(format!(
        "远程 ahe-server {}:{} 不可达（VPIN_SKIP_LOCAL_AHE=1，未尝试本地启动）",
        ep.host, ep.port
    ))
}

pub fn ensure_ahe_already_running(port: u16) -> Option<Value> {
    let ep = ahe_target(port);
    if http_health_ok(&ep.host, ep.port) {
        Some(json!({
            "started": false,
            "port": ep.port,
            "host": ep.host,
            "status": "ok"
        }))
    } else {
        None
    }
}

pub fn should_skip_local_ahe() -> bool {
    env_truthy("VPIN_SKIP_LOCAL_AHE")
}
