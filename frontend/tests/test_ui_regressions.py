"""Regression checks for modal layering, cached icons and composer alignment."""

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("GRADIO_E2E_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Requires the isolated, seeded Gradio test stack.")
ARTIFACTS = Path(__file__).parents[2] / ".tmp" / "gradio-ui-fixes"


def assert_aligned(page: Page) -> None:
    """Measure both the native buttons and their actual SVG/image centres."""
    page.wait_for_function("""() => {
        const buttons = [document.getElementById('composer-settings'),
            document.getElementById('composer-library'),
            document.querySelector('#composer [data-testid="upload-button"]'),
            document.querySelector('#composer [data-testid="submit-button"]')];
        if (buttons.some(button => !button)) return false;
        const centres = buttons.map(button => {
            const bounds = button.getBoundingClientRect();
            return bounds.top + bounds.height / 2;
        });
        return Math.max(...centres) - Math.min(...centres) <= 0.5;
    }""")
    centres = page.locator(
        "#composer-settings img, #composer-library img, #composer .submit-button svg"
    ).evaluate_all("""elements => elements.map(element => {
        const bounds = element.getBoundingClientRect();
        return bounds.top + bounds.height / 2;
    })""")
    assert len(centres) == 3
    assert max(centres) - min(centres) <= 0.5
    plus = page.locator('#composer [data-testid="upload-button"]')
    assert plus.evaluate('element => getComputedStyle(element, "::after").height') == "22px"


def assert_library_image(page: Page, checked: bool) -> None:
    """Wait for the correct asset to load, including immediately after a callback."""
    filename = "library-check.svg" if checked else "library.svg"
    page.wait_for_function(
        """filename => {
        const image = document.querySelector('#composer-library img');
        return image?.complete && image.naturalWidth > 0 && image.naturalHeight > 0
            && image.src.endsWith(filename);
    }""",
        arg=filename,
    )


@pytest.mark.parametrize(
    "width,height,scale,mode",
    [
        (1440, 1000, 1, "Light"),
        (906, 843, 1.25, "Light"),
        (906, 843, 1.25, "Dark"),
        (390, 844, 1, "Dark"),
    ],
)
def test_sidebar_dialog_and_composer_icons(
    width: int, height: int, scale: float, mode: str, tmp_path: Path
) -> None:
    """Reproduce the supplied screenshot and verify interaction above the open rail."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=scale
        )
        page = context.new_page()
        page.set_default_timeout(20000)
        errors: list[str] = []
        page.on("pageerror", lambda failure: errors.append(str(failure)))
        try:
            page.goto(URL)
            expect(page.locator("#chat-title")).to_contain_text("Orion visual review")
            page.locator("#appearance").get_by_label(mode, exact=True).check()
            if mode == "Dark":
                expect(page.locator("body")).to_have_class("dark")
            if width > 900:
                expect(page.locator("#conversation-rail")).to_have_class(re.compile(r"\bopen\b"))
            if (
                page.locator("#composer-library").get_attribute("aria-label")
                == "Exclude shared library"
            ):
                page.locator("#composer-library").click()
                expect(page.locator("#composer-library")).to_have_attribute(
                    "aria-label", "Include shared library"
                )
            assert_library_image(page, False)
            for _ in range(2):
                page.locator("#composer-library").click()
                expect(page.locator("#composer-library")).to_have_attribute(
                    "aria-label", "Exclude shared library"
                )
                assert_library_image(page, True)
                assert_aligned(page)
                page.locator("#composer-library").click()
                expect(page.locator("#composer-library")).to_have_attribute(
                    "aria-label", "Include shared library"
                )
                assert_library_image(page, False)
            page.locator("#composer textarea").fill("A long draft retains its own line.\n" * 6)
            assert_aligned(page)
            upload = tmp_path / "layout-proof.txt"
            upload.write_text(
                "A temporary layout test; never submitted to the backend.", encoding="utf-8"
            )
            page.locator('#composer input[type="file"]').set_input_files(upload)
            expect(page.locator('#composer [aria-label="File thumbnail"]')).to_have_count(1)
            assert_aligned(page)
            page.locator("#composer-settings").click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            box = dialog.bounding_box()
            assert box
            assert box["x"] >= 12 and box["y"] >= 12
            assert box["x"] + box["width"] <= width - 12
            assert box["y"] + box["height"] <= height - 12
            assert dialog.evaluate("""element => {
                const box = element.getBoundingClientRect();
                return [[box.left+12,box.top+12],[box.left+12,box.top+box.height/2],
                    [box.right-12,box.bottom-12]].every(([x,y])=>element.contains(document.elementFromPoint(x,y)));
            }""")
            expect(page.locator("#conversation-rail")).to_have_js_property("inert", True)
            page.get_by_role("button", name="Close", exact=True).focus()
            page.keyboard.press("Tab")
            assert dialog.evaluate("element => element.contains(document.activeElement)")
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(ARTIFACTS / f"dialog-{width}-{mode}.png"))
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(dialog).to_be_hidden()
            expect(page.locator("#conversation-rail")).to_have_js_property("inert", False)
            expect(page.locator("#composer textarea")).to_have_value(
                "A long draft retains its own line.\n" * 6
            )
            assert_library_image(page, False)
            assert_aligned(page)
            page.screenshot(path=str(ARTIFACTS / f"composer-{width}-{mode}.png"))
            assert errors == []
        finally:
            context.close()
            browser.close()
