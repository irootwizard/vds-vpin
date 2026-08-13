use cp_snark_full::challenge::ClientChallenge;
use cp_snark_full::{
    load_artifacts, prover_run, prover_with_challenge_json,
    run_full_protocol, sample_challenge_json, save_artifacts, setup_and_commit, verifier_from_path,
    verifier_run,
};
use std::env;
use std::fs;
use std::path::PathBuf;

fn print_usage() {
    eprintln!("Usage:");
    eprintln!("  cp-snark-full full <network>              Run complete CP-SNARK protocol");
    eprintln!("  cp-snark-full setup <network>               Setup + commitments (W* + cm_x)");
    eprintln!("  cp-snark-full prove <network>               Server: prove (local γ sample)");
    eprintln!("  cp-snark-full verify <network>              Client: verify artifacts/protocol.json");
    eprintln!("  cp-snark-full sample-challenge <network>    Client: emit challenge JSON (stdout)");
    eprintln!("  cp-snark-full prove-with-challenge <net> <challenge.json>");
    eprintln!("  cp-snark-full prove-layer <network>          M5 per-layer π stubs");
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        print_usage();
        std::process::exit(1);
    }

    let cmd = args[1].as_str();
    let network = args[2].as_str();

    match cmd {
        "full" => {
            println!("=== CP-SNARK Full Protocol (network={}) ===", network);
            let artifacts = run_full_protocol(network);
            println!("Model commitment (cm_W): {}", artifacts.model_commitment.cm_weights.point_hex);
            println!("Input commitment (cm_x): {}", artifacts.input_commitment.cm_public.point_hex);
            println!("num_weights: {}", artifacts.model_commitment.num_weights);
            println!("proof_coverage: {}", artifacts.proof_coverage);
            println!(
                "Client challenge gamma: {}",
                artifacts.client_challenge.gamma
            );
            println!("Prove time: {} ms", artifacts.prove_time_ms);
            println!("Verify time: {} ms", artifacts.verify_time_ms);
            println!("Artifacts saved to artifacts/{}/protocol.json", network);
            println!("Client verification: PASSED");
        }
        "setup" => {
            let (model, input, weights) = setup_and_commit(network);
            println!("Setup complete for network={}", network);
            println!("  weights count: {}", weights.len());
            println!("  cm_W: {}", model.cm_weights.point_hex);
            println!("  cm_x: {}", input.cm_public.point_hex);
            println!("  E2 base field n_2 (curveBaseField): {}", model.curve_e2.curve_base_field);
            println!("  E2 subgroup order q_2 (curveOrder): {}", model.curve_e2.curve_order);
        }
        "sample-challenge" => {
            let json = sample_challenge_json(network).expect("sample challenge");
            println!("{json}");
        }
        "prove-with-challenge" => {
            if args.len() < 4 {
                eprintln!("Usage: prove-with-challenge <network> <challenge.json>");
                std::process::exit(1);
            }
            let challenge_path = PathBuf::from(&args[3]);
            let challenge_json =
                fs::read_to_string(&challenge_path).expect("read challenge json");
            let artifacts =
                prover_with_challenge_json(network, &challenge_json).expect("prove");
            save_artifacts(&artifacts).expect("save");
            println!("Proof generated (client γ) for network={}", network);
            println!("  proof_coverage: {}", artifacts.proof_coverage);
            println!("  prove time: {} ms", artifacts.prove_time_ms);
        }
        "prove" => {
            let (num_point_mults, _, _, _, _) =
                cp_snark_full::load_data::load_data(network).expect("load_data");
            let (num_point_adds, _, _, _, _, _) =
                cp_snark_full::load_data_add::load_data_add(network).expect("load_data_add");
            let challenge = ClientChallenge::sample(num_point_adds, num_point_mults);
            let artifacts = prover_run(network, challenge);
            save_artifacts(&artifacts).expect("save");
            println!("Proof generated and saved for network={}", network);
            println!("  proof_coverage: {}", artifacts.proof_coverage);
            println!("  prove time: {} ms", artifacts.prove_time_ms);
        }
        "verify" => {
            let artifacts = load_artifacts(network).expect("load artifacts");
            verifier_run(&artifacts).expect("verification failed");
            println!("Client verification PASSED for network={}", network);
        }
        "verify-file" => {
            let path = PathBuf::from(network);
            verifier_from_path(&path).expect("verification failed");
            println!("Client verification PASSED for {:?}", path);
        }
        "prove-layer" => {
            use cp_snark_full::prove::layer::prove_layers_for_network;
            let bundle = prove_layers_for_network(network).expect("prove-layer");
            let dir = PathBuf::from("artifacts").join(network);
            std::fs::create_dir_all(&dir).expect("mkdir artifacts");
            let out = dir.join("layer_proofs.json");
            let payload = serde_json::json!({
                "network": network,
                "pi_conv_hex": bundle.pi_conv.as_ref().map(hex::encode),
                "pi_pool_hex": bundle.pi_pool.as_ref().map(hex::encode),
                "pi_fc_hex": bundle.pi_fc.iter().map(hex::encode).collect::<Vec<_>>(),
                "proof_coverage": "layer_proofs_partial",
            });
            std::fs::write(&out, serde_json::to_string_pretty(&payload).unwrap()).expect("write");
            println!("Layer proofs written to {}", out.display());
        }
        _ => {
            print_usage();
            std::process::exit(1);
        }
    }
}
