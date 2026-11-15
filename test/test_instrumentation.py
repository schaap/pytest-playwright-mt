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
Tests for the instrumentation

Note that the majority of the functionality is indirectly verified by others tests
"""

from enum import Enum
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext
from server import WebServer

from pytest_playwright_mt import ArtifactCollector, BrowserName, PlaywrightMTFixture, RecordingOption, context_name

# ruff: ignore[PLC2701]  # The private import is needed for observation in a test
from pytest_playwright_mt.instrumentation import _BROWSER_CONTEXTS_ATTR as BROWSER_CONTEXTS_ATTR
from pytest_playwright_mt.options import BrowserUse, PlaywrightMTOptions, parse_options


class CloseObject(Enum):
    """Minimum object to close in ``test_artifact_collector_secures_with_implicit_closes``."""

    Page = 0
    """Close the page and all objects above."""

    BrowserContext = 1
    """Close the browser context and all objects above."""

    Browser = 2
    """Close the browser and all objects above."""

    Nothing = 3
    """Do not explicitly close any objects, only ``__exit__`` the ``PlaywrightMT`` instance."""


@pytest.mark.parametrize(("close"), list(CloseObject))
def test_implicit_close_calls(
    pytestconfig: pytest.Config, tmp_path: Path, web_server: WebServer, close: CloseObject
) -> None:
    """
    Verify that objects that are implicitly closed (i.e. no explicit call to their ``close`` method) are still closed
    via our instrumented call.

    This behaviour is observed by requesting automatic screenshots: the screenshot itself needs the instrumented
    ``Page.close`` and artifact securing requires the other objects' instrumented ``close`` calls. If any of those is
    not called, the screenshots won't end up in the right place.
    """
    temp_storage = tmp_path / "temp_storage"

    # Use most plugin options straight from the command line, to be nice to the user
    # We will only overwrite those that deal with artifacts, as we will be observing those.
    plugin_options = parse_options(pytestconfig)

    artifact_collector = ArtifactCollector()
    playwright_mt_fixture = PlaywrightMTFixture(
        default_browser=BrowserName.CHROMIUM,
        browser_use=BrowserUse.STATIC,
        artifact_collector=artifact_collector,
        plugin_options=PlaywrightMTOptions(
            headed=plugin_options.headed,
            browser_channel=plugin_options.browser_channel,
            slowmo=plugin_options.slowmo,
            device=plugin_options.device,
            tracing=RecordingOption.OFF,
            video=RecordingOption.OFF,
            screenshot=RecordingOption.ON,
            full_page_screenshot=False,
        ),
        additional_browser_context_args=None,
        artifact_temporary_storage_root=tmp_path / "temp_storage",
    )

    with playwright_mt_fixture.create_instance() as pw:
        browser = pw.chromium()
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{web_server.url}counter")

        if close is CloseObject.Page:
            page.close()
        if close in {CloseObject.Page, CloseObject.BrowserContext}:
            context.close()
        if close in {CloseObject.Page, CloseObject.BrowserContext, CloseObject.Browser}:
            browser.close()

    temp_storage /= "playwright"
    assert temp_storage.exists()
    assert temp_storage.is_dir()
    assert any(temp_storage.glob("*/*/*.png"))


def test_dedicated_context_close(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Verify that a single page with a dedicated browser context (i.e. one created via ``Browser.new_page``) explicitly
    closes the browser context when the page is closed.
    """

    def contexts(browser: Browser) -> list[BrowserContext]:
        """
        List the registered contexts on an instrumented Browser.

        :param browser: The instrumented browser.
        :returns: The list of browser contexts.
        """
        return getattr(browser, BROWSER_CONTEXTS_ATTR, [])

    playwright_mt.video = RecordingOption.ON
    with playwright_mt.create_instance() as pw:
        # Create the page via new_page, observe that the context is also created
        browser = pw.launch()
        assert len(contexts(browser)) == 0
        page = browser.new_page()
        assert len(contexts(browser)) == 1

        # Do stuff with the page, then close it
        page.goto(f"{web_server.url}counter")

        # Observe that the page has been closed by observing that the video file is moved after the close
        videos_path = pw.artifact_temporary_storage / context_name(contexts(browser)[0]) / "videos"
        assert not any(videos_path.glob("*.webm"))
        page.close()
        assert any(videos_path.glob("*.webm"))

        # Do all that again with a regular context/page combination to verify that it is indeed the context close that
        # moves the video file, not the page close
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{web_server.url}counter")

        videos_path = pw.artifact_temporary_storage / context_name(context) / "videos"
        assert not any(videos_path.glob("*.webm"))
        page.close()
        assert not any(videos_path.glob("*.webm"))
        context.close()
        assert any(videos_path.glob("*.webm"))
