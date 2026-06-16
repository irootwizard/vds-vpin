use serde::{Deserialize, Serialize};

use super::layer_id::{LayerId, LayerKind};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NetworkTopology {
    pub network_id: String,
    pub layers: Vec<LayerId>,
}

impl NetworkTopology {
    pub fn for_network(network: &str) -> Self {
        let layers = match network {
            "L2" | "L4" => vec![LayerId::conv()],
            _ => vec![
                LayerId::conv(),
                LayerId::pool(),
                LayerId::fc(0),
                LayerId::fc(1),
            ],
        };
        Self {
            network_id: network.to_string(),
            layers,
        }
    }

    pub fn digest_message(&self) -> Vec<u8> {
        let mut msg = format!("vpin-topology:{}", self.network_id);
        for lid in &self.layers {
            let kind_b = match lid.kind {
                LayerKind::Convolution => 0u8,
                LayerKind::AveragePooling => 1u8,
                LayerKind::FullyConnected => 2u8,
            };
            msg.push('|');
            msg.push_str(&format!("{kind_b}:{}", lid.index));
        }
        msg.into_bytes()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn topology_a_has_four_layers() {
        let t = NetworkTopology::for_network("A");
        assert_eq!(t.layers.len(), 4);
        assert_eq!(t.layers[0].kind, LayerKind::Convolution);
    }
}
