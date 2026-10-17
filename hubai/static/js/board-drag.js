// Drag a task card to reorder it, or drop it in another column to change its status.
// Native HTML5 drag and drop; listeners are delegated from #live because HTMX replaces its contents every 3s.
// While a drag is in progress <body> carries .is-dragging, which pauses that refresh (see detail.html).
document.addEventListener("DOMContentLoaded", () => {
  const live = document.getElementById("live");
  const url = document.getElementById("board-view").dataset.reorderUrl;
  let dragged = null;
  let from = null;
  // People reorder To do and can park a card in Blocked; moving it to Doing or Done is for the agent that claims it
  // (the status dropdown still allows a deliberate override).
  const allowed = (to) => from !== "todo" || to === "todo" || to === "blocked";

  live.addEventListener("dragstart", (e) => {
    dragged = e.target.closest(".task-card");
    if (!dragged) return;
    from = dragged.closest(".board-column").dataset.status;
    document.body.classList.add("is-dragging");
    dragged.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged.dataset.taskId);
  });

  live.addEventListener("dragover", (e) => {
    const column = e.target.closest(".board-column");
    if (!dragged || !column) return;
    live.querySelectorAll(".is-drop-target, .is-no-drop").forEach((c) => c.classList.remove("is-drop-target", "is-no-drop"));
    if (!allowed(column.dataset.status)) {
      column.classList.add("is-no-drop");
      return;  // no preventDefault: the browser shows "not allowed" and refuses the drop
    }
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    column.classList.add("is-drop-target");
    // Insert before the first card whose vertical midpoint is below the pointer, else at the end.
    const cards = [...column.querySelectorAll(".task-card:not(.is-dragging)")];
    const next = cards.find((c) => e.clientY < c.getBoundingClientRect().top + c.offsetHeight / 2);
    if (next) column.insertBefore(dragged, next);
    else column.appendChild(dragged);
  });

  live.addEventListener("drop", (e) => {
    const column = e.target.closest(".board-column");
    if (!dragged || !column || !allowed(column.dataset.status)) return;
    e.preventDefault();
    const ids = [...column.querySelectorAll(".task-card")].map((c) => c.dataset.taskId).join(",");
    htmx.ajax("POST", url, { target: "#live", swap: "morph:innerHTML", values: { status: column.dataset.status, ids } });
  });

  live.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("is-dragging");
    dragged = null;
    document.body.classList.remove("is-dragging");
    live.querySelectorAll(".is-drop-target, .is-no-drop").forEach((c) => c.classList.remove("is-drop-target", "is-no-drop"));
  });
});
