"""Opt-in browser checks against an isolated in-memory backend, never user chats."""

import importlib
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from test_pages import BackendDouble, fake_backend

from api_client import BackendClient

pytestmark = pytest.mark.skipif(
    os.environ.get("LOCALRAG_UI_TESTS") != "1",
    reason="Set LOCALRAG_UI_TESTS=1 and install Playwright Chromium for isolated UI checks.",
)


def test_waiting_respects_reduced_motion_and_deliberate_focus_changes(
    isolated_ui: tuple[str, BackendDouble],
) -> None:
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    started, finish = threading.Event(), threading.Event()

    def delayed_send(key: str, text: str, request_id: str) -> dict[str, object]:
        started.set()
        assert finish.wait(timeout=15)
        return backend.send(key, text, request_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(locale="en-GB", reduced_motion="reduce")
        try:
            page.goto(url)
            expect(page.locator('#active-chat-marker [data-ready="true"]')).to_be_attached()
            with patch.object(BackendClient, "send_message", side_effect=delayed_send):
                composer = page.locator("#composer textarea")
                composer.fill("A slow response")
                composer.press("Enter")
                expect(page.locator("#submission-status")).to_be_visible()
                expect(page.locator(".thinking-dots i").first).to_have_css("animation-name", "none")
                expect(composer).to_be_focused()
                appearance = page.locator("#appearance").get_by_label("Dark", exact=True)
                appearance.check()
                expect(appearance).to_be_focused()
                assert started.wait(timeout=1)
                finish.set()
                expect(page.locator("#submission-status")).to_be_hidden()
                expect(composer).to_have_js_property("readOnly", False)
                expect(appearance).to_be_focused()
                expect(composer).not_to_be_focused()
        finally:
            finish.set()
            browser.close()


@pytest.mark.parametrize("send_method", ["button", "enter"])
def test_composer_sends_text_and_renders_answer(
    isolated_ui: tuple[str, BackendDouble], send_method: str
) -> None:
    """Send through the real component event, not just the controller's Python method."""
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    backend.submissions.clear()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(locale="en-GB")
        page.set_default_timeout(10000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(url)
            expect(page.locator('#active-chat-marker [data-ready="true"]')).to_be_attached()
            composer = page.locator("#composer textarea")
            composer.fill("When is the release?")
            if send_method == "button":
                page.locator('#composer [data-testid="submit-button"]').click()
            else:
                composer.press("Enter")
            expect(page.locator("#transcript")).to_contain_text("The release is on Friday.")
            assert len(backend.submissions) == 1
            assert backend.submissions[0][1] == "When is the release?"
            expect(composer).to_have_value("")
            expect(composer).to_be_focused()
            page.keyboard.type("A follow-up draft")
            expect(composer).to_have_value("A follow-up draft")
            assert errors == []
        finally:
            browser.close()


def test_shift_enter_composition_and_repeated_enter_preserve_draft(
    isolated_ui: tuple[str, BackendDouble],
) -> None:
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    backend.submissions.clear()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(locale="en-GB")
        try:
            page.goto(url)
            expect(page.locator('#active-chat-marker [data-ready="true"]')).to_be_attached()
            composer = page.locator("#composer textarea")
            composer.press("Enter")
            assert backend.chats == {}
            composer.fill("First line")
            composer.press("Shift+Enter")
            composer.press_sequentially("Second line")
            expect(composer).to_have_value("First line\nSecond line")
            assert backend.submissions == []
            composer.evaluate("""element => {
                element.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, isComposing:true}));
                element.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, repeat:true}));
            }""")
            assert backend.submissions == []
            expect(composer).to_have_value("First line\nSecond line")
            composer.press("Enter")
            expect(page.locator("#transcript")).to_contain_text("The release is on Friday.")
            assert len(backend.submissions) == 1
            assert backend.submissions[0][1] == "First line\nSecond line"
        finally:
            browser.close()


@pytest.mark.parametrize(
    "width,scale,mode,send_method",
    [
        (1440, 1, "Light", "enter"),
        (1048, 1.25, "Dark", "button"),
        (390, 1, "Light", "button"),
        (390, 1, "Dark", "enter"),
    ],
)
def test_processing_status_and_retry_keep_the_question(
    isolated_ui: tuple[str, BackendDouble],
    width: int,
    scale: float,
    mode: str,
    send_method: str,
) -> None:
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    backend.submissions.clear()
    started, finish = threading.Event(), threading.Event()

    def delayed_send(key: str, text: str, request_id: str) -> dict[str, object]:
        started.set()
        assert finish.wait(timeout=15)
        return backend.send(key, text, request_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            locale="en-GB", viewport={"width": width, "height": 900}, device_scale_factor=scale
        )
        try:
            page.goto(url)
            expect(page.locator('#active-chat-marker [data-ready="true"]')).to_be_attached()
            expect(page.locator("#scope-notice")).to_contain_text("General chat:")
            page.locator("#appearance").get_by_label(mode, exact=True).check()
            composer = page.locator("#composer textarea")
            with patch.object(BackendClient, "send_message", side_effect=delayed_send):
                composer.fill("A slow response")
                if send_method == "enter":
                    composer.press("Enter")
                else:
                    page.locator('#composer [data-testid="submit-button"]').click()
                expect(page.locator("#submission-status")).to_be_visible()
                expect(page.locator("#submission-status").get_by_role("status")).to_contain_text(
                    "Creating a reply"
                )
                expect(page.locator(".thinking-dots i")).to_have_count(3)
                expect(composer).to_be_enabled()
                expect(composer).to_have_js_property("readOnly", True)
                expect(composer).to_be_focused()
                expect(page.locator("#transcript")).to_have_attribute("aria-busy", "true")
                expect(page.locator('#composer [data-testid="submit-button"]')).to_be_disabled()
                status_box = page.locator("#submission-status").bounding_box()
                composer_box = page.locator("#composer-shell").bounding_box()
                assert (
                    status_box
                    and composer_box
                    and status_box["y"] + status_box["height"] <= composer_box["y"]
                )
                artifacts = Path(__file__).parents[2] / ".tmp" / "reply-status-focus"
                artifacts.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(artifacts / f"waiting-{width}-{mode}.png"))
                assert started.wait(timeout=1)
                finish.set()
                expect(page.locator("#transcript")).to_contain_text("The release is on Friday.")
                expect(page.locator("#submission-status")).to_be_hidden()
                expect(composer).to_be_enabled()
                expect(composer).to_have_value("")
                expect(composer).to_have_js_property("readOnly", False)
                expect(composer).to_be_focused()
                page.keyboard.type("Next draft without clicking")
                expect(composer).to_have_value("Next draft without clicking")
            backend.fail_send = True
            composer.fill("Keep the failed question")
            composer.press("Enter")
            expect(page.locator("#pending-submission")).to_be_visible()
            expect(page.locator("#workspace-error textarea")).to_have_value(
                "Ollama is temporarily unavailable."
            )
            expect(page.locator("#submission-status")).to_be_hidden()
            expect(composer).to_have_value("Keep the failed question")
            expect(composer).to_be_focused()
            expect(composer).to_have_js_property("readOnly", True)
            request_id = backend.submissions[-1][2]
            backend.fail_send = False
            page.get_by_role("button", name="Retry submission", exact=True).click()
            expect(page.locator("#pending-submission")).to_be_hidden()
            expect(composer).to_be_enabled()
            expect(composer).to_have_value("")
            expect(composer).to_be_focused()
            assert backend.submissions[-1][2] == request_id
        finally:
            finish.set()
            backend.fail_send = False
            browser.close()


@pytest.mark.parametrize(
    "width,height,scale,mode",
    [
        (1440, 1000, 1, "Light"),
        (1440, 1000, 1, "Dark"),
        (1048, 985, 1.25, "Light"),
        (1048, 985, 1.25, "Dark"),
        (390, 844, 1, "Light"),
        (390, 844, 1, "Dark"),
    ],
)
def test_selection_borders_and_menu_do_not_change_sidebar_scrolling(
    isolated_ui: tuple[str, BackendDouble], width: int, height: int, scale: float, mode: str
) -> None:
    """Reproduce mouse focus, fractional scaling and clipped menus from the screenshot."""
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    key = backend.create("chat:test", 5, 0.2)["conversation_id"]
    backend.update(key, title="Selected conversation")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}, device_scale_factor=scale, locale="en-GB"
        )
        page.set_default_timeout(15000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{url}/?chat={key}")
            expect(page.locator("#chat-title")).to_contain_text("Selected conversation")
            page.locator("#appearance").get_by_label(mode, exact=True).check()
            appearance = page.locator(f'#appearance label:has(input[value="{mode}"])')
            expect(appearance).to_have_css("outline-style", "none")
            page.locator("#language").get_by_label("Deutsch", exact=True).check()
            expect(page.locator("html")).to_have_attribute("lang", "de")
            language = page.locator('#language label:has(input[value="de"])')
            expect(language).to_have_css("outline-style", "none")
            for control in [appearance, language, page.locator(".chat-row")]:
                borders = control.evaluate("""element => {
                    const css = getComputedStyle(element);
                    return ['Top','Right','Bottom','Left'].map(side =>
                        [css[`border${side}Width`], css[`border${side}Color`]]);
                }""")
                assert all(border == borders[0] for border in borders)
                assert borders[0][0] == "1px"
                expect(control).to_have_css("box-shadow", "none")
            # Keyboard users still receive a visible, unclipped focus indicator.
            page.locator("#composer textarea").focus()
            page.keyboard.press("Tab")
            language.locator("input").focus()
            focused = page.locator("#appearance input:focus-visible, #language input:focus-visible")
            expect(focused).to_have_count(1)
            expect(focused.locator("..")).to_have_css("outline-style", "solid")
            rail = page.locator("#conversation-rail")
            if width <= 900:
                rail.locator(".toggle-button").click()
            scroll_boxes = """() => [...document.querySelectorAll('#conversation-rail, #conversation-rail *')]
                .filter(element => /auto|scroll/.test(getComputedStyle(element).overflowY))
                .map(element => [element.clientHeight, element.scrollHeight, element.clientWidth, element.scrollWidth])"""
            before = page.evaluate(scroll_boxes)
            row = page.locator(".chat-row")
            row.locator("summary").click()
            menu = row.locator(".chat-menu-items")
            expect(menu).to_be_visible()
            assert menu.evaluate("element => element.matches(':popover-open')")
            assert page.evaluate(scroll_boxes) == before
            assert menu.evaluate("element => element.scrollHeight <= element.clientHeight")
            for action in menu.get_by_role("button").all():
                assert action.evaluate("""element => {
                    const b = element.getBoundingClientRect();
                    return b.left >= 0 && b.top >= 0 && b.right <= innerWidth && b.bottom <= innerHeight
                        && element.contains(document.elementFromPoint(b.left + b.width/2, b.top + b.height/2));
                }""")
            artifacts = Path(__file__).parents[2] / ".tmp" / "chat-menu-borders"
            artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts / f"menu-{width}-{mode}.png"))
            menu.get_by_role("button", name="Umbenennen", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(menu).to_be_hidden()
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).to_be_hidden()
            # A long chat list may scroll, but opening its last menu must add no overflow.
            for index in range(30):
                item = backend.create("chat:test", 5, 0.2)
                backend.update(item["conversation_id"], title=f"Chat {index:02}")
            rail.get_by_role("button", name="Aktualisieren", exact=True).click()
            expect(page.locator(".chat-row")).to_have_count(31)
            last = page.locator(".chat-row").last
            last.locator("summary").scroll_into_view_if_needed()
            before = page.evaluate(scroll_boxes)
            last.locator("summary").click()
            menu = last.locator(".chat-menu-items")
            expect(menu).to_be_visible()
            assert page.evaluate(scroll_boxes) == before
            assert menu.evaluate("""element => {
                const b = element.getBoundingClientRect();
                return b.top >= 0 && b.bottom <= innerHeight;
            }""")
            page.keyboard.press("Escape")
            expect(menu).to_be_hidden()
            assert errors == []
        finally:
            browser.close()


