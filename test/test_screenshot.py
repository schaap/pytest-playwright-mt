# Copyright 2026 Thomas Schaap
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Tests for the screenshot feature
"""

import shutil

import pytest
from helpers import ask_confirmation
from playwright.sync_api import ViewportSize
from playwright_pytester import PlaywrightPytester, name_matches_test, pytester_artifacts
from server import WebServer

from pytest_playwright_mt import BrowserName, PlaywrightMTFixture, RecordingOption


def test_screenshot_captures(playwright_pytester: PlaywrightPytester, browser_name: BrowserName) -> None:
    """
    Verify that screenshots can be captured, and that capture observes the set ``RecordingOption``.
    """

    # The tests that are expected to store a screenshot
    expected_screenshots: list[tuple[str, RecordingOption | BrowserName]] = [
        ("test_screenshot_captures_on_success", RecordingOption.ON),
        ("test_screenshot_captures_on_failure", RecordingOption.ON),
        ("test_screenshot_captures_on_failure", RecordingOption.RETAIN_ON_FAILURE),
        # Using the BrowserName is not distinguishing in any way, but it's easier for the code down below than None:
        ("test_screenshot_multiple_pages", browser_name),
    ]

    # The tests that are expected to run but must not store a screenshot (their output directory *may* be present)
    expected_no_screenshots: list[tuple[str, RecordingOption | BrowserName]] = [
        ("test_screenshot_does_not_capture_on_success", RecordingOption.OFF),
        ("test_screenshot_does_not_capture_on_success", RecordingOption.RETAIN_ON_FAILURE),
        ("test_screenshot_does_not_capture_on_failure", RecordingOption.OFF),
    ]

    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file("_test_screenshot_capture.py")

    result = playwright_pytester.pytester.runpytest_inprocess(*playwright_pytester.params)
    result.assert_outcomes(passed=4, failed=3)

    # Check that all expected screenshots are there
    for test_name, option in expected_screenshots:
        assert any(pytester_artifacts(playwright_pytester, test_name, [str(option)], "screenshots/*/*.png"))

    # Check that all expected absent screenshots are not there
    for test_name, option in expected_no_screenshots:
        assert not any(pytester_artifacts(playwright_pytester, test_name, [str(option)], "screenshots/*/*"))

    # Check that there are no unexpected output directories. This basically says that every directory in the pytester's
    # output directory must match an entry in the expected screenshots and expected no-screenshots lists.
    all_tests = [(test_name, [str(option)]) for test_name, option in [*expected_screenshots, *expected_no_screenshots]]
    assert not [
        directory
        for directory in playwright_pytester.output_dir.glob("*")
        if not any(name_matches_test(directory, test_name, params) for test_name, params in all_tests)
    ], "Found unexpected output directories"

    # Special case: verify that we have all expected screenshots of the multi-screenshot test. We expect 3 screenshots,
    # across 2 contexts.
    screenshots = pytester_artifacts(
        playwright_pytester, "test_screenshot_multiple_pages", [str(browser_name)], "screenshots/*/*.png"
    )
    assert len(screenshots) == 3
    assert len({screenshot.parent for screenshot in screenshots}) == 2


@pytest.mark.usefixtures("interactive")
def test_screenshot_option_full_page(
    playwright_pytester: PlaywrightPytester,
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    browser_name: BrowserName,
) -> None:
    """
    Verify that ``--full-page-screenshot`` screenshots work.

    Note that this test is very much dependent on the configured viewports of the browsers involved, as well as the
    sizes of elements in the pages being shown. Take care to balance them correctly when adjusting this test.
    """
    # The page to screenshot. This is specifically designed to be just a blue patch within the configured viewport of
    # the browser, but have a red part and a notice below that. The red part and the notice should only show up in the
    # full page screenshot, as they fall outside the browser's viewport.
    (playwright_pytester.pytester.path / "index.html").write_text(
        WebServer.basic_html(
            "Big page",
            """
        <div style="background-color: #000088; height: 300px; width: 100%">Ignore this part</div><hr/>
        <div style="background-color: #660000; height: 100px; width: 100%">Empty part</div><hr/>
        <p><b>YOU SHOULD SEE THIS ONLY IN THE FULL PAGE SCREENSHOT</b></p>
    """,
        )
    )

    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file("_test_screenshot_full_page.py")

    # Normal screenshot
    result = playwright_pytester.pytester.runpytest_inprocess(
        *playwright_pytester.params, "-k", "test_screenshot_not_full_page", "--screenshot", "on"
    )
    result.assert_outcomes(passed=1)
    normal_screenshots = pytester_artifacts(
        playwright_pytester, "test_screenshot_not_full_page", [str(browser_name)], "screenshots/*/*.png"
    )
    assert len(normal_screenshots) == 1

    # Full page screenshot
    result = playwright_pytester.pytester.runpytest_inprocess(
        *playwright_pytester.params, "-k", "test_screenshot_full_page", "--screenshot", "on", "--full-page-screenshot"
    )
    result.assert_outcomes(passed=1)
    full_page_screenshots = pytester_artifacts(
        playwright_pytester, "test_screenshot_full_page", [str(browser_name)], "screenshots/*/*.png"
    )
    assert len(full_page_screenshots) == 1

    # Build and show a page to compare the two screenshots
    # This is specifically designed to correctly show both full screenshots side-by-side, so the tester can easily
    # compare them.
    shutil.move(normal_screenshots[0], web_server.pages_dir / "normal.png")
    shutil.move(full_page_screenshots[0], web_server.pages_dir / "fullpage.png")
    (web_server.pages_dir / "index.html").write_text(
        WebServer.basic_html(
            "Screenshot Results",
            """
            <table>
                <thead>
                    <tr style="text-align: center; font-weight: 800;">
                        <td>NORMAL</td><td>FULL PAGE</td>
                    </tr>
                </thead>
                <tbody>
                    <tr style="vertical-align: top">
                        <td><img src="normal.png" /></td><td><img src="fullpage.png" /></td>
                    </tr>
                </tbody>
            </table>
            """,
        )
    )

    playwright_mt.headed = True
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_context(viewport=ViewportSize(width=700, height=800)).new_page()
        page.goto(web_server.url)

        assert ask_confirmation("Is the full page screenshot significantly larger?")
