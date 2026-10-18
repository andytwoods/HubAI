// Adds a "Copy" button to every element marked data-copy (setup commands, token, join code).
// Elements marked data-secret stay blurred until clicked (or focused and Enter pressed); Copy works either way.
document.addEventListener("DOMContentLoaded", () => {
  const reveal = (el) => {
    el.classList.toggle("is-revealed");
    el.title = el.classList.contains("is-revealed") ? "Click to hide" : "Click to reveal";
  };
  document.querySelectorAll("[data-secret]").forEach((el) => {
    el.addEventListener("click", () => reveal(el));
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); reveal(el); } });
  });
  document.querySelectorAll("[data-copy]").forEach((el) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button is-small is-light copy-button";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy to clipboard");
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(el.textContent.trim());
        button.textContent = "Copied ✓";
      } catch (err) {
        console.error("Copy failed", err);
        button.textContent = "Copy failed";
      }
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    });
    el.insertAdjacentElement("afterend", button);
  });
});
