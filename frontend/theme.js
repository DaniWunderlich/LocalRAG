/* Mirror documented component theme variables to the shared reading surface. */
export default function ({ parentElement }) {
  window.__localRagAppearance?.();
  const root = document.documentElement;
  const properties = {
    "background": "background-color",
    "surface": "background-color",
    "alternative": "secondary-background-color",
    "text": "text-color",
    "muted": "gray-text-color",
    "border": "border-color",
    "accent": "primary-color",
    "success": "green-text-color",
    "warning": "yellow-text-color",
    "error": "red-text-color",
    "disabled": "gray-text-color",
  };

  function sync() {
    const theme = getComputedStyle(parentElement);
    for (const [name, native] of Object.entries(properties)) {
      const value = theme.getPropertyValue(`--st-${native}`).trim();
      if (value && root.style.getPropertyValue(`--rag-${name}`) !== value) {
        root.style.setProperty(`--rag-${name}`, value);
      }
    }
  }

  const observer = new MutationObserver(sync);
  // Streamlit updates the theme wrapper's class when native appearance changes.
  for (let node = parentElement; node && node !== root; node = node.parentElement) {
    observer.observe(node, { attributes: true, attributeFilter: ["class", "style"] });
  }
  sync();
  const dispose = () => {
    observer.disconnect();
    if (window.__localRagAppearance === dispose) delete window.__localRagAppearance;
  };
  window.__localRagAppearance = dispose;
  return dispose;
}
