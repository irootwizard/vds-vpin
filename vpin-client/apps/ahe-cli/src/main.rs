use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;

use ahe_client::{
    load_bsgs, load_bsgs_ec, load_official_preprocessed, official_batch_to_ui_json,
    official_to_ui_json, preprocess_upload_path, run_ahe_session, run_ahe_session_ec,
    upload_path_to_ui_json, MnistLoadError, PlatformConfig, PreprocessedSample, ProgressCb,
    MNIST_TEST_LEN,
};
use clap::{Parser, Subcommand, ValueEnum};
use rand::thread_rng;

#[derive(Clone, Copy, Debug, ValueEnum)]
enum CryptoBackend {
    Ark,
    Ec,
}

#[derive(Parser)]
#[command(name = "ahe-cli", about = "vpin-client Rust AHE inference CLI")]
struct Cli {
    #[command(subcommand)]
    cmd: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Single-image AHE inference
    Infer {
        #[arg(long, default_value = "cnn-mnist-trained")]
        model: String,
        #[arg(long, default_value = "0")]
        mnist_index: i32,
        /// Preprocessed sample JSON (overrides official MNIST load)
        #[arg(long)]
        sample_json: Option<PathBuf>,
        /// Local image file — preprocessed via vpin_client (upload pipeline)
        #[arg(long)]
        image: Option<PathBuf>,
        #[arg(long, value_enum, default_value_t = CryptoBackend::Ark)]
        crypto_backend: CryptoBackend,
        #[arg(long)]
        progress_ndjson: bool,
    },
    /// Batch AHE evaluation
    EvalMnistAhe {
        #[arg(long, default_value = "cnn-mnist-trained")]
        model: String,
        #[arg(long, default_value = "0")]
        start: u32,
        #[arg(long, default_value = "10")]
        limit: usize,
        #[arg(long)]
        indices: Option<String>,
        #[arg(long)]
        jobs_json: Option<PathBuf>,
        #[arg(long, default_value = "1")]
        concurrency: usize,
        #[arg(long)]
        progress: bool,
        #[arg(long)]
        progress_ndjson: bool,
        #[arg(long, value_enum, default_value_t = CryptoBackend::Ark)]
        crypto_backend: CryptoBackend,
    },
    /// Official MNIST preprocess (UI JSON)
    Preprocess {
        #[arg(long, default_value = "0")]
        mnist_index: i32,
    },
    /// Batch official MNIST preprocess (UI JSON)
    PreprocessBatch {
        #[arg(long, default_value = "0")]
        start: u32,
        #[arg(long, default_value = "10")]
        count: u32,
    },
    /// Upload image preprocess (UI JSON)
    PreprocessUpload {
        path: PathBuf,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    let cfg = PlatformConfig::load();
    match cli.cmd {
        Commands::Preprocess { mnist_index } => {
            let json = official_to_ui_json(&cfg.repo_root, mnist_index)?;
            println!("{}", serde_json::to_string(&json)?);
        }
        Commands::PreprocessBatch { start, count } => {
            let json = official_batch_to_ui_json(&cfg.repo_root, start, count)?;
            println!("{}", serde_json::to_string(&json)?);
        }
        Commands::PreprocessUpload { path } => {
            let json = upload_path_to_ui_json(&path)?;
            println!("{}", serde_json::to_string(&json)?);
        }
        Commands::Infer {
            model,
            mnist_index,
            sample_json,
            image,
            crypto_backend,
            progress_ndjson,
        } => {
            let sample = load_sample(&cfg, mnist_index, sample_json.as_deref(), image.as_deref())?;
            let on_progress = progress_cb(progress_ndjson);
            let result = match crypto_backend {
                CryptoBackend::Ark => {
                    let bsgs = load_bsgs(&cfg.bsgs_table)?;
                    run_ahe_session(
                        &cfg.ws_url(),
                        &model,
                        &sample.fixed,
                        &sample.shape,
                        &bsgs,
                        None,
                        Some(sample.mnist_index),
                        Some(sample.label),
                    )
                    .await?
                }
                CryptoBackend::Ec => {
                    let bsgs = load_bsgs_ec(&cfg.bsgs_table)?;
                    run_ahe_session_ec(
                        &cfg.ws_url(),
                        &model,
                        &sample.fixed,
                        &sample.shape,
                        &bsgs,
                        None,
                        Some(sample.mnist_index),
                        Some(sample.label),
                        on_progress,
                    )
                    .await?
                }
            };
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "prediction": result.prediction,
                    "label": result.label,
                    "logits": result.logits,
                    "timing": {
                        "preprocess_ms": result.timing.preprocess_ms,
                        "encrypt_ms": result.timing.encrypt_ms,
                        "decrypt_ms": result.timing.decrypt_ms,
                        "client_crypto_ms": result.timing.client_crypto_ms,
                        "server_wait_ms": result.timing.server_wait_ms,
                        "network_ms": result.timing.network_ms,
                        "ws_ms": result.timing.ws_ms,
                        "crypto_infer_ms": result.timing.crypto_infer_ms,
                        "total_ms": result.timing.total_ms,
                    },
                }))?
            );
        }
        Commands::EvalMnistAhe {
            model,
            start,
            limit,
            indices,
            jobs_json,
            concurrency,
            progress,
            progress_ndjson,
            crypto_backend,
        } => {
            let jobs = resolve_batch_jobs(&cfg, &model, start, limit, indices, jobs_json)?;
            let report = run_batch(
                &cfg,
                &model,
                jobs,
                concurrency,
                progress,
                progress_ndjson,
                crypto_backend,
            )
            .await?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            let out = PathBuf::from(format!(
                "reports/batch_{}_{}.json",
                report["limit"].as_u64().unwrap_or(0),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)?
                    .as_secs()
            ));
            std::fs::create_dir_all("reports")?;
            std::fs::write(&out, serde_json::to_string_pretty(&report)?)?;
            eprintln!("Wrote {}", out.display());
        }
    }
    Ok(())
}

