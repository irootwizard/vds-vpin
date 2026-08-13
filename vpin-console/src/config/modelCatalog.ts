import type { BackendModel } from "@/services/backendApi";
import { isStrictNetworkAModel } from "@/config/networkAProof";
export type ModelFamilyId = "network_a" | "lenet_cifar" | "resnet_cifar" | "lenet_mnist" | "unknown";

export type InferenceMode = "rust_ahe" | "timing_demo";

export type PerfProfileKey = "mnist-lenet" | "mnist-resnet" | "cifar-lenet" | "cifar-resnet";

export interface ModelFamilySpec {
  id: ModelFamilyId;
  label: string;
  networkKeys: string[];
  idPatterns: RegExp[];
  defaultDatasetId: string;
  homomorphicOpScale: number;
}

export interface EnrichedModel extends BackendModel {
  network?: string;
  deployable?: boolean;
  message?: string;
  family: ModelFamilyId;
  familyLabel: string;
  defaultDatasetId: string;
  perfProfileKey: PerfProfileKey;
  homomorphicOpScale: number;
}

export interface InferencePlan {
  mode: InferenceMode;
  requiresAheServer: boolean;
  showRustEnginePicker: boolean;
  perfProfileKey: PerfProfileKey;
  defaultDatasetId: string;
  familyLabel: string;
  preflightModelDetail: string;
  preflightSchemeDetail: string;
}

const MODEL_FAMILIES: ModelFamilySpec[] = [
  {
    id: "network_a",
    label: "Network A · MNIST",
    networkKeys: ["A", "B"],
    idPatterns: [/cnn-mnist/i],
    defaultDatasetId: "mnist-test",
    homomorphicOpScale: 1,
  },
  {
    id: "lenet_mnist",
    label: "LeNet · MNIST",
    networkKeys: [],
    idPatterns: [/^lenet-mnist$/i, /lenet.*mnist/i],
    defaultDatasetId: "mnist-test",
    homomorphicOpScale: 1,
  },
  {
    id: "lenet_cifar",
    label: "LeNet · CIFAR-10",
    networkKeys: ["lenet_cifar", "lenet-cifar"],
    idPatterns: [/lenet.*cifar/i, /^lenet-cifar10$/],
    defaultDatasetId: "cifar10-test",
    homomorphicOpScale: 1.5,
  },
  {
    id: "resnet_cifar",
    label: "ResNet · CIFAR-10",
    networkKeys: ["resnet_cifar", "resnet-cifar"],
    idPatterns: [/resnet/i],
    defaultDatasetId: "cifar10-test",
    homomorphicOpScale: 12,
  },
];

const FALLBACK_FAMILY: ModelFamilySpec = {
  id: "unknown",
  label: "通用 CNN",
  networkKeys: [],
  idPatterns: [],
  defaultDatasetId: "mnist-test",
  homomorphicOpScale: 1,
};

function isCifarDataset(datasetId?: string): boolean {
  if (!datasetId) return false;
  const d = datasetId.toLowerCase();
  return d.includes("cifar");
}

function isResnetArchetype(modelId: string, family: ModelFamilyId): boolean {
  return family === "resnet_cifar" || /resnet/i.test(modelId);
}

/** 模型 × 数据集 → timing-demo 参数键 */
export function resolvePerfProfileKey(
  modelId: string,
  datasetId?: string,
  family?: ModelFamilyId,
): PerfProfileKey {
  const fam = family ?? resolveModelFamily({ id: modelId, input_shape: "" }).id;
  const cifar =
    isCifarDataset(datasetId) || fam === "lenet_cifar" || fam === "resnet_cifar";
  const resnet = isResnetArchetype(modelId, fam);
  if (cifar) return resnet ? "cifar-resnet" : "cifar-lenet";
  return resnet ? "mnist-resnet" : "mnist-lenet";
}

export function resolveModelFamily(
  model: Pick<BackendModel, "id" | "input_shape"> & { network?: string },
): ModelFamilySpec {
  for (const spec of MODEL_FAMILIES) {
    if (spec.idPatterns.some((re) => re.test(model.id))) {
      return spec;
    }
  }
  const network = (model.network ?? "").toLowerCase();
  for (const spec of MODEL_FAMILIES) {
    if (spec.networkKeys.some((k) => k.toLowerCase() === network)) {
      return spec;
    }
  }
  if (/mnist/i.test(model.id) || (model.input_shape ?? "").includes("28x28")) {
    if (/resnet/i.test(model.id)) {
      return MODEL_FAMILIES.find((s) => s.id === "resnet_cifar") ?? FALLBACK_FAMILY;
    }
    if (/lenet/i.test(model.id) && !/cifar/i.test(model.id)) {
      return MODEL_FAMILIES.find((s) => s.id === "lenet_mnist") ?? FALLBACK_FAMILY;
    }
    return MODEL_FAMILIES.find((s) => s.id === "network_a") ?? FALLBACK_FAMILY;
  }
  if (/resnet/i.test(model.id)) {
    return MODEL_FAMILIES.find((s) => s.id === "resnet_cifar") ?? FALLBACK_FAMILY;
  }
  if (/cifar/i.test(model.id) || (model.input_shape ?? "").includes("32x32")) {
    return MODEL_FAMILIES.find((s) => s.id === "lenet_cifar") ?? FALLBACK_FAMILY;
  }
  return FALLBACK_FAMILY;
}

export function enrichModel(raw: BackendModel): EnrichedModel {
  const family = resolveModelFamily(raw);
  const perfProfileKey = resolvePerfProfileKey(raw.id, family.defaultDatasetId, family.id);
  return {
    ...raw,
    family: family.id,
    familyLabel: family.label,
    defaultDatasetId: family.defaultDatasetId,
    perfProfileKey,
    homomorphicOpScale: family.homomorphicOpScale,
  };
}

/**
 * 推理路径：仅严格 Network A（cnn-mnist*）在 Tauri 且 AHE 就绪时走真 Rust；
 * 其余模型（含 LeNet/ResNet + 任意数据集）一律 timing-demo mock。
 */
export function resolveInferencePlan(
  model: EnrichedModel | null,
  modelId: string,
  aheCapableIds: Set<string>,
  isDesktop: boolean,
  datasetId?: string,
): InferencePlan {
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
  const family = MODEL_FAMILIES.find((f) => f.id === enriched.family) ?? FALLBACK_FAMILY;
  const perfProfileKey = resolvePerfProfileKey(modelId, datasetId ?? enriched.defaultDatasetId, family.id);
  const useRust =
    isDesktop && isStrictNetworkAModel(modelId) && aheCapableIds.has(modelId);

  return {
    mode: useRust ? "rust_ahe" : "timing_demo",
    requiresAheServer: useRust,
    showRustEnginePicker: useRust,
    perfProfileKey,
    defaultDatasetId: family.defaultDatasetId,
    familyLabel: family.label,
    preflightModelDetail: useRust
      ? `${family.label} · AHE 权重已注册`
      : `${family.label} · 演示计时（timing-demo）`,
    preflightSchemeDetail: useRust
      ? "Tauri → ahe-cli → Rust ahe-server"
      : `timing-demo · ${perfProfileKey} · jitter 95–105%`,
  };
}

export function modelSelectLabel(m: EnrichedModel): string {
  return m.name;
}
