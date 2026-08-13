import {
  enrichModel,
  resolveInferencePlan,
  resolvePerfProfileKey,
  type EnrichedModel,
  type InferencePlan,
  type PerfProfileKey,
} from "@/config/modelCatalog";
import { isStrictNetworkAModel } from "@/config/networkAProof";
import { isCifarDataset, isMnistDataset } from "@/services/custodyDataset";

export type GovernanceStatus = "real_ahe" | "mock" | "blocked";

/** 模型族（与训练产物解耦，仅用于治理评估） */
export type ModelArchetype = "network_a" | "lenet" | "resnet";

export type DatasetKind = "mnist" | "cifar";

export interface HomomorphicFeasibility {
  status: GovernanceStatus;
  canLaunch: boolean;
  statusLabel: string;
  statusType: "success" | "warning" | "error" | "info";
  compatibilityOk: boolean;
  compatibilityDetail: string;
  modelArchetype: ModelArchetype;
  datasetKind: DatasetKind | null;
  pairLabel: string;
  inferencePlan: InferencePlan;
  perfProfileKey: PerfProfileKey;
  /** 假定该组合已训练时的参考准确度（%） */
  expectedAccuracyPct: number;
  mockBatchDisplayPct: number | null;
  checks: { id: string; label: string; pass: boolean; detail: string }[];
}

const ARCHETYPE_LABEL: Record<ModelArchetype, string> = {
  network_a: "Simple CNN · Network A",
  lenet: "LeNet",
  resnet: "ResNet",
};

const DATASET_LABEL: Record<DatasetKind, string> = {
  mnist: "MNIST",
  cifar: "CIFAR-10",
};

/**
 * 假定各模型族×数据集均已训练时的参考准确度（%）。
 * 仅 network_a×cifar 不可用（值为 0，由兼容性逻辑阻断）。
 */
const PAIR_ACCURACY_PCT: Record<ModelArchetype, Record<DatasetKind, number>> = {
  network_a: { mnist: 92.91, cifar: 0 },
  lenet: { mnist: 98.3, cifar: 56.19 },
  resnet: { mnist: 99.56, cifar: 57.4 },
};

export function resolveModelArchetype(
  model: Pick<EnrichedModel, "id" | "family">,
): ModelArchetype {
  if (isStrictNetworkAModel(model.id)) return "network_a";
  if (model.family === "resnet_cifar" || /resnet/i.test(model.id)) return "resnet";
  return "lenet";
}

export function datasetKindFromId(datasetId: string): DatasetKind | null {
  if (isMnistDataset(datasetId)) return "mnist";
  if (isCifarDataset(datasetId)) return "cifar";
  return null;
}

export function formatModelDatasetPair(
  archetype: ModelArchetype,
  kind: DatasetKind,
): string {
  return `${ARCHETYPE_LABEL[archetype]} × ${DATASET_LABEL[kind]}`;
}

/** 假定已训练：按模型族×数据集查表；registry 准确度仅作同组合时的补充 */
export function resolvePairAccuracyPct(
  archetype: ModelArchetype,
  kind: DatasetKind,
  registryAccuracy?: number,
): number {
  const table = PAIR_ACCURACY_PCT[archetype][kind];
  if (table > 0) return table;
  if (registryAccuracy != null && registryAccuracy > 0) return registryAccuracy;
  return table;
}

export function evaluateDatasetModelCompatibility(
  archetype: ModelArchetype,
  datasetId: string,
): { ok: boolean; detail: string; kind: DatasetKind | null } {
  const kind = datasetKindFromId(datasetId);
  if (!kind) {
    return { ok: false, detail: "请选择 MNIST 或 CIFAR-10 数据集", kind: null };
  }
  if (archetype === "network_a" && kind === "cifar") {
    return {
      ok: false,
      detail: "Simple CNN Network A 不适用于 CIFAR-10",
      kind,
    };
  }
  return {
    ok: true,
    detail: `${formatModelDatasetPair(archetype, kind)} · 可同态推理评估`,
    kind,
  };
}

