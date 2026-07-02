/// Build the BSGS precomputed table (table.bin) for the E2 curve.
///
/// Computes j*G for j = 0..BSGS_M using iterative projective addition,
/// writes the BSG1 binary format expected by BsgsTable::load().
///
/// Usage:
///   cargo run -p ahe-cli --bin bsgs-build --release -- [output_path]
///
/// Default output: <repo_root>/src/Pre_computed_table/table.bin

use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::Instant;

use ahe_codec::BSGS_M;
use ahe_crypto_e2::{CurveE2, E2Projective};
use num_bigint::BigUint;

const MAGIC: &[u8; 4] = b"BSG1";

fn repo_root() -> PathBuf {
    if let Ok(r) = std::env::var("VPIN_REPO_ROOT") {
        let p = PathBuf::from(r);
        if p.is_dir() {
            return p;
        }
    }
    let mut dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for _ in 0..8 {
        if dir.join("vpin-client").is_dir() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let out_path = if let Some(p) = args.get(1) {
        PathBuf::from(p)
    } else {
        repo_root()
            .join("src")
            .join("Pre_computed_table")
            .join("table.bin")
    };

    let m = BSGS_M as usize;
    eprintln!("Generating BSGS table: m={m}");
    eprintln!("Output: {}", out_path.display());

    // Generator in projective coordinates.
    let g: E2Projective = CurveE2::mul_generator(&BigUint::from(1u32));
    let mut cur: E2Projective = CurveE2::identity();

    // Pre-allocate: 16-byte header + m * 68-byte entries.
    let entry_size = 68usize;
    let total_bytes = 16 + m * entry_size;
    let mut buf = Vec::with_capacity(total_bytes);

    buf.extend_from_slice(MAGIC);
    buf.extend_from_slice(&(BSGS_M).to_le_bytes());      // u32 LE
    buf.extend_from_slice(&(m as u64).to_le_bytes());    // u64 LE

    let t0 = Instant::now();
    let report_every = m / 10;

    for j in 0u32..BSGS_M {
        if report_every > 0 && j as usize % report_every == 0 {
            let pct = j as f64 / m as f64 * 100.0;
            eprintln!("  {:.0}%  ({j}/{m})  {:.1}s", pct, t0.elapsed().as_secs_f64());
        }

        let (x, y) = CurveE2::lookup_key(&cur);   // identity → ([0;32],[0;32])
        buf.extend_from_slice(&x);
        buf.extend_from_slice(&y);
        buf.extend_from_slice(&j.to_le_bytes());

        cur = CurveE2::add_projective(&cur, &g);
    }

    eprintln!("  100%  done in {:.1}s — writing …", t0.elapsed().as_secs_f64());

    if let Some(parent) = out_path.parent() {
        fs::create_dir_all(parent).expect("create dir");
    }
    let mut file = fs::File::create(&out_path).expect("create file");
    file.write_all(&buf).expect("write");
    file.flush().expect("flush");

    let mb = buf.len() as f64 / 1024.0 / 1024.0;
    eprintln!("Written {} ({:.1} MB)", out_path.display(), mb);
}
