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
  let keepComposerFocus = false;
  const composerResize = new ResizeObserver(() => schedule());
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let mode = "system";
  let language = "en";
  const labels = {
    en: {Light:"Light", Dark:"Dark", System:"System", jump:"Jump to latest message", send:"Send message (Enter)", keys:"Enter to send. Shift+Enter for a new line."},
    de: {Light:"Hell", Dark:"Dunkel", System:"System", jump:"Zur neuesten Nachricht springen", send:"Nachricht senden (Enter)", keys:"Enter zum Senden. Shift+Enter für einen Zeilenumbruch."}
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
  function syncSubmission(marker) {
    const textarea = document.querySelector('#composer textarea');
    if (!textarea) return;
    const busy = !!document.querySelector('#submission-status [data-submitting="true"]');
    const locked = busy || marker?.dataset.pendingSubmission === 'true';
    if (textarea.readOnly !== locked) textarea.readOnly = locked;
    document.getElementById('composer')?.setAttribute('aria-busy', String(busy));
    document.getElementById('transcript')?.setAttribute('aria-busy', String(busy));
    const send = document.querySelector('#composer [data-testid="submit-button"]');
    const upload = document.querySelector('#composer [data-testid="upload-button"]');
    for (const control of [send, upload]) control?.setAttribute('aria-disabled', String(locked));
    document.querySelectorAll('#composer input[type="file"]').forEach(input => {
      const disabled = locked || textarea.disabled;
      if (input.disabled !== disabled) input.disabled = disabled;
    });
    const focus = document.activeElement;
    if (keepComposerFocus && !dialog && !textarea.disabled && !textarea.closest('[inert]')
        && (focus === document.body || focus === textarea || focus === send || focus?.id === 'retry-submission')) {
      textarea.focus({preventScroll:true});
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
    const textarea = document.querySelector('#composer textarea');
    if (textarea) textarea.setAttribute('aria-description', labels[language].keys);
    const send = document.querySelector('#composer [data-testid="submit-button"]');
    if (send) { send.title = labels[language].send; send.setAttribute('aria-label', labels[language].send); }
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
    syncSubmission(marker);
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
  function submissionClick(event) {
    const textarea = document.querySelector('#composer textarea');
    const send = event.target.closest?.('#composer [data-testid="submit-button"]');
    const retry = event.target.closest?.('#retry-submission');
    const upload = event.target.closest?.('#composer [data-testid="upload-button"]');
    if ((send || upload) && textarea?.readOnly) {
      event.preventDefault();
      event.stopImmediatePropagation();
      textarea.focus({preventScroll:true});
      return;
    }
    if (send || retry) {
      keepComposerFocus = true;
      textarea?.focus({preventScroll:true});
      schedule();
    } else if (!event.target.closest?.('#composer')) {
      keepComposerFocus = false;
    }
  }
  function focusChanged(event) {
    if (!event.target.closest?.('#composer, #retry-submission')) keepComposerFocus = false;
  }
  function composerDrop(event) {
    if (event.target.closest?.('#composer') && document.querySelector('#composer textarea')?.readOnly) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }
  function composerKeys(event) {
    if (!event.target.matches?.('#composer textarea') || event.key !== 'Enter') return;
    if (event.isComposing || event.keyCode === 229) { event.stopImmediatePropagation(); return; }
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    if (event.type === 'keypress') {
      if (!event.shiftKey) event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    // Gradio submits on Shift+Enter for multiline inputs; preserve the browser newline instead.
    if (event.shiftKey) { event.stopImmediatePropagation(); return; }
    // Intercept before Gradio's textarea handler; use its existing submit event.
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.repeat || event.target.disabled || event.target.readOnly || dialog) return;
    if (!event.target.value.trim() && !document.querySelector('#composer [aria-label="File thumbnail"]')) return;
    const send = document.querySelector('#composer [data-testid="submit-button"]');
    if (send && !send.disabled) send.click();
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
  observer.observe(document.body, {childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:['disabled','hidden']});
  document.addEventListener("scroll", schedule, {capture:true, passive:true});
  document.addEventListener("click", click);
  document.addEventListener("keydown", keys);
  document.addEventListener("keydown", composerKeys, true);
  document.addEventListener("keypress", composerKeys, true);
  document.addEventListener("click", submissionClick, true);
  document.addEventListener("focusin", focusChanged);
  document.addEventListener("drop", composerDrop, true);
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
    document.removeEventListener("keydown", composerKeys, true);
    document.removeEventListener("keypress", composerKeys, true);
    document.removeEventListener("click", submissionClick, true);
    document.removeEventListener("focusin", focusChanged);
    document.removeEventListener("drop", composerDrop, true);
    window.removeEventListener("resize", schedule);
    media.removeEventListener("change", appearance);
  };
}
