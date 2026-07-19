use axum::{routing::{get, post}, Router, extract::Query, Json};
use std::{net::SocketAddr, collections::HashMap};
use std::sync::Arc;
use tokio::sync::RwLock;

mod routes;

pub struct AppState {
    pub vk: RwLock<Option<ovds_core::VerificationKey>>,
    pub server_state: RwLock<Option<ovds_core::ServerState>>,
    pub sk: RwLock<Option<ovds_core::SecretKey>>,
    pub db: sled::Db,
}

pub type SharedState = Arc<AppState>;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let db = sled::open("ovds_data").expect("sled open");
    let state = SharedState::new(AppState {
        vk: RwLock::new(None), server_state: RwLock::new(None),
        sk: RwLock::new(None), db,
    });

    if let Err(e) = routes::try_restore(&state).await {
        tracing::warn!("No persisted state: {e}");
    }

    let query_state = state.clone();

    let app = Router::new()
        .route("/health", get(health))
        .route("/setup", post(routes::setup))
        .route("/append", post(routes::append))
        .route("/append_batch", post(routes::append_batch))
        .route("/query_batch", post(routes::query_batch))
        .route("/query", post(routes::query_single))
        .route("/query", get(move |Query(params): Query<HashMap<String, String>>| {
            let state = query_state.clone();
            async move {
                let idx: u64 = params.get("index").and_then(|v| v.parse().ok()).unwrap_or(0);
                let ss = state.server_state.read().await;
                match &*ss {
                    Some(ss) => match ovds_core::protocol::query(ss, idx) {
                        Ok(resp) => Json(serde_json::json!({
                            "index": resp.index,
                            "value": resp.value.to_str_radix(10),
                            "proof": {
                                "sigma_hex": hex::encode(&resp.proof.sigma.0),
                                "tag_hex": hex::encode(&resp.proof.tag.to_bytes_be()),
                            }
                        })),
                        Err(e) => Json(serde_json::json!({"error": e.to_string()})),
                    },
                    None => Json(serde_json::json!({"error": "not setup"})),
                }
            }
        }))
        .route("/verify", post(routes::verify))
        .route("/verify_batch", post(routes::verify_batch))
        .with_state(state);

    let addr: SocketAddr = "127.0.0.1:9000".parse().unwrap();
    tracing::info!("OVDS server listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn health() -> &'static str { r#"{"status":"ok","runtime":"ovds-server"}"# }
