use axum::{
    extract::State,
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use tower_http::cors::{Any, CorsLayer};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[derive(Clone)]
struct AppState {
    server_id: String,
}

#[derive(Serialize)]
struct HealthResponse {
    status: String,
    server_id: String,
    timestamp: String,
}

#[derive(Serialize)]
struct ModelInfo {
    id: String,
    name: String,
    description: String,
}

#[derive(Serialize)]
struct ModelsResponse {
    models: Vec<ModelInfo>,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "vpin_server=debug,tower_http=debug,axum=debug".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let state = AppState {
        server_id: uuid::Uuid::new_v4().to_string(),
    };

    let app = Router::new()
        .route("/api/v1/health", get(health_check))
        .route("/api/v1/models", get(list_models))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], 8000));
    tracing::info!("vPIN server listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("Failed to bind address");

    axum::serve(listener, app)
        .await
        .expect("Server error");
}

async fn health_check(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok".to_string(),
        server_id: state.server_id,
        timestamp: chrono::Utc::now().to_rfc3339(),
    })
}

async fn list_models() -> Json<ModelsResponse> {
    Json(ModelsResponse {
        models: vec![
            ModelInfo {
                id: "network-a".to_string(),
                name: "CNN Network A".to_string(),
                description: "MNIST CNN model with CP-SNARK support".to_string(),
            },
        ],
    })
}
