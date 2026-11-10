/* Local composer behaviour. No user content, requests or remote scripts. */
export default function () {
  window.__localRagComposer?.();
  let main = null;
  let shell = null;
  let transcript = null;
  let jump = null;
  let frame = 0;
  const resize = new ResizeObserver(() => schedule());

  function detach() {
    document.removeEventListener("scroll", schedule, true);
    resize.disconnect();
    jump?.remove();
    main = shell = transcript = jump = null;
  }

  function makeJump() {
    const button = document.createElement("button");
    button.id = "rag-jump-to-end";
    button.type = "button";
    button.hidden = true;
    button.setAttribute("aria-label", "Jump to latest message");
    button.title = "Jump to latest message";
    button.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14m-6-6 6 6 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    button.addEventListener("click", () => {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      transcript?.lastElementChild?.scrollIntoView({
        block: "end", behavior: reduced ? "instant" : "smooth",
      });
    });
    return button;
  }

  function sync() {
    frame = 0;
    const nextMain = document.querySelector('[data-testid="stMain"]');
    const nextShell = document.querySelector(".st-key-composer-shell");
    const nextTranscript = document.querySelector(".st-key-transcript");
    if (!nextMain || !nextShell || !nextTranscript) {
      detach();
      return;
    }
    if (main !== nextMain || shell !== nextShell || transcript !== nextTranscript || !jump?.isConnected) {
      detach();
      main = nextMain;
      shell = nextShell;
      transcript = nextTranscript;
      jump = makeJump();
      shell.appendChild(jump);
      document.addEventListener("scroll", schedule, { passive: true, capture: true });
      resize.observe(main);
      resize.observe(shell);
      resize.observe(transcript);
    }

    const hasMessages = transcript.querySelector('[class*="st-key-turn-"]') !== null;
    const remaining = transcript.getBoundingClientRect().bottom - shell.getBoundingClientRect().top;
    jump.hidden = !hasMessages || remaining <= 80;
  }

  function schedule() {
    if (!frame) frame = window.requestAnimationFrame(sync);
  }

  const mutations = new MutationObserver(schedule);
  mutations.observe(document.body, { childList: true, subtree: true, characterData: true });
  window.addEventListener("resize", schedule, { passive: true });
  schedule();
  const dispose = () => {
    mutations.disconnect();
    window.removeEventListener("resize", schedule);
    if (frame) window.cancelAnimationFrame(frame);
    detach();
    if (window.__localRagComposer === dispose) delete window.__localRagComposer;
  };
  window.__localRagComposer = dispose;
  return dispose;
}