export function evaluateHomomorphicFeasibility(
  model: EnrichedModel | null,
  modelId: string,
  datasetId: string,
  aheCapableIds: Set<string>,
  isDesktop: boolean,
  batchSize: number,
): HomomorphicFeasibility {
  const enriched =
    model ??
    enrichModel({
      id: modelId,
      name: modelId,
      framework: "",
      task: "",
      accuracy: 0,
      input_shape: "",
    });

  const archetype = resolveModelArchetype(enriched);
  const compat = evaluateDatasetModelCompatibility(archetype, datasetId);
  const inferencePlan = resolveInferencePlan(
    enriched,
    modelId,
    aheCapableIds,
    isDesktop,
    datasetId,
  );
  const perfProfileKey = inferencePlan.perfProfileKey;
  const kind = compat.kind;
  const pairLabel = kind ? formatModelDatasetPair(archetype, kind) : "—";
  const expectedAccuracyPct =
    kind != null ? resolvePairAccuracyPct(archetype, kind, enriched.accuracy) : 0;
  const mockBatchDisplayPct =
    batchSize > 1 && expectedAccuracyPct > 0
      ? Math.round(expectedAccuracyPct * 0.95 * 100) / 100
      : null;

  if (!compat.ok || kind == null) {
    return {
      status: "blocked",
      canLaunch: false,
      statusLabel: "不可运行",
      statusType: "error",
      compatibilityOk: false,
      compatibilityDetail: compat.detail,
      modelArchetype: archetype,
      datasetKind: kind,
      pairLabel,
      inferencePlan,
      perfProfileKey,
      expectedAccuracyPct,
      mockBatchDisplayPct,
      checks: [
        { id: "pair", label: "模型×数据集", pass: false, detail: compat.detail },
      ],
    };
  }

  const isReal =
    archetype === "network_a" &&
    kind === "mnist" &&
    inferencePlan.mode === "rust_ahe";
  const aheReady = aheCapableIds.has(modelId);

  if (isReal) {
    const checks = [
      {
        id: "pair",
        label: "模型×数据集",
        pass: true,
        detail: pairLabel,
      },
      {
        id: "ahe",
        label: "AHE 权重",
        pass: aheReady,
        detail: aheReady ? "homomorphic 权重已注册" : "未检测到 AHE 权重",
      },
      {
        id: "runtime",
        label: "桌面客户端",
        pass: isDesktop,
        detail: isDesktop ? "Tauri" : "浏览器环境将降级为演示计时",
      },
    ];
    const canLaunch = aheReady && isDesktop;
    return {
      status: "real_ahe",
      canLaunch,
      statusLabel: canLaunch ? "可密态推理" : "条件未满足",
      statusType: canLaunch ? "success" : "warning",
      compatibilityOk: true,
      compatibilityDetail: compat.detail,
      modelArchetype: archetype,
      datasetKind: kind,
      pairLabel,
      inferencePlan,
      perfProfileKey,
      expectedAccuracyPct,
      mockBatchDisplayPct,
      checks,
    };
  }

  const checks = [
    { id: "pair", label: "模型×数据集", pass: true, detail: pairLabel },
    {
      id: "path",
      label: "推理方式",
      pass: true,
      detail: `演示计时 · ${perfProfileKey}`,
    },
    {
      id: "accuracy",
      label: "假定训练准确度",
      pass: expectedAccuracyPct > 0,
      detail: `${expectedAccuracyPct.toFixed(2)}%${
        mockBatchDisplayPct != null ? `（批量展示约 ${mockBatchDisplayPct.toFixed(2)}%）` : ""
      }`,
    },
  ];

  return {
    status: "mock",
    canLaunch: true,
    statusLabel: "可演示推理",
    statusType: "info",
    compatibilityOk: true,
    compatibilityDetail: compat.detail,
    modelArchetype: archetype,
    datasetKind: kind,
    pairLabel,
    inferencePlan,
    perfProfileKey,
    expectedAccuracyPct,
    mockBatchDisplayPct,
    checks,
  };
}

/** @deprecated 使用 resolvePairAccuracyPct */
export function resolveComboAccuracyPct(
  model: EnrichedModel,
  datasetId: string,
): number {
  const archetype = resolveModelArchetype(model);
  const kind = datasetKindFromId(datasetId);
  if (!kind) return 0;
  return resolvePairAccuracyPct(archetype, kind, model.accuracy);
}
