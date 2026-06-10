use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use vpin_server_crypto::circuit::cps_ver::{
    prove_toy_cps, verify_toy_cps_bundle, ToyCpsTraces,
};
use vpin_server_crypto::circuit::layer::{
    conv_mac::ConvToyTrace, fc_mac::FcToyTrace, pool_sum::PoolToyTrace,
};
use vpin_server_crypto::{
    prove_with_challenge, save_artifacts, setup_model, verify_pedersen_open_model,
    ClientChallenge, ModelCommitmentBundle, ModelCommitmentOpening, ProverError,
    ServerProveInput, SetupBundle, TraceBundleRef,
};
use vpin_server_crypto::load_data::{ec_witness_root, witness_available};

fn print_usage() {
    eprintln!("Usage:");
    eprintln!("  vpin-server-crypto setup <network> [weights.json]");
    eprintln!("  vpin-server-crypto prove-with-challenge <network> <challenge.json> [setup.json]");
    eprintln!("  vpin-server-crypto verify-pedersen <setup.json>");
    eprintln!("  vpin-server-crypto verify-cps --toy");
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        print_usage();
        std::process::exit(1);
    }

    let cmd = args[1].as_str();

    // `verify-cps` is the only subcommand that does not take a positional
    // <network> arg.
    if cmd == "verify-cps" {
        let toy = args.iter().any(|a| a == "--toy");
        if !toy {
            eprintln!("Usage: verify-cps --toy");
            std::process::exit(1);
        }
        match run_verify_cps_toy() {
            Ok(()) => {
                println!("cps_ver_unified_toy_ok");
            }
            Err(e) => {
                eprintln!("verify-cps --toy failed: {e}");
                std::process::exit(1);
            }
        }
        return;
    }

    if args.len() < 3 {
        print_usage();
        std::process::exit(1);
    }
    let network = args[2].as_str();

    match cmd {
        "setup" => match run_setup(network, args.get(3).map(String::as_str)) {
            Ok(path) => {
                println!("Setup artifacts written to {}", path.display());
            }
            Err(e) => {
                eprintln!("setup failed: {e}");
                std::process::exit(1);
            }
        },
        "verify-pedersen" => {
            if args.len() < 3 {
                eprintln!("Usage: verify-pedersen <setup.json>");
                std::process::exit(1);
            }
            let path = PathBuf::from(&args[2]);
            match run_verify_pedersen(&path) {
                Ok(true) => println!("pedersen_open_ok"),
                Ok(false) => {
                    eprintln!("pedersen opening verification failed");
                    std::process::exit(1);
                }
                Err(e) => {
                    eprintln!("verify-pedersen failed: {e}");
                    std::process::exit(1);
                }
            }
        }
        "prove-with-challenge" => {
            if args.len() < 4 {
                eprintln!("Usage: prove-with-challenge <network> <challenge.json> [setup.json]");
                std::process::exit(1);
            }
            let challenge_path = PathBuf::from(&args[3]);
            let setup_path = args.get(4).map(|s| PathBuf::from(s));
            match run_prove(network, &challenge_path, setup_path.as_deref()) {
                Ok(path) => {
                    println!("Proof artifacts written to {}", path.display());
                }
                Err(e) => {
                    eprintln!("prove-with-challenge failed: {e}");
                    std::process::exit(1);
                }
            }
        }
        _ => {
            print_usage();
            std::process::exit(1);
        }
    }
}

fn run_setup(network: &str, weights_path: Option<&str>) -> Result<PathBuf, String> {
    let weights = load_weights(weights_path, network)?;
    let setup = setup_model(network, &weights).map_err(|e| e.to_string())?;
    write_setup_json(network, &setup)
}

fn run_prove(
    network: &str,
    challenge_path: &PathBuf,
    setup_path: Option<&Path>,
) -> Result<PathBuf, String> {
    let challenge_json = fs::read_to_string(challenge_path)
        .map_err(|e| format!("read challenge: {e}"))?;
    let challenge: ClientChallenge =
        serde_json::from_str(&challenge_json).map_err(|e| format!("parse challenge: {e}"))?;

    let setup = if let Some(path) = setup_path {
        read_setup_json(path)?
    } else {
        let default = default_setup_path(network);
        if default.is_file() {
            read_setup_json(&default)?
        } else {
            let weights = load_weights(None, network)?;
            setup_model(network, &weights).map_err(|e| e.to_string())?
        }
    };

    let input = ServerProveInput {
        network_id: network.to_string(),
        challenge,
        cm_w: setup.model_commitment.clone(),
        cm_x: setup.input_commitment.clone(),
        model_opening: setup.model_opening.clone(),
        input_opening: None,
        trace_bundle: TraceBundleRef {
            conv_trace: None,
            pool_trace: None,
            fc_trace: None,
        },
        ec_witness_root: resolve_ec_witness_root(network),
    };

    let artifacts = prove_with_challenge(input).map_err(|e| match e {
        ProverError::MissingClientGamma => {
            "missing client gamma — server must not sample γ".to_string()
        }
        other => other.to_string(),
    })?;
    save_artifacts(&artifacts).map_err(|e| e.to_string())
}

fn default_setup_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("artifacts")
        .join(network)
        .join("setup.json")
}

