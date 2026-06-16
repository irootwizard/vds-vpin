//! Assemble `layer_proof` specs from [`ModelParams`](crate::model::ModelParams) + trace.

use crate::layer_proof::{
    ConvLayerProofSpec, FcLayerProofSpec, PoolLayerProofSpec, ServerLinearProofStack,
};
use crate::model::{load_model_params, ModelParams};
use crate::trace::conv::ConvWitnessSource;
use crate::trace::ec::EcTrace;

#[derive(Clone, Debug)]
pub struct BuildStackInput<'a> {
    pub model: &'a ModelParams,
    pub ec: &'a EcTrace,
    pub conv: ConvWitnessSource,
    /// Per-window pool values + sums; `None` until pool trace export exists.
    pub pool: Option<PoolTraceInput>,
    /// FC layer activations: must align with `model.fc.len()` when present.
    pub fc: Vec<FcTraceInput>,
}

#[derive(Clone, Debug)]
pub struct PoolTraceInput {
    pub windows: Vec<Vec<u128>>,
    pub output_sums: Vec<u128>,
}

#[derive(Clone, Debug)]
pub struct FcTraceInput {
    pub inputs: Vec<u128>,
    pub outputs: Vec<u128>,
}

#[derive(Clone, Debug)]
pub struct LinearStackWitness {
    pub stack: ServerLinearProofStack,
    pub ec: EcTrace,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BuildStackError {
    ConvWindowsMissing,
    ConvParse(String),
    PoolMissing,
    FcLayerCount { expected: usize, got: usize },
    ModelLoad(String),
}

pub fn build_linear_stack(input: &BuildStackInput<'_>) -> Result<LinearStackWitness, BuildStackError> {
    let conv = match &input.conv {
        ConvWitnessSource::TraceJson { bundle } => {
            Some(bundle.to_proof_spec().map_err(BuildStackError::ConvParse)?)
        }
        ConvWitnessSource::RecomputePlaintext { padded, stride } => {
            Some(ConvLayerProofSpec::from_plaintext_conv(
                padded,
                &filter_to_2d(&input.model.conv.filter_flat),
                *stride,
            ))
        }
        ConvWitnessSource::Missing => None,
    };

    let pool = input.pool.as_ref().map(|p| PoolLayerProofSpec {
        windows: p.windows.clone(),
        output_sums: p.output_sums.clone(),
        inv_k_squared_fp: input.model.pool.inv_k_squared_fp,
    });

    if input.model.fc.len() != input.fc.len() {
        return Err(BuildStackError::FcLayerCount {
            expected: input.model.fc.len(),
            got: input.fc.len(),
        });
    }

    let fc_layers: Vec<FcLayerProofSpec> = input
        .model
        .fc
        .iter()
        .zip(input.fc.iter())
        .map(|(params, trace)| FcLayerProofSpec {
            weights_in_out: params.weights.clone(),
            bias: params.bias.clone(),
            inputs: trace.inputs.clone(),
            outputs: trace.outputs.clone(),
        })
        .collect();

    Ok(LinearStackWitness {
        stack: ServerLinearProofStack {
            conv,
            pool,
            fc_layers,
        },
        ec: input.ec.clone(),
    })
}

fn filter_to_2d(flat: &[u128]) -> Vec<Vec<u128>> {
    if flat.len() != 9 {
        return vec![flat.to_vec()];
    }
    vec![
        vec![flat[0], flat[1], flat[2]],
        vec![flat[3], flat[4], flat[5]],
        vec![flat[6], flat[7], flat[8]],
    ]
}

/// Same as `build_stack_for_network` (architecture draft name).
pub fn build_linear_stack_optional(network: &str) -> Result<LinearStackWitness, BuildStackError> {
    build_stack_for_network(network)
}

/// Convenience: load model + EC JSON, conv from `conv_trace.json` if present.
pub fn build_stack_for_network(network: &str) -> Result<LinearStackWitness, BuildStackError> {
    let model = load_model_params(network).map_err(|e| BuildStackError::ModelLoad(e.to_string()))?;
    let ec = crate::trace::ec::load_ec_trace(network)
        .map_err(|e| BuildStackError::ModelLoad(e.to_string()))?;
    let conv = crate::trace::conv::resolve_conv_source(network, None);
    if matches!(conv, ConvWitnessSource::Missing) {
        return Err(BuildStackError::ConvWindowsMissing);
    }
    let pool = crate::trace::pool::load_pool_trace(network)
        .map_err(|e| BuildStackError::ModelLoad(e))?;
    let fc = crate::trace::fc::load_fc_traces(network)
        .map_err(|e| BuildStackError::ModelLoad(e))?;

    build_linear_stack(&BuildStackInput {
        model: &model,
        ec: &ec,
        conv,
        pool,
        fc,
    })
}
