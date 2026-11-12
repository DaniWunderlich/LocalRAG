"""Escaped, grouped chat navigation with native keyboard-accessible controls."""

from html import escape

from localization import translate
from workspace import Session

RAIL_JS = """
element.addEventListener('click', event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  event.stopPropagation();
  element.querySelectorAll('.chat-menu[open]').forEach(menu => menu.removeAttribute('open'));
  trigger('click', {action:button.dataset.action, chat_id:button.dataset.chat});
});
element.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    const menu = event.target.closest('.chat-menu');
    if (menu) { menu.removeAttribute('open'); menu.querySelector('summary').focus(); }
  }
});
element.addEventListener('toggle', event => {
  const menu = event.target;
  if (!menu.matches('.chat-menu')) return;
  const items = menu.querySelector('.chat-menu-items');
  if (!menu.open) { items.hidePopover(); return; }
  element.querySelectorAll('.chat-menu[open]').forEach(other => {
    if (other !== menu) other.removeAttribute('open');
  });
  // The browser's top layer escapes the sidebar's scrolling and clipping boxes.
  items.showPopover();
  const anchor = menu.querySelector('summary').getBoundingClientRect();
  const bounds = items.getBoundingClientRect();
  const left = Math.max(12, Math.min(anchor.right - bounds.width, innerWidth - bounds.width - 12));
  const below = anchor.bottom + 6;
  const top = below + bounds.height <= innerHeight - 12 ? below : Math.max(12, anchor.top - bounds.height - 6);
  items.style.left = `${left}px`;
  items.style.top = `${top}px`;
}, true);
"""


def chat_navigation(session: Session) -> str:
    """Group chats by durable folder; retain recent-activity order within each group."""

    def text(value: str) -> str:
        return escape(translate(value, session.language), quote=True)

    groups: dict[str, list[dict[str, str]]] = {}
    for item in session.summaries:
        if (
            session.chat_query.casefold()
            in (item["title"] + " " + item.get("folder", "")).casefold()
        ):
            groups.setdefault(item.get("folder", ""), []).append(item)
    result = []
    for folder in sorted(groups, key=lambda value: (bool(value), value.casefold())):
        rows = []
        for item in groups[folder]:
            key = escape(item["conversation_id"], quote=True)
            title = escape(item["title"])
            if item["status"] != "active":
                title += " · " + text("deletion pending")
            selected = (
                ' aria-current="true"' if item["conversation_id"] == session.active_id else ""
            )
            actions = "".join(
                f'<button type="button" data-action="{action}" data-chat="{key}">{text(label)}</button>'
                for action, label in [
                    ("rename", "Rename"),
                    ("move", "Move to folder"),
                    ("delete", "Delete chat"),
                ]
            )
            rows.append(
                f'<div class="chat-row"><button type="button" class="chat-select" data-action="select" data-chat="{key}"{selected}>{title}</button>'
                f'<details class="chat-menu"><summary aria-label="{text("Chat actions")}: {escape(item["title"], quote=True)}" title="{text("Chat actions")}">···</summary>'
                f'<div class="chat-menu-items" popover="manual">{actions}</div></details></div>'
            )
        content = "".join(rows)
        if folder:
            result.append(
                f'<details class="chat-folder" open><summary>▱ {escape(folder)}</summary>{content}</details>'
            )
        else:
            result.append(f'<div class="unfiled-chats">{content}</div>')
    return "".join(result) or f'<p class="muted">{text("No chats found.")}</p>'
