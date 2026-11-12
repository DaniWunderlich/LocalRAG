"""Optional browser acceptance against an isolated, seeded Gradio stack."""

import os
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("GRADIO_E2E_URL", "")
pytestmark = pytest.mark.skipif(
    not URL, reason="Set GRADIO_E2E_URL to the isolated seeded review chat."
)
ARTIFACTS = Path(__file__).parents[2] / ".tmp" / "gradio-browser"


@pytest.fixture(params=[(1440, 1000), (768, 1000), (390, 844)])
def page(request: pytest.FixtureRequest) -> Iterator[Page]:
    """Use a separate headless browser and collect failures without user browser access."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": request.param[0], "height": request.param[1]}
        )
        page = context.new_page()
        errors: list[str] = []
        external: list[str] = []
        page.on("pageerror", lambda failure: errors.append(str(failure)))
        page.on(
            "request",
            lambda request: (
                external.append(request.url)
                if urlsplit(request.url).netloc
                and urlsplit(request.url).netloc != urlsplit(URL).netloc
                else None
            ),
        )
        page.set_default_timeout(20000)
        page.goto(URL)
        expect(page.locator("#chat-title")).to_contain_text("Orion visual review")
        expect(page.locator('#active-chat-marker [data-ready="true"]')).to_be_attached()
        if request.param[0] <= 900:
            expect(page.locator("#conversation-rail")).not_to_have_class(re.compile(r"\bopen\b"))
        yield page
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / f"{request.node.name}.png"))
        assert errors == []
        assert external == []
        context.close()
        browser.close()


def test_composer_placement_appearance_and_scroll(page: Page) -> None:
    """Keep controls visible and correctly ordered while navigating a long transcript."""
    box = page.locator("#composer-shell").bounding_box()
    assert box and page.viewport_size and box["y"] + box["height"] <= page.viewport_size["height"]
    buttons = [
        page.locator("#composer-settings"),
        page.locator("#composer-library"),
        page.locator('#composer [data-testid="upload-button"]'),
        page.locator('#composer [data-testid="submit-button"]'),
    ]
    positions = [button.bounding_box() for button in buttons]
    assert all(positions)
    assert positions[0] and positions[1] and positions[2]
    assert positions[0]["x"] < positions[1]["x"] < positions[2]["x"]
    assert (
        max(item["y"] + item["height"] / 2 for item in positions if item)
        - min(item["y"] + item["height"] / 2 for item in positions if item)
        <= 0.5
    )
    composer = page.locator("#composer textarea")
    composer.fill("Draft remains while changing appearance")
    page.locator("#appearance").get_by_label("Dark", exact=True).check()
    expect(page.locator("body")).to_have_class("dark")
    expect(
        page.locator("#appearance label").filter(has=page.locator('input[value="Dark"]'))
    ).to_have_css("background-color", "rgb(37, 45, 40)")
    expect(composer).to_have_value("Draft remains while changing appearance")
    assert (
        page.locator("#composer-shell").evaluate("e=>getComputedStyle(e).backgroundColor")
        == "rgb(32, 39, 34)"
    )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(ARTIFACTS / f"dark-{page.viewport_size['width'] if page.viewport_size else 0}.png")
    )
    page.locator("#appearance").get_by_label("Light", exact=True).check()
    expect(page.locator("body")).not_to_have_class("dark")
    scroller = page.locator("#transcript .panel-wrap")
    scroller.evaluate("e=>e.scrollTop=0")
    jump = page.get_by_role("button", name="Jump to latest message")
    expect(jump).to_be_visible()
    jump.click()
    expect(jump).to_be_hidden()
    assert scroller.evaluate("e=>e.scrollHeight-e.scrollTop-e.clientHeight") < 80
    page.reload()
    expect(page.locator("#chat-title")).to_contain_text("Orion visual review")
    expect(page.locator("body")).not_to_have_class("dark")


def test_settings_library_and_source_disclosure(page: Page) -> None:
    """Exercise real callback wiring and keep the live composer through changes."""
    page.locator("#composer textarea").fill("Unsent question for the visual review")
    page.locator("#composer-settings").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(
        page.get_by_role("dialog").get_by_text("Maximum source excerpts", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_hidden()
    expect(page.locator("#composer textarea")).to_have_value(
        "Unsent question for the visual review"
    )
    page.get_by_role("button", name="Include shared library", exact=True).click()
    expect(page.get_by_role("button", name="Exclude shared library", exact=True)).to_be_visible()
    page.wait_for_function("""() => {
        const image = document.querySelector('#composer-library img');
        return image?.complete && image.naturalWidth > 0 && image.src.endsWith('library-check.svg');
    }""")
    expect(page.locator("#composer textarea")).to_have_value(
        "Unsent question for the visual review"
    )
    page.get_by_role("button", name="Exclude shared library", exact=True).click()
    expect(page.get_by_role("button", name="Include shared library", exact=True)).to_be_visible()
    details = page.locator("#transcript details").last
    details.locator("summary").click()
    expect(details.locator("pre")).to_contain_text("Project Orion")
    expect(page.locator("#workspace-error")).to_be_hidden()


def test_file_only_submission_uses_the_native_upload(page: Page, tmp_path: Path) -> None:
    """Upload through the real frontend cache and index without invoking chat generation."""
    if not page.locator("#conversation-rail").evaluate("e=>e.classList.contains('open')"):
        page.get_by_role("button", name="Toggle Sidebar", exact=True).click()
    page.locator("#new-chat").click()
    expect(page.locator("#chat-title")).to_contain_text("New chat")
    file = tmp_path / "gradio-browser-upload.txt"
    file.write_text("The browser acceptance document concerns Project Cedar.", encoding="utf-8")
    page.locator('#composer input[type="file"]').set_input_files(file)
    submit = page.locator('#composer [data-testid="submit-button"]')
    expect(submit).to_be_enabled()
    submit.click()
    attachments = page.get_by_role("button", name=re.compile("Chat documents"))
    expect(attachments).to_be_visible(timeout=120000)
    attachments.click()
    expect(page.locator("#attachment-table")).to_contain_text(file.name)
    expect(page.locator("#workspace-error")).to_be_hidden()
    assert "chat=" in page.url
    assert page.locator('#transcript [data-testid="user"]').count() == 0


def test_chat_switching_keeps_independent_composer_drafts(page: Page) -> None:
    """Follow the native rail between saved chats without mixing unsent questions."""
    page.locator("#composer textarea").fill("Unsent visual review question")
    if not page.locator("#conversation-rail").evaluate("e=>e.classList.contains('open')"):
        page.get_by_role("button", name="Toggle Sidebar", exact=True).click()
    page.get_by_role("button", name="Shared Gradio acceptance", exact=True).click()
    expect(page.locator("#chat-title")).to_contain_text("Shared Gradio acceptance")
    expect(page.locator("#composer textarea")).to_have_value("")
    expect(page.get_by_role("button", name="Exclude shared library", exact=True)).to_be_visible()
    page.locator("#composer textarea").fill("Unsent shared-library question")
    if not page.locator("#conversation-rail").evaluate("e=>e.classList.contains('open')"):
        page.get_by_role("button", name="Toggle Sidebar", exact=True).click()
    page.get_by_role("button", name="Orion visual review", exact=True).click()
    expect(page.locator("#chat-title")).to_contain_text("Orion visual review")
    expect(page.locator("#composer textarea")).to_have_value("Unsent visual review question")
    expect(page.get_by_role("button", name="Include shared library", exact=True)).to_be_visible()
