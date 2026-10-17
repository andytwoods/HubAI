// Normal / Compact / Titles-only task views. Pure CSS switch, so it survives the 3s HTMX refresh.
// The choice is remembered per browser; storage may be unavailable, so every access is guarded.
document.addEventListener("DOMContentLoaded", () => {
  const board = document.getElementById("board-view");
  const buttons = document.querySelectorAll("[data-board-view]");
  const apply = (view) => {
    board.className = `view-${view}`;
    buttons.forEach((b) => b.classList.toggle("is-link", b.dataset.boardView === view));
  };
  let saved = "normal";
  try {
    saved = localStorage.getItem("hubai-board-view") || "normal";
  } catch (err) {
    console.warn("Can't read saved board view", err);
  }
  apply(saved);
  buttons.forEach((b) => b.addEventListener("click", () => {
    apply(b.dataset.boardView);
    try {
      localStorage.setItem("hubai-board-view", b.dataset.boardView);
    } catch (err) {
      console.warn("Can't save board view", err);
    }
  }));
});
