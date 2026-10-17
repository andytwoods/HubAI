// Drag a task card to reorder it, or drop it in another column to change its status.
// Native HTML5 drag and drop; listeners are delegated from #live because HTMX replaces its contents every 3s.
// While a drag is in progress <body> carries .is-dragging, which pauses that refresh (see detail.html).
document.addEventListener("DOMContentLoaded", () => {
  const live = document.getElementById("live");
  const url = document.getElementById("board-view").dataset.reorderUrl;
  let dragged = null;

  live.addEventListener("dragstart", (e) => {
    dragged = e.target.closest(".task-card");
    if (!dragged) return;
    document.body.classList.add("is-dragging");
    dragged.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged.dataset.taskId);
  });

  live.addEventListener("dragover", (e) => {
    const column = e.target.closest(".board-column");
    if (!dragged || !column) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    live.querySelectorAll(".board-column.is-drop-target").forEach((c) => c.classList.remove("is-drop-target"));
    column.classList.add("is-drop-target");
    // Insert before the first card whose vertical midpoint is below the pointer, else at the end.
    const cards = [...column.querySelectorAll(".task-card:not(.is-dragging)")];
    const next = cards.find((c) => e.clientY < c.getBoundingClientRect().top + c.offsetHeight / 2);
    if (next) column.insertBefore(dragged, next);
    else column.appendChild(dragged);
  });

  live.addEventListener("drop", (e) => {
    const column = e.target.closest(".board-column");
    if (!dragged || !column) return;
    e.preventDefault();
    const ids = [...column.querySelectorAll(".task-card")].map((c) => c.dataset.taskId).join(",");
    htmx.ajax("POST", url, { target: "#live", swap: "morph:innerHTML", values: { status: column.dataset.status, ids } });
  });

  live.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("is-dragging");
    dragged = null;
    document.body.classList.remove("is-dragging");
    live.querySelectorAll(".is-drop-target").forEach((c) => c.classList.remove("is-drop-target"));
  });
});
