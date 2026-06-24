(function () {
  const isEmbed = new URLSearchParams(window.location.search).get("embed") === "1";

  if (isEmbed) {
    document.documentElement.classList.add("embed-mode");
  }

  function loadIncludes() {
    document.querySelectorAll("[data-include]").forEach(function (element) {
      const file = element.getAttribute("data-include");
      if (!file) return;

      if (isEmbed && (file.includes("header.html") || file.includes("sidebar.html"))) {
        element.remove();
        return;
      }

      fetch(file)
        .then(function (response) {
          return response.text();
        })
        .then(function (data) {
          element.innerHTML = data;
          highlightActiveNav();
        })
        .catch(function () {
          if (!isEmbed) {
            element.innerHTML = "<!-- include failed: " + file + " -->";
          }
        });
    });
  }

  function highlightActiveNav() {
    const page = window.location.pathname.split("/").pop() || "index.html";
    const navMap = {
      "index.html": "nav-dashboard",
      "model-center.html": "nav-model",
      "data-config.html": "nav-task",
      "task-dashboard.html": "nav-task",
      "security-center.html": "nav-security",
      "verification-report.html": "nav-security",
      "privacy-budget.html": "nav-security",
    };
    const activeId = navMap[page];
    if (!activeId) return;
    const item = document.getElementById(activeId);
    if (item) item.classList.add("active");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadIncludes);
  } else {
    loadIncludes();
  }
})();
