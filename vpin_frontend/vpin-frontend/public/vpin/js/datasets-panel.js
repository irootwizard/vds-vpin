/**
 * Dataset catalog panel for data-config.html
 * - Local: from GET /api/v1/datasets/catalog (local[]) with offline fallback
 * - Remote: from GET /api/v1/datasets/remote or catalog.remote[]
 * - Image kinds: thumbnail grid + lightbox preview (SVG placeholders, no server pixels)
 */
(function () {
  const API_BASE = (function () {
    const embed = new URLSearchParams(window.location.search).get("api_base");
    if (embed) return embed;
    if (window.parent && window.parent !== window) {
      try {
        const p = window.parent.location.pathname;
        if (p && !p.includes("/vpin/pages/")) return "/api/v1";
      } catch (_) {
        /* cross-origin */
      }
    }
    return "/api/v1";
  })();

  const OFFLINE_CATALOG = {
    local: [
      {
        id: "mnist-test",
        name: "MNIST 官方测试集",
        kind: "image",
        location: "local",
        format: "idx_uint8_28x28",
        sample_count: 10000,
        index_range: [0, 9999],
        previewable: true,
        preview_samples: [
          { index: 0, thumbnail_key: "mnist-0" },
          { index: 1, thumbnail_key: "mnist-1" },
          { index: 2, thumbnail_key: "mnist-2" },
        ],
        message: "离线模式 · 明文在本机加载",
      },
    ],
    remote: [],
  };

  function mnistThumbSvg(digit, index) {
    const label = digit != null ? String(digit) : "#" + index;
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56">' +
      '<rect width="56" height="56" fill="#f5f5f5" rx="4"/>' +
      '<rect x="8" y="8" width="40" height="40" fill="#e8e8e8" rx="2"/>' +
      '<text x="28" y="34" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" fill="#595959">' +
      label +
      "</text></svg>";
    return "data:image/svg+xml," + encodeURIComponent(svg);
  }

  function thumbnailForSample(sample) {
    const key = sample.thumbnail_key || "";
    const digitMatch = /^mnist-(\d)$/.exec(key);
    const digit = digitMatch ? Number(digitMatch[1]) : sample.label;
    return mnistThumbSvg(digit, sample.index);
  }

  function kindLabel(kind) {
    if (kind === "image") return "图像";
    if (kind === "tabular") return "表格";
    return kind || "—";
  }

  function formatCount(n) {
    if (n == null) return "动态";
    return Number(n).toLocaleString() + " 条";
  }

  function el(tag, className, html) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function renderDatasetCard(ds, location) {
    const card = el("div", "dataset-card" + (ds.previewable ? " previewable" : ""));
    card.dataset.id = ds.id;
    card.dataset.location = location;

    const badges =
      '<span class="dataset-badge">' +
      kindLabel(ds.kind) +
      "</span>" +
      (ds.status === "placeholder"
        ? '<span class="dataset-badge badge-muted">占位</span>'
        : "") +
      (ds.dynamic ? '<span class="dataset-badge badge-info">动态</span>' : "");

    card.innerHTML =
      '<div class="dataset-card__head">' +
      "<h4>" +
      ds.name +
      "</h4>" +
      '<div class="dataset-badges">' +
      badges +
      "</div></div>" +
      '<p class="dataset-card__meta">' +
      (ds.format ? "格式：" + ds.format + " · " : "") +
      "样本：" +
      formatCount(ds.sample_count) +
      "</p>" +
      (ds.message ? '<p class="dataset-card__hint">' + ds.message + "</p>" : "");

    if (ds.kind === "image" && ds.previewable && ds.preview_samples && ds.preview_samples.length) {
      const grid = el("div", "dataset-preview-grid");
      ds.preview_samples.forEach(function (sample) {
        const btn = el("button", "dataset-thumb", "");
        btn.type = "button";
        btn.title = "索引 " + sample.index + (sample.label != null ? " · 标签 " + sample.label : "");
        const img = document.createElement("img");
        img.src = thumbnailForSample(sample);
        img.alt = "preview " + sample.index;
        btn.appendChild(img);
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          openPreview(ds, sample);
        });
        grid.appendChild(btn);
      });
      card.appendChild(grid);
    } else if (ds.kind === "image" && ds.previewable && ds.dynamic) {
      card.appendChild(
        el("p", "dataset-card__hint", "上传图像后可在「图像精度预处理」中预览"),
      );
    }

    card.addEventListener("click", function () {
      selectDataset(ds, location);
    });

    return card;
  }

  function selectDataset(ds, location) {
    document.querySelectorAll(".dataset-card.selected").forEach(function (c) {
      c.classList.remove("selected");
    });
    const card = document.querySelector(
      '.dataset-card[data-id="' + ds.id + '"][data-location="' + location + '"]',
    );
    if (card) card.classList.add("selected");

    const status = document.getElementById("datasetSelectStatus");
    if (status) {
      status.textContent =
        "已选择「" +
        ds.name +
        "」（" +
        (location === "local" ? "本地" : "远程") +
        "）";
    }

    try {
      localStorage.setItem(
        "vpinSelectedDataset",
        JSON.stringify({ id: ds.id, location: location, name: ds.name, kind: ds.kind }),
      );
    } catch (_) {
      /* ignore */
    }
  }

  function openPreview(ds, sample) {
    const modal = document.getElementById("datasetPreviewModal");
    const img = document.getElementById("datasetPreviewImage");
    const caption = document.getElementById("datasetPreviewCaption");
    if (!modal || !img || !caption) return;

    img.src = thumbnailForSample(sample);
    caption.textContent =
      ds.name +
      " · 索引 " +
      sample.index +
      (sample.label != null ? " · 标签 " + sample.label : "") +
      "（示意缩略图，非服务端明文）";
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  function closePreview() {
    const modal = document.getElementById("datasetPreviewModal");
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  function renderList(container, items, location) {
    container.innerHTML = "";
    if (!items || !items.length) {
      container.appendChild(el("p", "dataset-empty", "暂无数据集"));
      return;
    }
    items.forEach(function (ds) {
      container.appendChild(renderDatasetCard(ds, location));
    });
  }

  function switchTab(tab) {
    document.querySelectorAll(".dataset-tab").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    document.getElementById("datasetPanelLocal").hidden = tab !== "local";
    document.getElementById("datasetPanelRemote").hidden = tab !== "remote";
  }

  async function fetchCatalog() {
    try {
      const res = await fetch(API_BASE + "/datasets/catalog");
      if (!res.ok) throw new Error(res.status);
      return await res.json();
    } catch (_) {
      return OFFLINE_CATALOG;
    }
  }

  async function init() {
    const localList = document.getElementById("datasetListLocal");
    const remoteList = document.getElementById("datasetListRemote");
    const loadHint = document.getElementById("datasetLoadHint");
    if (!localList || !remoteList) return;

    if (loadHint) loadHint.textContent = "正在加载数据集目录…";

    const catalog = await fetchCatalog();
    renderList(localList, catalog.local || OFFLINE_CATALOG.local, "local");
    renderList(remoteList, catalog.remote || [], "remote");

    if (loadHint) {
      loadHint.textContent =
        catalog.remote && catalog.remote.length
          ? "远程目录来自 API · 图像预览为本地示意缩略图"
          : "远程目录不可用，仅展示本地数据集（离线）";
    }

    document.querySelectorAll(".dataset-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        switchTab(btn.dataset.tab);
      });
    });

    const closeBtn = document.getElementById("datasetPreviewClose");
    const modal = document.getElementById("datasetPreviewModal");
    if (closeBtn) closeBtn.addEventListener("click", closePreview);
    if (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) closePreview();
      });
    }

    try {
      const raw = localStorage.getItem("vpinSelectedDataset");
      if (raw) {
        const sel = JSON.parse(raw);
        const card = document.querySelector(
          '.dataset-card[data-id="' + sel.id + '"][data-location="' + sel.location + '"]',
        );
        if (card) card.classList.add("selected");
        const status = document.getElementById("datasetSelectStatus");
        if (status) status.textContent = "已选择「" + sel.name + "」";
      }
    } catch (_) {
      /* ignore */
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
