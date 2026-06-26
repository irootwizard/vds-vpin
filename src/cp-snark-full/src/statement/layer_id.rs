use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LayerKind {
    Convolution,
    AveragePooling,
    FullyConnected,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LayerId {
    pub kind: LayerKind,
    pub index: u8,
}

impl LayerId {
    pub const fn conv() -> Self {
        Self {
            kind: LayerKind::Convolution,
            index: 0,
        }
    }

    pub const fn pool() -> Self {
        Self {
            kind: LayerKind::AveragePooling,
            index: 0,
        }
    }

    pub const fn fc(index: u8) -> Self {
        Self {
            kind: LayerKind::FullyConnected,
            index,
        }
    }
}
