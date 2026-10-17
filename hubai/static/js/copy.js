// Adds a "Copy" button to every element marked data-copy (setup commands, token, join code).
document.addEventListener("DOMContentLoaded", () => {
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