struct Sample {
    mnist_index: i32,
    fixed: Vec<i32>,
    shape: Vec<usize>,
    label: i32,
}

fn progress_cb(enabled: bool) -> Option<ProgressCb> {
    if !enabled {
        return None;
    }
    Some(Arc::new(|v| {
        eprintln!("{}", v);
    }))
}

fn sample_from_preprocessed(p: PreprocessedSample) -> Sample {
    Sample {
        mnist_index: p.mnist_index,
        fixed: p.fixed,
        shape: p.shape,
        label: p.label,
    }
}

fn load_sample(
    cfg: &PlatformConfig,
    mnist_index: i32,
    sample_json: Option<&Path>,
    image: Option<&Path>,
) -> anyhow::Result<Sample> {
    if let Some(path) = sample_json {
        return load_sample_from_json(path);
    }
    if let Some(img) = image {
        return load_upload_rust(img);
    }
    match load_official_preprocessed(&cfg.repo_root, mnist_index) {
        Ok(p) => Ok(sample_from_preprocessed(p)),
        Err(MnistLoadError::RawNotFound(_)) => load_mnist_via_python(&cfg.repo_root, mnist_index),
        Err(e) => Err(e.into()),
    }
}

fn load_sample_from_json(path: &Path) -> anyhow::Result<Sample> {
    let entry: serde_json::Value = serde_json::from_slice(&std::fs::read(path)?)?;
    parse_sample_entry(&entry)
}

fn parse_sample_entry(entry: &serde_json::Value) -> anyhow::Result<Sample> {
    let shape: Vec<usize> = entry["shape"]
        .as_array()
        .or_else(|| entry.get("fixed_shape").and_then(|v| v.as_array()))
        .ok_or_else(|| anyhow::anyhow!("sample missing shape"))?
        .iter()
        .map(|v| v.as_u64().unwrap() as usize)
        .collect();
    let fixed: Vec<i32> = entry["fixed_int32"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("sample missing fixed_int32"))?
        .iter()
        .map(|v| v.as_i64().unwrap() as i32)
        .collect();
    Ok(Sample {
        mnist_index: entry["mnist_index"].as_i64().unwrap_or(0) as i32,
        fixed,
        shape,
        label: entry["label"].as_i64().unwrap_or(-1) as i32,
    })
}

fn venv_python(repo: &Path) -> PathBuf {
    let win = repo.join(".venv").join("Scripts").join("python.exe");
    if win.is_file() {
        return win;
    }
    repo.join(".venv").join("bin").join("python")
}

