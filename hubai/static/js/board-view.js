// Per-column views (full / compact / titles only) and minimised columns, remembered per browser.
// Classes are reapplied right after every HTMX swap of #live (before the browser paints), since the swap
// brings the server's plain markup back.
// The "all columns" buttons above the board set every column at once.
// Also closes the task modal (#modal lives outside #live, so it survives the refresh).
document.addEventListener("DOMContentLoaded", () => {
  const KEY = "hubai-board-columns";
  const live = document.getElementById("live");
  const read = (k) => { try { return localStorage.getItem(k); } catch (err) { return null; } };
  let state = {};
  try { state = JSON.parse(read(KEY)) || {}; } catch (err) { state = {}; }
  const fallback = read("hubai-board-view") || "normal";  // the old single setting, before per-column views
  const col = (status) => (state[status] = state[status] || { view: fallback, collapsed: false });
  const save = () => {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (err) { console.warn("Can't save board view", err); }
  };

  const apply = () => {
    live.querySelectorAll("[data-column]").forEach((column) => {
      const c = col(column.dataset.column);
      column.classList.toggle("is-collapsed", c.collapsed);
      const cards = column.querySelector(".board-column");
      cards.className = `board-column view-${c.view}`;
      column.querySelectorAll("[data-col-view]").forEach((b) => {
        const on = b.dataset.colView === c.view;
        b.classList.toggle("is-link", on);
        b.classList.toggle("is-white", !on);
      });
    });
  };
  apply();
  // htmx fires afterSwap on the element that made the request (the poll is #live itself, but a drag, a
  // status select, the add-task form or the modal are not), so look at where the response was swapped.
  document.body.addEventListener("htmx:afterSwap", (e) => {
    const target = (e.detail && e.detail.target) || e.target;
    if (target === live || live.contains(target)) apply();
  });

  live.addEventListener("click", (e) => {
    const column = e.target.closest("[data-column]");
    if (!column) return;
    const status = column.dataset.column;
    const viewButton = e.target.closest("[data-col-view]");
    if (viewButton) col(status).view = viewButton.dataset.colView;
    else if (e.target.closest("[data-col-collapse]")) col(status).collapsed = true;
    else if (column.classList.contains("is-collapsed") && e.target.closest(".column-head")) col(status).collapsed = false;
    else return;
    save();
    apply();
  });

  document.querySelectorAll("[data-board-view]").forEach((b) => b.addEventListener("click", () => {
    live.querySelectorAll("[data-column]").forEach((column) => {
      const c = col(column.dataset.column);
      c.view = b.dataset.boardView;
      c.collapsed = false;
    });
    save();
    apply();
  }));

  const modal = document.getElementById("modal");
  document.addEventListener("click", (e) => { if (e.target.closest("[data-close-modal]")) modal.innerHTML = ""; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") modal.innerHTML = ""; });
});