fn write_setup_json(network: &str, setup: &SetupBundle) -> Result<PathBuf, String> {
    let dir = default_setup_path(network).parent().unwrap().to_path_buf();
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join("setup.json");
    let payload = serde_json::json!({
        "network_id": setup.network_id,
        "model_commitment": setup.model_commitment,
        "input_commitment": setup.input_commitment,
        "model_opening": setup.model_opening,
        "num_weights": setup.weights.len(),
    });
    fs::write(&path, serde_json::to_string_pretty(&payload).unwrap())
        .map_err(|e| e.to_string())?;
    Ok(path)
}

fn read_setup_json(path: &Path) -> Result<SetupBundle, String> {
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    Ok(SetupBundle {
        network_id: v["network_id"]
            .as_str()
            .unwrap_or("A")
            .to_string(),
        model_commitment: serde_json::from_value(v["model_commitment"].clone())
            .map_err(|e| e.to_string())?,
        input_commitment: serde_json::from_value(v["input_commitment"].clone())
            .map_err(|e| e.to_string())?,
        model_opening: serde_json::from_value(v["model_opening"].clone())
            .map_err(|e| e.to_string())?,
        weights: Vec::new(),
    })
}

fn load_weights(weights_path: Option<&str>, network: &str) -> Result<Vec<u128>, String> {
    if let Some(path) = weights_path {
        return parse_weights_file(Path::new(path));
    }
    let default = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../src/cp-snark-full/model_exports")
        .join(network)
        .join("full_weights.json");
    if default.is_file() {
        return parse_weights_file(&default);
    }
    Ok(vec![1u128, 2, 3])
}

fn resolve_ec_witness_root(network: &str) -> Option<PathBuf> {
    if std::env::var("VPIN_EC_REAL_PROVE").ok().as_deref() != Some("1") {
        return None;
    }
    let root = ec_witness_root(network);
    if witness_available(network) && root.is_dir() {
        Some(root)
    } else {
        None
    }
}

fn run_verify_pedersen(path: &Path) -> Result<bool, String> {
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: serde_json::Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    let model: ModelCommitmentBundle =
        serde_json::from_value(v["model_commitment"].clone()).map_err(|e| e.to_string())?;
    let opening: ModelCommitmentOpening =
        serde_json::from_value(v["model_opening"].clone()).map_err(|e| e.to_string())?;
    Ok(verify_pedersen_open_model(&model, &opening))
}

fn run_verify_cps_toy() -> Result<(), String> {
    let w_star: Vec<u128> = vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7];
    let traces = ToyCpsTraces {
        conv: ConvToyTrace {
            filter: vec![1, 0, 1, 2, 0, 2, 1, 0, 1],
            windows: vec![
                vec![1, 2, 3, 5, 6, 7, 9, 10, 11],
                vec![2, 3, 4, 6, 7, 8, 10, 11, 12],
                vec![5, 6, 7, 9, 10, 11, 13, 14, 15],
                vec![6, 7, 8, 10, 11, 12, 14, 15, 16],
            ],
            outputs: vec![48, 56, 80, 88],
        },
        pool: PoolToyTrace {
            windows: vec![vec![48, 56, 80, 88]],
            outputs: vec![272],
        },
        fc: FcToyTrace {
            input: 272,
            weights: vec![2, 3],
            bias: vec![5, 7],
            outputs: vec![549, 823],
        },
    };
    let challenge = ClientChallenge {
        gamma: "11".repeat(32),
        gamma_add: "22".repeat(32),
        gamma_mult: "33".repeat(32),
        num_point_adds: 0,
        num_point_mults: 0,
    };
    let (bundle, prove_timing) = prove_toy_cps(&w_star, &traces, &challenge)
        .map_err(|e| format!("prove_toy_cps: {e}"))?;
    let verify_timing = verify_toy_cps_bundle(&bundle, Some(&traces))
        .map_err(|e| format!("verify_toy_cps_bundle: {e}"))?;
    println!(
        "verify-cps --toy: cm_W kind={} num_scalars={} padded_len={} prove_ms={{conv:{},pool:{},fc:{}}} verify_total_ms={}",
        bundle.cm_w.kind,
        bundle.cm_w.num_scalars,
        bundle.cm_w.padded_len,
        prove_timing.prove_ms_conv,
        prove_timing.prove_ms_pool,
        prove_timing.prove_ms_fc,
        verify_timing.total_ms,
    );
    Ok(())
}

fn parse_weights_file(path: &Path) -> Result<Vec<u128>, String> {
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if let Ok(parsed) = serde_json::from_str::<Vec<String>>(&raw) {
        return parsed
            .iter()
            .map(|s| s.parse::<u128>().map_err(|e| format!("weight {s}: {e}")))
            .collect();
    }
    let v: serde_json::Value = serde_json::from_str(&raw).map_err(|e| format!("parse weights: {e}"))?;
    let arr = v
        .get("w_star_flat")
        .or_else(|| v.get("weights"))
        .and_then(|x| x.as_array())
        .ok_or_else(|| "expected weight array or w_star_flat".to_string())?;
    arr.iter()
        .map(|item| {
            let owned = item.to_string();
            let s = item.as_str().unwrap_or(&owned);
            s.parse::<u128>().map_err(|e| format!("weight {s}: {e}"))
        })
        .collect()
}
