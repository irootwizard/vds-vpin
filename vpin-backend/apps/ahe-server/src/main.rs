use ahe_client::PlatformConfig;
use axum::{routing::get, Router};
use std::net::SocketAddr;

mod ws;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    let cfg = PlatformConfig::load();
    let app = Router::new()
        .route("/api/v1/health", get(health))
        .route("/api/v1/session/ws", get(ws::session_ws));

    let addr: SocketAddr = format!("{}:{}", cfg.server_host, cfg.server_port)
        .parse()
        .expect("addr parse");
    tracing::info!("ahe-server listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn health() -> &'static str {
    r#"{"status":"ok","runtime":"vpin-backend-ahe-server"}"#
}
