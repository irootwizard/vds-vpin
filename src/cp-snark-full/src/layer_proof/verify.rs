//! Scalar verification of per-layer computational statements (paper algorithms, no cm_W).

use libspartan::scalar::Scalar;

use super::common::challenge_for_stage;
use super::conv::ConvLayerProofSpec;
use super::fc::FcLayerProofSpec;
use super::pool::PoolLayerProofSpec;
use super::rlc::{conv_rlc_left, conv_rlc_right, fc_rlc_left, fc_rlc_right, mac_filter_window};
use super::common::LayerProofStage;
use crate::challenge::ClientChallenge;
use crate::curve::embed_u128_to_scalar;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LayerProofError {
    DimensionMismatch { stage: LayerProofStage, detail: String },
    EquationFailed { stage: LayerProofStage, detail: String },
    RlcMismatch { stage: LayerProofStage },
}

pub type LayerProofResult<T> = Result<T, LayerProofError>;

/// Verify all per-cell MACs (paper Eq. 5 / (6) spirit): â[i] = ⟨f, window_i⟩.
pub fn verify_conv_eq5_per_cell(spec: &ConvLayerProofSpec) -> LayerProofResult<()> {
    if spec.output_flat.len() != spec.windows.len() {
        return Err(LayerProofError::DimensionMismatch {
            stage: LayerProofStage::Convolution,
            detail: format!(
                "outputs {} vs windows {}",
                spec.output_flat.len(),
                spec.windows.len()
            ),
        });
    }
    for (i, window) in spec.windows.iter().enumerate() {
        let mac = mac_filter_window(&spec.filter_flat, window);
        let out = embed_u128_to_scalar(spec.output_flat[i]);
        if mac != out {
            return Err(LayerProofError::EquationFailed {
                stage: LayerProofStage::Convolution,
                detail: format!("cell {i}: mac != output"),
            });
        }
    }
    Ok(())
}

/// Verify compressed RLC (paper Eq. 9) with verifier γ (RLC only, no per-cell Eq. 5).
pub fn verify_conv_eq9_rlc_only(
    spec: &ConvLayerProofSpec,
    challenge: &ClientChallenge,
) -> LayerProofResult<()> {
    let gamma = challenge_for_stage(LayerProofStage::Convolution, challenge);
    let left = conv_rlc_left(&spec.output_flat, &gamma);
    let right = conv_rlc_right(&spec.filter_flat, &spec.windows, &gamma);
    if left != right {
        return Err(LayerProofError::RlcMismatch {
            stage: LayerProofStage::Convolution,
        });
    }
    Ok(())
}

/// Verify compressed RLC (paper Eq. 9) with verifier γ.
pub fn verify_conv_eq9_rlc(
    spec: &ConvLayerProofSpec,
    challenge: &ClientChallenge,
) -> LayerProofResult<()> {
    verify_conv_eq5_per_cell(spec)?;
    let gamma = challenge_for_stage(LayerProofStage::Convolution, challenge);
    let left = conv_rlc_left(&spec.output_flat, &gamma);
    let right = conv_rlc_right(&spec.filter_flat, &spec.windows, &gamma);
    if left != right {
        return Err(LayerProofError::RlcMismatch {
            stage: LayerProofStage::Convolution,
        });
    }
    Ok(())
}

/// Average pooling: JB = sum of window (paper Eq. 7, homomorphic sum before public scale).
pub fn verify_pool_eq7_per_cell(spec: &PoolLayerProofSpec) -> LayerProofResult<()> {
    if spec.output_sums.len() != spec.windows.len() {
        return Err(LayerProofError::DimensionMismatch {
            stage: LayerProofStage::AveragePooling,
            detail: format!(
                "sums {} vs windows {}",
                spec.output_sums.len(),
                spec.windows.len()
            ),
        });
    }
    for (i, window) in spec.windows.iter().enumerate() {
        let mut acc = Scalar::zero();
        for &v in window {
            acc += embed_u128_to_scalar(v);
        }
        let expected = embed_u128_to_scalar(spec.output_sums[i]);
        if acc != expected {
            return Err(LayerProofError::EquationFailed {
                stage: LayerProofStage::AveragePooling,
                detail: format!("window {i}: sum != output_sums"),
            });
        }
    }
    Ok(())
}

/// FC per output (paper Eq. 8): t[j] = Σ_k W[k,j]·d[k] + b[j].
pub fn verify_fc_eq8_per_output(spec: &FcLayerProofSpec) -> LayerProofResult<()> {
    let out_dim = spec.outputs.len();
    if spec.bias.len() != out_dim {
        return Err(LayerProofError::DimensionMismatch {
            stage: LayerProofStage::FullyConnected,
            detail: "bias vs outputs".into(),
        });
    }
    for j in 0..out_dim {
        let mut mac = Scalar::zero();
        for (k, row) in spec.weights_in_out.iter().enumerate() {
            let w = row.get(j).copied().unwrap_or(0);
            let d = spec.inputs.get(k).copied().unwrap_or(0);
            mac += embed_u128_to_scalar(w) * embed_u128_to_scalar(d);
        }
        mac += embed_u128_to_scalar(spec.bias[j]);
        if mac != embed_u128_to_scalar(spec.outputs[j]) {
            return Err(LayerProofError::EquationFailed {
                stage: LayerProofStage::FullyConnected,
                detail: format!("output {j}"),
            });
        }
    }
    Ok(())
}

/// FC compressed RLC (paper Eq. 10) with verifier γ′ (RLC only, no per-output Eq. 8).
pub fn verify_fc_eq10_rlc_only(
    spec: &FcLayerProofSpec,
    challenge: &ClientChallenge,
) -> LayerProofResult<()> {
    let gamma_prime = challenge_for_stage(LayerProofStage::FullyConnected, challenge);
    let left = fc_rlc_left(&spec.outputs, &gamma_prime);
    let right = fc_rlc_right(
        &spec.inputs,
        &spec.weights_in_out,
        &spec.bias,
        &gamma_prime,
    );
    if left != right {
        return Err(LayerProofError::RlcMismatch {
            stage: LayerProofStage::FullyConnected,
        });
    }
    Ok(())
}

/// FC compressed RLC (paper Eq. 10) with verifier γ′.
pub fn verify_fc_eq10_rlc(
    spec: &FcLayerProofSpec,
    challenge: &ClientChallenge,
) -> LayerProofResult<()> {
    verify_fc_eq8_per_output(spec)?;
    let gamma_prime = challenge_for_stage(LayerProofStage::FullyConnected, challenge);
    let left = fc_rlc_left(&spec.outputs, &gamma_prime);
    let right = fc_rlc_right(
        &spec.inputs,
        &spec.weights_in_out,
        &spec.bias,
        &gamma_prime,
    );
    if left != right {
        return Err(LayerProofError::RlcMismatch {
            stage: LayerProofStage::FullyConnected,
        });
    }
    Ok(())
}
