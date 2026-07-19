use thiserror::Error;

#[derive(Error, Debug)]
pub enum OvdsError {
    #[error("BLS error: {0}")]
    Bls(String),

    #[error("RSA error: {0}")]
    Rsa(String),

    #[error("Verification failed: {0}")]
    Verification(String),

    #[error("Index not found: {0}")]
    NotFound(u64),

    #[error("Hash error: {0}")]
    Hash(String),

    #[error("Invalid parameter: {0}")]
    InvalidParam(String),
}
