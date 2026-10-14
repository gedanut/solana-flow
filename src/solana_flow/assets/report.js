"use strict";
(() => {
  const search = document.getElementById("search");
  const asset = document.getElementById("asset");
  const direction = document.getElementById("direction");
  const status = document.getElementById("status");
  const rows = Array.from(document.querySelectorAll("tbody tr"));
  const update = () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const match = (!query || row.textContent.toLowerCase().includes(query)) &&
        (!asset.value || row.dataset.asset === asset.value) &&
        (!direction.value || row.dataset.direction === direction.value) &&
        (!status.value || row.dataset.status === status.value);
      row.hidden = !match;
      if (match) visible++;
    }
    document.getElementById("row-count").textContent = `${visible} of ${rows.length} ledger rows`;
    document.getElementById("empty").hidden = visible !== 0;
  };
  for (const control of [search, asset, direction, status]) {
    control.addEventListener("input", update);
    control.addEventListener("change", update);
  }
  update();
})();
