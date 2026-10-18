// Adds a copy icon to every element marked data-copy (setup commands, token, join code).
// Command blocks (<pre>) get it in their top-right corner; inline values get it right after them on the same line.
// Elements marked data-secret stay blurred until clicked (or focused and Enter pressed); copying works either way.
const COPY_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
const DONE_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

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
    button.className = "copy-button";
    button.innerHTML = COPY_ICON;
    button.title = "Copy";
    button.setAttribute("aria-label", "Copy to clipboard");
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(el.textContent.trim());
        button.innerHTML = DONE_ICON;
        button.title = "Copied";
        button.classList.add("is-done");
      } catch (err) {
        console.error("Copy failed", err);
        button.title = "Copy failed";
      }
      setTimeout(() => {
        button.innerHTML = COPY_ICON;
        button.title = "Copy";
        button.classList.remove("is-done");
      }, 1500);
    });
    if (el.tagName === "PRE") {
      const wrap = document.createElement("div");
      wrap.className = "copy-wrap";
      el.replaceWith(wrap);
      wrap.append(el, button);
    } else {
      el.insertAdjacentElement("afterend", button);
    }
  });
});