fn load_upload_rust(image: &Path) -> anyhow::Result<Sample> {
    let (stages, _filename) = preprocess_upload_path(image)?;
    Ok(Sample {
        mnist_index: -1,
        fixed: stages.fixed,
        shape: vec![1, 1, 32, 32],
        label: -1,
    })
}

fn load_mnist_via_python(repo: &Path, index: i32) -> anyhow::Result<Sample> {
    if !(0..MNIST_TEST_LEN).contains(&index) {
        anyhow::bail!("mnist index must be 0..9999, got {index}");
    }
    let python = venv_python(repo);
    let script = format!(
        r#"import json, sys
from vpin_client.data.official import load_official_test
r = load_official_test(int(sys.argv[1]))
print(json.dumps({{
    "mnist_index": r.mnist_index,
    "label": r.label,
    "shape": list(r.fixed_int32.shape),
    "fixed_int32": r.fixed_int32.reshape(-1).tolist(),
}}))"#
    );
    let out = Command::new(&python)
        .args(["-c", &script, &index.to_string()])
        .current_dir(repo)
        .output()?;
    if !out.status.success() {
        anyhow::bail!("{}", String::from_utf8_lossy(&out.stderr).trim());
    }
    parse_sample_entry(&serde_json::from_slice::<serde_json::Value>(&out.stdout)?)
}

fn emit_progress_ndjson(enabled: bool, phase: &str, data: serde_json::Value) {
    if !enabled {
        return;
    }
    let mut map = serde_json::Map::new();
    map.insert("kind".into(), serde_json::json!("progress"));
    map.insert("phase".into(), serde_json::json!(phase));
    if let Some(obj) = data.as_object() {
        for (k, v) in obj {
            map.insert(k.clone(), v.clone());
        }
    }
    eprintln!("{}", serde_json::Value::Object(map));
}

struct BatchJobEntry {
    job_id: String,
    mnist_index: Option<i32>,
    image_path: Option<PathBuf>,
    sample: Sample,
}

fn job_id_for_entry(entry: &serde_json::Value, slot: usize) -> String {
    if let Some(idx) = entry.get("mnist_index").and_then(|v| v.as_i64()) {
        return format!("mnist-{idx}");
    }
    if let Some(uid) = entry.get("upload_id").and_then(|v| v.as_str()) {
        return format!("upload-{}", &uid[..uid.len().min(12)]);
    }
    if let Some(path) = entry.get("image_path").and_then(|v| v.as_str()) {
        return format!("image-{}", Path::new(path).file_name().and_then(|s| s.to_str()).unwrap_or("file"));
    }
    format!("job-{slot}")
}

fn resolve_batch_jobs(
    cfg: &PlatformConfig,
    model: &str,
    start: u32,
    limit: usize,
    indices: Option<String>,
    jobs_json: Option<PathBuf>,
) -> anyhow::Result<Vec<BatchJobEntry>> {
    let mut entries: Vec<serde_json::Value> = Vec::new();
    if let Some(path) = jobs_json {
        let raw: serde_json::Value = serde_json::from_slice(&std::fs::read(path)?)?;
        entries = if raw.is_array() {
            raw.as_array().cloned().unwrap_or_default()
        } else {
            raw.get("jobs")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_default()
        };
    } else if let Some(s) = indices {
        for part in s.split(',') {
            let part = part.trim();
            if !part.is_empty() {
                entries.push(serde_json::json!({"mnist_index": part.parse::<i32>()?}));
            }
        }
    } else {
        if start as u64 + limit as u64 > MNIST_TEST_LEN as u64 {
            anyhow::bail!("start+limit exceeds MNIST test set");
        }
        for i in 0..limit {
            entries.push(serde_json::json!({"mnist_index": (start as i32) + i as i32}));
        }
    }

    let mut jobs = Vec::new();
    for (slot, entry) in entries.iter().enumerate() {
        let jid = job_id_for_entry(entry, slot);
        let mnist_index = entry.get("mnist_index").and_then(|v| v.as_i64()).map(|v| v as i32);
        let image_path = entry
            .get("image_path")
            .and_then(|v| v.as_str())
            .map(PathBuf::from);
        let sample = if let Some(ref img) = image_path {
            load_upload_rust(img)?
        } else if let Some(idx) = mnist_index {
            load_sample(cfg, idx, None, None)?
        } else if let Some(uid) = entry.get("upload_id").and_then(|v| v.as_str()) {
            load_upload_id_via_python(&cfg.repo_root, uid)?
        } else {
            anyhow::bail!("job {jid} missing mnist_index, image_path, or upload_id");
        };
        let _ = model; // reserved for per-job model override
        jobs.push(BatchJobEntry {
            job_id: jid,
            mnist_index,
            image_path,
            sample,
        });
    }
    Ok(jobs)
}

