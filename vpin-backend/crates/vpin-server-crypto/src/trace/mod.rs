//! Witness JSON loaders (`rust_files/{network}/`).

pub mod load_data;
pub mod load_data_add;

pub use load_data::{load_data, rust_files_root, witness_available};
pub use load_data_add::load_data_add;
