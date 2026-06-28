import { computed, reactive, ref } from "vue";
import { getPreprocessLane } from "../services/aheClient.js";

/** @typedef {'python'|'rust'} PreprocessLane */

/**
 * Per-lane preprocess galleries — switching stack shows the matching lane only.
 */
export function useAhePreprocessLanes(inferEngineRef) {
  const index = ref(0);

  /** @type {Record<PreprocessLane, { gallery: object[], selectedSample: object|null, lastUploadPath: string|null }>} */
  const lanes = reactive({
    python: { gallery: [], selectedSample: null, lastUploadPath: null },
    rust: { gallery: [], selectedSample: null, lastUploadPath: null },
  });

  const activeLane = computed(() => getPreprocessLane(inferEngineRef.value));

  const selectedSample = computed(() => lanes[activeLane.value].selectedSample);

  function sampleKey(item) {
    return item.upload_id || `mnist-${item.mnist_index}`;
  }

  function isSelected(lane, item) {
    const sel = lanes[lane].selectedSample;
    if (!sel) return false;
    if (item.upload_id && sel.upload_id) return item.upload_id === sel.upload_id;
    return item.mnist_index === sel.mnist_index;
  }

  function formatMeta(item) {
    if (item.source === "upload") {
      return item.filename || item.upload_id?.slice(0, 8) || "upload";
    }
    return `#${item.mnist_index} · ${item.label}`;
  }

  function upsertGalleryItem(lane, item) {
    const list = lanes[lane].gallery;
    const existing = list.findIndex((g) => sampleKey(g) === sampleKey(item));
    if (existing >= 0) {
      list[existing] = item;
    } else {
      list.unshift(item);
    }
  }

  function applySelection(lane, prep) {
    lanes[lane].selectedSample = prep;
    if (prep.mnist_index != null) {
      index.value = prep.mnist_index;
    }
    return prep;
  }

  function selectSample(lane, item) {
    applySelection(lane, item);
  }

  function setGallery(lane, items) {
    lanes[lane].gallery = items;
  }

  function pickDefaultSelection(lane, preferredIndex) {
    const list = lanes[lane].gallery;
    if (!list.length) {
      lanes[lane].selectedSample = null;
      return;
    }
    const current = list.find((item) => item.mnist_index === preferredIndex);
    applySelection(lane, current || list[0]);
  }

  /** @type {Record<PreprocessLane, string[]>} */
  const multiSelectedKeys = reactive({
    python: [],
    rust: [],
  });

  /** @type {Record<PreprocessLane, string|null>} */
  const multiAnchorKey = reactive({
    python: null,
    rust: null,
  });

  function isMultiSelected(lane, item) {
    return multiSelectedKeys[lane].includes(sampleKey(item));
  }

  function clearMultiSelect(lane) {
    multiSelectedKeys[lane] = [];
    multiAnchorKey[lane] = null;
  }

  function getMultiSelectedSamples(lane) {
    const keys = new Set(multiSelectedKeys[lane]);
    return lanes[lane].gallery.filter((item) => keys.has(sampleKey(item)));
  }

  function toggleMultiSelect(lane, item, { additive = false, range = false } = {}) {
    const key = sampleKey(item);
    const list = lanes[lane].gallery;
    const keys = multiSelectedKeys[lane];

    if (range && multiAnchorKey[lane]) {
      const anchorIdx = list.findIndex((g) => sampleKey(g) === multiAnchorKey[lane]);
      const clickIdx = list.findIndex((g) => sampleKey(g) === key);
      if (anchorIdx >= 0 && clickIdx >= 0) {
        const [lo, hi] = anchorIdx < clickIdx ? [anchorIdx, clickIdx] : [clickIdx, anchorIdx];
        const rangeKeys = list.slice(lo, hi + 1).map(sampleKey);
        multiSelectedKeys[lane] = [...new Set([...keys, ...rangeKeys])];
      }
    } else if (additive) {
      if (keys.includes(key)) {
        multiSelectedKeys[lane] = keys.filter((k) => k !== key);
      } else {
        multiSelectedKeys[lane] = [...keys, key];
      }
      multiAnchorKey[lane] = key;
    } else {
      multiSelectedKeys[lane] = [key];
      multiAnchorKey[lane] = key;
    }
    applySelection(lane, item);
  }

  return {
    lanes,
    index,
    activeLane,
    selectedSample,
    sampleKey,
    isSelected,
    isMultiSelected,
    clearMultiSelect,
    getMultiSelectedSamples,
    toggleMultiSelect,
    multiSelectedKeys,
    formatMeta,
    upsertGalleryItem,
    applySelection,
    selectSample,
    setGallery,
    pickDefaultSelection,
  };
}
