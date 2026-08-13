use ahe_crypto_e2::E2Point;
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::json;
use thiserror::Error;

pub const AHE_V1_MAGIC: &[u8; 4] = b"ahe1";

#[derive(Clone, Debug)]
pub struct AheV1Chunk {
    pub phase_id: String,
    pub part: String,
    pub chunk_index: u32,
    pub total_chunks: u32,
    pub payload: Vec<u8>,
}

#[derive(Error, Debug)]
pub enum WireError {
    #[error("wire: {0}")]
    Msg(String),
}

pub fn encode_ahe_v1_chunks(
    phase_id: &str,
    part: &str,
    points: &[E2Point],
    cells_per_chunk: usize,
) -> Result<Vec<AheV1Chunk>, WireError> {
    if cells_per_chunk == 0 {
        return Err(WireError::Msg("cells_per_chunk=0".into()));
    }
    let total = points.len().div_ceil(cells_per_chunk) as u32;
    let mut chunks = Vec::new();
    for (ci, chunk_pts) in points.chunks(cells_per_chunk).enumerate() {
        let mut payload = Vec::with_capacity(4 + 4 + 4 + chunk_pts.len() * 64);
        payload.extend_from_slice(AHE_V1_MAGIC);
        payload.extend_from_slice(&(chunk_pts.len() as u32).to_le_bytes());
        payload.push(0); // dtype object
        for p in chunk_pts {
            let (x, y) = point_to_coords(p);
            payload.extend_from_slice(&x);
            payload.extend_from_slice(&y);
        }
        chunks.push(AheV1Chunk {
            phase_id: phase_id.to_string(),
            part: part.to_string(),
            chunk_index: ci as u32,
            total_chunks: total,
            payload,
        });
    }
    Ok(chunks)
}

pub fn decode_ahe_v1_tensor(chunks: &[Vec<u8>]) -> Result<Vec<E2Point>, WireError> {
    let mut out = Vec::new();
    for payload in chunks {
        if payload.len() < 9 || &payload[0..4] != AHE_V1_MAGIC {
            return Err(WireError::Msg("bad ahe1 chunk".into()));
        }
        let n = u32::from_le_bytes(payload[4..8].try_into().unwrap()) as usize;
        let mut off = 9usize;
        for _ in 0..n {
            if off + 64 > payload.len() {
                return Err(WireError::Msg("truncated cell".into()));
            }
            let mut x = [0u8; 32];
            let mut y = [0u8; 32];
            x.copy_from_slice(&payload[off..off + 32]);
            off += 32;
            y.copy_from_slice(&payload[off..off + 32]);
            off += 32;
            out.push(coords_to_point(&x, &y));
        }
    }
    Ok(out)
}

fn point_to_coords(p: &E2Point) -> ([u8; 32], [u8; 32]) {
    match p {
        E2Point::Identity => ([0u8; 32], [0u8; 32]),
        E2Point::Affine { x, y } => (*x, *y),
    }
}

fn coords_to_point(x: &[u8; 32], y: &[u8; 32]) -> E2Point {
    if *x == [0u8; 32] && *y == [0u8; 32] {
        E2Point::Identity
    } else {
        E2Point::Affine { x: *x, y: *y }
    }
}

pub fn chunk_to_ws_frame(chunk: &AheV1Chunk) -> serde_json::Value {
    json!({
        "type": "ciphertext_chunk",
        "phase_id": chunk.phase_id,
        "part": chunk.part,
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
        "encoding": "ahe-v1",
        "payload_b64": STANDARD.encode(&chunk.payload),
    })
}