@pytest.fixture(scope="module")
def isolated_ui() -> Iterator[tuple[str, BackendDouble]]:
    """Serve the actual application while replacing only its backend HTTP boundary."""
    with fake_backend() as backend:
        import app as app_module

        app = importlib.reload(app_module).app

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
            thread.start()
            deadline = time.monotonic() + 15
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert server.started
            try:
                yield f"http://127.0.0.1:{sock.getsockname()[1]}", backend
            finally:
                server.should_exit = True
                thread.join(timeout=15)


@pytest.mark.parametrize(
    "width,height,scale,mode",
    [
        (1440, 1000, 1, "Light"),
        (1440, 1000, 1, "Dark"),
        (1048, 939, 1.25, "Light"),
        (1048, 939, 1.25, "Dark"),
        (390, 844, 1, "Light"),
        (390, 844, 1, "Dark"),
    ],
)
def test_folder_dialog_is_compact_and_controls_do_not_overlap(
    isolated_ui: tuple[str, BackendDouble], width: int, height: int, scale: float, mode: str
) -> None:
    """Keep folder selection in normal dialog flow, including creating and reusing folders."""
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    key = backend.create("chat:test", 5, 0.2)["conversation_id"]
    backend.update(key, title="Strassensperrung Bülach")
    for folder in ["Arbeit", "Privat"]:
        item = backend.create("chat:test", 5, 0.2)
        backend.update(item["conversation_id"], title=f"Existing {folder}", folder=folder)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}, device_scale_factor=scale, locale="en-GB"
        )
        page.set_default_timeout(15000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{url}/?chat={key}")
            expect(page.locator("#chat-title")).to_contain_text("Strassensperrung Bülach")
            page.locator("#appearance").get_by_label(mode, exact=True).check()
            page.locator("#language").get_by_label("Deutsch", exact=True).check()
            expect(page.locator("html")).to_have_attribute("lang", "de")
            page.locator("#composer textarea").fill("Keep this draft")
            rail = page.locator("#conversation-rail")

            def open_move() -> None:
                if not rail.evaluate("element => element.classList.contains('open')"):
                    rail.locator(".toggle-button").click()
                row = page.locator(".chat-row").filter(has=page.locator(f'[data-chat="{key}"]'))
                row.locator("summary").click()
                row.get_by_role("button", name="In Ordner verschieben", exact=True).click()

            open_move()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            expect(dialog.locator("#chat-manager-title")).to_have_text("In Ordner verschieben")
            expect(dialog.locator("#chat-manager-context")).to_have_text("Strassensperrung Bülach")
            expect(dialog.locator("#manager-name")).to_be_hidden()
            expect(dialog.get_by_role("button", name="Chat löschen", exact=True)).to_have_count(0)
            expect(dialog.get_by_role("combobox")).to_have_count(0)
            dialog.get_by_label("Arbeit", exact=True).check()
            dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
            expect(dialog).to_be_hidden()
            assert backend.chats[key]["folder"] == "Arbeit"
            assert backend.chats[key]["title"] == "Strassensperrung Bülach"
            open_move()
            expect(dialog.get_by_label("Arbeit", exact=True)).to_be_checked()
            dialog.get_by_label("Neuen Ordner erstellen", exact=True).check()
            expect(dialog.locator("#manager-new-folder textarea")).to_be_visible()
            artifacts = Path(__file__).parents[2] / ".tmp" / "folder-dialog"
            artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts / f"move-{width}-{mode}.png"))
            dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
            expect(dialog.locator("#manager-notice")).to_contain_text("Gib einen Ordnernamen ein.")
            expect(page.locator("#workspace-error")).to_be_hidden()
            dialog.locator("#manager-new-folder textarea").fill("Dokumente")
            # The list, new-name field and action buttons occupy separate vertical regions.
            bounds = dialog.bounding_box()
            assert bounds and bounds["x"] >= 12 and bounds["y"] >= 12
            assert bounds["x"] + bounds["width"] <= width - 12
            assert bounds["y"] + bounds["height"] <= height - 12
            for selector in [
                "#manager-folder label",
                "#manager-new-folder textarea",
                "#manager-actions button",
            ]:
                for control in dialog.locator(selector).all():
                    assert control.evaluate("""element => {
                        const b = element.getBoundingClientRect();
                        return element.contains(document.elementFromPoint(b.left+b.width/2, b.top+b.height/2));
                    }""")
            assert dialog.evaluate(
                "element => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight"
            )
            page.screenshot(path=str(artifacts / f"validation-{width}-{mode}.png"))
            dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
            expect(dialog).to_be_hidden()
            assert backend.chats[key]["folder"] == "Dokumente"
            expect(page.locator("#composer textarea")).to_have_value("Keep this draft")
            open_move()
            expect(dialog.get_by_label("Dokumente", exact=True)).to_be_checked()
            dialog.get_by_label("Privat", exact=True).check()
            dialog.get_by_role("button", name="Abbrechen", exact=True).click()
            expect(dialog).to_be_hidden()
            assert backend.chats[key]["folder"] == "Dokumente"
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize(
    "width,mode", [(1440, "Light"), (1440, "Dark"), (390, "Light"), (390, "Dark")]
)
def test_icons_localization_and_sidebar_management(
    isolated_ui: tuple[str, BackendDouble], width: int, mode: str
) -> None:
    url, backend = isolated_ui
    backend.chats.clear()
    backend.documents.clear()
    for title in ["Open conversation", "Manage this conversation"]:
        item = backend.create("chat:test", 5, 0.2)
        backend.update(item["conversation_id"], title=title)
    first, target = list(backend.chats)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900}, locale="en-GB")
        page.set_default_timeout(15000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{url}/?chat={first}")
            expect(page.locator("#chat-title")).to_contain_text("Open conversation")
            page.locator("#appearance").get_by_label(mode, exact=True).check()
            page.locator("#composer textarea").fill("Preserve this draft")
            page.locator("#language").get_by_label("Deutsch", exact=True).check()
            expect(page.locator("html")).to_have_attribute("lang", "de")
            expect(page.locator("#composer textarea")).to_have_attribute(
                "placeholder", "Stelle eine Frage oder hänge Dokumente an"
            )
            expect(page.locator("#composer textarea")).to_have_value("Preserve this draft")
            expect(page.locator(f'#appearance input[value="{mode}"]')).to_be_checked()
            assert page.locator("body").evaluate(
                "element => element.classList.contains('dark')"
            ) == (mode == "Dark")
            rail = page.locator("#conversation-rail")
            if width <= 900:
                rail.locator(".toggle-button").click()
            expect(page.locator("#find-chat textarea")).to_have_css("border-top-width", "0px")
            expect(page.locator("#find-chat textarea")).to_have_css(
                "background-color", "rgba(0, 0, 0, 0)"
            )
            row = page.locator(".chat-row").filter(has_text="Manage this conversation")
            row.locator("summary").click()
            row.get_by_role("button", name="Umbenennen", exact=True).click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            expect(rail).to_have_js_property("inert", True)
            dialog.locator("#manager-name textarea").fill("Projektplanung")
            dialog.get_by_role("button", name="Änderungen speichern", exact=True).click()
            expect(dialog).to_be_hidden()
            row = page.locator(".chat-row").filter(has_text="Projektplanung")
            row.locator("summary").click()
            row.get_by_role("button", name="In Ordner verschieben", exact=True).click()
            dialog.get_by_label("Neuen Ordner erstellen", exact=True).check()
            dialog.locator("#manager-new-folder textarea").fill("Arbeit")
            dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
            expect(dialog).to_be_hidden()
            expect(page.locator(".chat-folder > summary")).to_contain_text("Arbeit")
            expect(page.locator(f'#appearance input[value="{mode}"]')).to_be_checked()
            assert backend.chats[target]["folder"] == "Arbeit"
            assert backend.chats[target]["title"] == "Projektplanung"
            expect(page.locator("#chat-title")).to_contain_text("Open conversation")
            expect(page.locator("#composer textarea")).to_have_value("Preserve this draft")
            # Reload proves browser preferences and backend folder assignments restore together.
            if width == 1440:
                row = page.locator(".chat-row").filter(has_text="Projektplanung")
                row.locator("summary").click()
                row.get_by_role("button", name="In Ordner verschieben", exact=True).click()
                dialog.get_by_label("Ohne Ordner", exact=True).check()
                dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
                expect(dialog).to_be_hidden()
                expect(page.locator(".chat-folder")).to_have_count(0)
                assert backend.chats[target]["folder"] == ""
                row.locator("summary").click()
                row.get_by_role("button", name="In Ordner verschieben", exact=True).click()
                dialog.get_by_label("Neuen Ordner erstellen", exact=True).check()
                dialog.locator("#manager-new-folder textarea").fill("Arbeit")
                dialog.get_by_role("button", name="Chat verschieben", exact=True).click()
                expect(dialog).to_be_hidden()
            artifacts = Path(__file__).parents[2] / ".tmp" / "chat-management"
            artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts / f"folders-de-{width}-{mode}.png"))
            page.reload()
            expect(page.locator("html")).to_have_attribute("lang", "de")
            expect(page.locator(".chat-folder > summary")).to_contain_text("Arbeit")
            if width <= 900:
                rail.locator(".toggle-button").click()
            row = page.locator(".chat-row").filter(has_text="Projektplanung")
            row.locator("summary").click()
            row.get_by_role("button", name="Chat löschen", exact=True).click()
            expect(dialog).to_be_visible()
            dialog.get_by_role("button", name="Chat löschen", exact=True).click()
            expect(dialog.locator("#manager-notice")).to_contain_text("Bestätige")
            assert target in backend.chats
            dialog.get_by_label("Diesen Chat und seine privaten Dateien löschen").check()
            dialog.get_by_role("button", name="Chat löschen", exact=True).click()
            expect(dialog).to_be_hidden()
            expect(page.locator(".chat-folder")).to_have_count(0)
            assert target not in backend.chats and first in backend.chats
            if width <= 900:
                rail.locator(".toggle-button").click()
            page.locator("#language").get_by_label("English", exact=True).check()
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("#new-chat")).to_have_text("New chat")
            assert page.locator("body").evaluate("element => element.scrollWidth <= innerWidth")
            # Native HTML selection still restores each chat's own draft.
            page.locator("#composer textarea").fill("Draft in the first chat")
            if width <= 900:
                rail.locator(".toggle-button").click()
            page.locator("#new-chat").click()
            expect(page.locator("#chat-title")).to_contain_text("New chat")
            page.locator("#composer textarea").fill("Draft in the new chat")
            if width <= 900:
                rail.locator(".toggle-button").click()
            page.get_by_role("button", name="Open conversation", exact=True).click()
            expect(page.locator("#chat-title")).to_contain_text("Open conversation")
            expect(page.locator("#composer textarea")).to_have_value("Draft in the first chat")
            page.screenshot(path=str(artifacts / f"workspace-{width}-{mode}.png"))
            assert errors == []
        finally:
            browser.close()
