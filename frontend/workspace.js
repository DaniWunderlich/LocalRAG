() => {
  window.__localRagWorkspace?.();
  const root = document.documentElement;
  let frame = 0;
  let active = null;
  let count = 0;
  let nearEnd = true;
  let sidebarLayout = null;
  let dialog = null;
  let previousFocus = null;
  let inertBackground = [];
  let observedComposer = null;
  const composerResize = new ResizeObserver(() => schedule());
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let mode = "system";
  let language = "en";
  const labels = {
    en: {Light:"Light", Dark:"Dark", System:"System", jump:"Jump to latest message"},
    de: {Light:"Hell", Dark:"Dunkel", System:"System", jump:"Zur neuesten Nachricht springen"}
  };
  try { mode = localStorage.getItem("localrag-appearance") || "system"; } catch { /* Storage may be unavailable. */ }
  if (!["light", "dark", "system"].includes(mode)) mode = "system";

  function appearance() {
    const dark = mode === "dark" || (mode === "system" && media.matches);
    root.classList.toggle("dark", dark);
    document.body.classList.toggle("dark", dark);

  }
  window.__localRagSetAppearance = value => {
    mode = String(value).toLowerCase();
    if (!["light", "dark", "system"].includes(mode)) mode = "system";
    try { localStorage.setItem("localrag-appearance", mode); } catch { /* Keep the session preference. */ }
    appearance();
  };
  function scrollRoot() {
    const chat = document.getElementById("transcript");
    if (!chat) return null;
    const nodes = [chat, ...chat.querySelectorAll("div")];
    return nodes.find(node => /auto|scroll/.test(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight + 4) || chat;
  }
  function restoreBackground() {
    inertBackground.forEach(element => { element.inert = false; });
    inertBackground = [];
  }
  function isolateDialog(panel) {
    restoreBackground();
    // Preserve the active branch; make every surrounding control truly modal.
    for (let branch = panel; branch.parentElement && branch !== document.body; branch = branch.parentElement) {
      for (const sibling of branch.parentElement.children) {
        if (sibling !== branch && sibling instanceof HTMLElement && !sibling.inert) {
          sibling.inert = true;
          inertBackground.push(sibling);
        }
      }
    }
  }
  function alignComposer() {
    const shell = document.getElementById("composer-shell");
    const tools = document.getElementById("composer-actions");
    const submit = shell?.querySelector('#composer [data-testid="submit-button"]');
    if (shell !== observedComposer) {
      composerResize.disconnect();
      observedComposer = shell;
      if (shell) composerResize.observe(shell);
    }
    if (!shell || !tools || !submit || !submit.getClientRects().length) return;
    const top = submit.getBoundingClientRect().top - shell.getBoundingClientRect().top - shell.clientTop;
    if (Math.abs(tools.offsetTop - top) > 0.1 || tools.style.bottom !== "auto") {
      tools.style.top = `${top}px`;
      tools.style.bottom = "auto";
    }
  }
  function sync() {
    frame = 0;
    alignComposer();
    const marker = document.querySelector("#active-chat-marker [data-active-chat]");
    const next = marker?.dataset.activeChat || "";
    const changedChat = next !== active;
    const rail = document.getElementById("conversation-rail");
    const compact = window.innerWidth <= 900;
    if (rail && sidebarLayout !== compact) {
      sidebarLayout = compact;
      if (rail.classList.contains("open") === compact) rail.querySelector(".toggle-button")?.click();
    } else if (rail && compact && changedChat && rail.classList.contains("open")) {
      rail.querySelector(".toggle-button")?.click();
    }
    const messages = Number(marker?.dataset.messageCount || 0);
    const scrolling = scrollRoot();
    const button = document.getElementById("jump-to-latest");
    if (scrolling && button) {
      if (next !== active || (messages > count && nearEnd)) scrolling.scrollTop = scrolling.scrollHeight;
      active = next;
      count = messages;
      nearEnd = scrolling.scrollHeight - scrolling.clientHeight - scrolling.scrollTop < 80;
      button.hidden = !messages || nearEnd;
    }
    language = marker?.dataset.language || "en";
    root.lang = language;
    document.querySelectorAll('#appearance input, #language input').forEach(input => {
      const name = input.closest('#appearance') ? labels[language][input.value] : (input.value === 'de' ? 'Deutsch' : 'English');
      if (name) {
        input.setAttribute('aria-label', name);
        input.closest('label').title = name;
      }
    });
    const jump = document.getElementById('jump-to-latest');
    if (jump) { jump.title = labels[language].jump; jump.setAttribute('aria-label', labels[language].jump); }
    const panel = [document.getElementById("chat-manager"), document.getElementById("chat-settings")].find(panel => panel?.getClientRects().length > 0);
    const opened = panel && panel.getClientRects().length > 0;
    if (opened && dialog !== panel) {
      previousFocus = document.activeElement;
      dialog = panel;
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "true");
      panel.setAttribute("aria-labelledby", panel.id === 'chat-manager' ? "chat-manager-title" : "chat-settings-title");
      isolateDialog(panel);
      panel.tabIndex = -1;
      panel.focus();
    } else if (!opened && dialog) {
      restoreBackground();
      dialog = null;
      previousFocus?.focus();
    }
    document.querySelectorAll("#composer-actions button").forEach(button => {
      button.setAttribute("aria-label", button.textContent.trim());
      button.title = button.textContent.trim();
    });
    appearance();
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(sync); }
  function click(event) {
    if (!event.target.closest('.chat-menu')) document.querySelectorAll('.chat-menu[open]').forEach(menu => menu.removeAttribute('open'));
    if (event.target.closest("#jump-to-latest")) {
      const scrolling = scrollRoot();
      scrolling?.scrollTo({top:scrolling.scrollHeight, behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
    }
  }
  function keys(event) {
    if (!dialog) return;
    if (event.key === "Escape" && dialog.querySelector('[role="listbox"]')) return;
    if (event.key === "Escape") dialog.querySelector('#close-chat-settings, #close-chat-manager')?.click();
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll("input,select,textarea,button,[tabindex='0']")].filter(node => !node.disabled && node.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { event.preventDefault(); first?.focus(); }
  }
  const observer = new MutationObserver(() => {
    const marker = document.querySelector("#active-chat-marker [data-active-chat]");
    if (marker?.dataset.ready === "true") {
      const url = new URL(window.location.href);
      if (marker.dataset.activeChat) url.searchParams.set("chat", marker.dataset.activeChat);
      else url.searchParams.delete("chat");
      if (url.href !== window.location.href) history.replaceState(null, "", url);
    }
    schedule();
  });
  observer.observe(document.body, {childList:true, subtree:true, characterData:true});
  document.addEventListener("scroll", schedule, {capture:true, passive:true});
  document.addEventListener("click", click);
  document.addEventListener("keydown", keys);
  window.addEventListener("resize", schedule);
  media.addEventListener("change", appearance);
  appearance();
  schedule();
  window.__localRagWorkspace = () => {
    observer.disconnect();
    composerResize.disconnect();
    restoreBackground();
    if (frame) cancelAnimationFrame(frame);
    document.removeEventListener("scroll", schedule, true);
    document.removeEventListener("click", click);
    document.removeEventListener("keydown", keys);
    window.removeEventListener("resize", schedule);
    media.removeEventListener("change", appearance);
  };
}