fn load_upload_id_via_python(repo: &Path, upload_id: &str) -> anyhow::Result<Sample> {
    let python = venv_python(repo);
    let uid = upload_id.replace('\'', "''");
    let script = format!(
        r#"import json
from vpin_client.data.input_loader import load_inference_input
r = load_inference_input(upload_id='{uid}')
print(json.dumps({{
    "mnist_index": r.mnist_index if r.mnist_index is not None else -1,
    "label": r.label if r.label is not None else -1,
    "shape": list(r.fixed_int32.shape),
    "fixed_int32": r.fixed_int32.reshape(-1).tolist(),
}}))"#
    );
    let out = Command::new(&python)
        .args(["-c", &script])
        .current_dir(repo)
        .output()?;
    if !out.status.success() {
        anyhow::bail!("{}", String::from_utf8_lossy(&out.stderr).trim());
    }
    parse_sample_entry(&serde_json::from_slice::<serde_json::Value>(&out.stdout)?)
}

async fn run_batch(
    cfg: &PlatformConfig,
    model: &str,
    jobs: Vec<BatchJobEntry>,
    concurrency: usize,
    progress: bool,
    progress_ndjson: bool,
    crypto: CryptoBackend,
) -> anyhow::Result<serde_json::Value> {
    use std::time::Instant;
    use tokio::sync::Semaphore;

    let total = jobs.len();
    let job_keys: Vec<String> = jobs.iter().map(|j| j.job_id.clone()).collect();
    emit_progress_ndjson(
        progress_ndjson,
        "batch_start",
        serde_json::json!({
            "total": total,
            "concurrency": concurrency,
            "engine": format!("rust-{}", match crypto { CryptoBackend::Ark => "ark", CryptoBackend::Ec => "ec" }),
            "model_id": model,
            "job_keys": job_keys,
        }),
    );

    let t0 = Instant::now();
    let sem = Arc::new(Semaphore::new(concurrency.max(1)));
    let mut handles = Vec::new();

    match crypto {
        CryptoBackend::Ark => {
            let bsgs = load_bsgs(&cfg.bsgs_table)?;
            let mut rng = thread_rng();
            let shared_keys = ahe_crypto_e2::KeyMaterial::key_gen(&mut rng);
            for (slot, job) in jobs.into_iter().enumerate() {
                emit_progress_ndjson(
                    progress_ndjson,
                    "batch_item_start",
                    serde_json::json!({
                        "slot": slot,
                        "job_id": job.job_id,
                        "mnist_index": job.mnist_index,
                        "image_path": job.image_path.as_ref().map(|p| p.to_string_lossy().to_string()),
                    }),
                );
                let permit = sem.clone().acquire_owned().await?;
                let cfg = cfg.clone();
                let model = model.to_string();
                let keys = shared_keys.clone();
                let bsgs = Arc::clone(&bsgs);
                let job_id = job.job_id.clone();
                let label = job.sample.label;
                let sample = job.sample;
                let h = tokio::spawn(async move {
                    let _p = permit;
                    run_ahe_session(
                        &cfg.ws_url(),
                        &model,
                        &sample.fixed,
                        &sample.shape,
                        &bsgs,
                        Some(keys),
                        Some(sample.mnist_index),
                        Some(sample.label),
                    )
                    .await
                    .map(|r| (job_id, label, r))
                });
                handles.push((slot, h));
            }
        }
        CryptoBackend::Ec => {
            let bsgs = load_bsgs_ec(&cfg.bsgs_table)?;
            for (slot, job) in jobs.into_iter().enumerate() {
                emit_progress_ndjson(
                    progress_ndjson,
                    "batch_item_start",
                    serde_json::json!({
                        "slot": slot,
                        "job_id": job.job_id,
                        "mnist_index": job.mnist_index,
                        "image_path": job.image_path.as_ref().map(|p| p.to_string_lossy().to_string()),
                    }),
                );
                let permit = sem.clone().acquire_owned().await?;
                let cfg = cfg.clone();
                let model = model.to_string();
                let bsgs = Arc::clone(&bsgs);
                let job_id = job.job_id.clone();
                let label = job.sample.label;
                let sample = job.sample;
                let stream = progress_ndjson && concurrency <= 1;
                let on_progress = progress_cb(stream);
                let h = tokio::spawn(async move {
                    let _p = permit;
                    run_ahe_session_ec(
                        &cfg.ws_url(),
                        &model,
                        &sample.fixed,
                        &sample.shape,
                        &bsgs,
                        None,
                        Some(sample.mnist_index),
                        Some(sample.label),
                        on_progress,
                    )
                    .await
                    .map(|r| (job_id, label, r))
                });
                handles.push((slot, h));
            }
        }
    }

    let mut results = Vec::new();
    let mut correct = 0usize;
    let mut total_session_ms = 0.0f64;
    let mut completed = 0usize;
    for (slot, h) in handles {
        completed += 1;
        match h.await? {
            Ok((job_id, label, r)) => {
                total_session_ms += r.timing.crypto_infer_ms;
                let ok = r.prediction == label;
                if ok {
                    correct += 1;
                }
                let elapsed_s = t0.elapsed().as_secs_f64();
                emit_progress_ndjson(
                    progress_ndjson,
                    "batch_item_done",
                    serde_json::json!({
                        "slot": slot,
                        "job_id": job_id,
                        "prediction": r.prediction,
                        "label": label,
                        "correct_item": ok,
                        "completed": completed,
                        "total": total,
                        "correct": correct,
                        "accuracy": correct as f64 / completed as f64,
                        "elapsed_s": elapsed_s,
                        "eta_s": elapsed_s / completed as f64 * (total - completed) as f64,
                        "timing": {
                            "crypto_infer_ms": r.timing.crypto_infer_ms,
                            "client_crypto_ms": r.timing.client_crypto_ms,
                            "total_ms": r.timing.total_ms,
                        },
                    }),
                );
                if progress {
                    eprintln!(
                        "[ {}/{} ] job={} correct={} acc={:.1}%",
                        completed,
                        total,
                        job_id,
                        correct,
                        (correct as f64 / completed as f64) * 100.0
                    );
                }
                results.push(serde_json::json!({
                    "job_id": job_id,
                    "mnist_index": r.mnist_index,
                    "label": label,
                    "prediction": r.prediction,
                    "correct": ok,
                    "logits": r.logits,
                    "timing": {
                        "encrypt_ms": r.timing.encrypt_ms,
                        "decrypt_ms": r.timing.decrypt_ms,
                        "client_crypto_ms": r.timing.client_crypto_ms,
                        "server_wait_ms": r.timing.server_wait_ms,
                        "network_ms": r.timing.network_ms,
                        "ws_ms": r.timing.ws_ms,
                        "crypto_infer_ms": r.timing.crypto_infer_ms,
                        "total_ms": r.timing.total_ms,
                    },
                }));
            }
            Err(e) => {
                emit_progress_ndjson(
                    progress_ndjson,
                    "batch_item_done",
                    serde_json::json!({
                        "slot": slot,
                        "failed": true,
                        "error": e.to_string(),
                        "completed": completed,
                        "total": total,
                    }),
                );
            }
        }
    }

    let elapsed_s = t0.elapsed().as_secs_f64();
    let report = serde_json::json!({
        "limit": total,
        "correct": correct,
        "accuracy": if total > 0 { correct as f64 / total as f64 } else { 0.0 },
        "concurrency": concurrency,
        "elapsed_s": elapsed_s,
        "img_per_s": if elapsed_s > 0.0 { total as f64 / elapsed_s } else { 0.0 },
        "avg_crypto_infer_ms": if total > 0 { total_session_ms / total as f64 } else { 0.0 },
        "results": results,
        "engine": format!("rust-{}", match crypto { CryptoBackend::Ark => "ark", CryptoBackend::Ec => "ec" }),
    });
    emit_progress_ndjson(progress_ndjson, "batch_done", serde_json::json!({ "report": report }));
    Ok(report)
}
