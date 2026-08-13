use std::path::PathBuf;

#[derive(Clone, Debug)]
pub struct PlatformConfig {
    pub repo_root: PathBuf,
    pub weights_dir: PathBuf,
    pub bsgs_table: PathBuf,
    pub server_host: String,
    pub server_port: u16,
}

impl PlatformConfig {
    pub fn load() -> Self {
        let repo = ahe_model_bundle::detect_repo_root();
        let weights = std::env::var("VPIN_WEIGHTS_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| ahe_model_bundle::default_network_a_weights_dir(&repo));
        let bsgs = std::env::var("VPIN_BSGS_TABLE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                let release = repo.join("data/bsgs/table.bin");
                if release.is_file() {
                    return release;
                }
                let fixture_bin = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../../tests/fixtures/table.bin");
                if fixture_bin.is_file() {
                    return fixture_bin;
                }
                let repo_bin = repo.join("src/Pre_computed_table/table.bin");
                if repo_bin.is_file() {
                    return repo_bin;
                }
                repo.join("src/Pre_computed_table/table.pickle")
            });
        Self {
            repo_root: repo.clone(),
            weights_dir: weights,
            bsgs_table: bsgs,
            server_host: std::env::var("AHE_SERVER_HOST").unwrap_or_else(|_| "127.0.0.1".into()),
            server_port: std::env::var("AHE_SERVER_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(8001),
        }
    }

    pub fn ws_url(&self) -> String {
        format!(
            "ws://{}:{}/api/v1/session/ws",
            self.server_host, self.server_port
        )
    }
}
