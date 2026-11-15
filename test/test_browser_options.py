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
Tests for the different browser options.

Only the ones we actually do something with are tested. The majority of options - even the ones we declare explicitly
for the sake of things like autocompletion in IDEs - are simple pass-through options that oftentimes can't even reliably
be verified. We simply rely on Playwright itself to correctly parse its own options.

Note that browser_channel is not explicitly tested, as it requires additional downloads and usually pulls in proprietary
parts. These should not be part of the test suite of a completely open plugin. The correctness of the option's
implementation is assumed because it's handled exactly the same as other options which *are* tested.

The tests in this module are excessively parametrized on which browsers are used. This is done to exercise all our
code paths to instantiate browsers. Most tests have superfluous, effectively duplicate calls when the test run is
parametrized for multiple browsers. Only the interactive tests do not have this, at the expense of more code.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, cast

import pytest
from helpers import ask_confirmation
from playwright.sync_api import Browser, Download, ViewportSize
from server import WebServer

from pytest_playwright_mt import PlaywrightMT, PlaywrightMTFixture

SLOWMO_TEST_DELAY: Final[int] = 250
"""Delay (ms) between Playwright operation used when testing the slowmo options."""

ALL_BROWSER_FUNCS: Final[list[Callable[..., Browser]]] = [
    PlaywrightMT.chromium,
    PlaywrightMT.firefox,
    PlaywrightMT.webkit,
    PlaywrightMT.launch,
]
"""All the browser instantiation methods of ``PlaywrightMT``, ready for use in a parametrization marker."""


@pytest.mark.usefixtures("interactive")
def test_headed_dynamic(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Test that a headed instance can be spawned, using ``launch``.
    """
    playwright_mt.headed = True
    assert perform_headed_test("Headed test (dynamic)", playwright_mt, PlaywrightMT.launch, web_server)


@pytest.mark.parametrize(("browser_func"), [PlaywrightMT.chromium, PlaywrightMT.firefox, PlaywrightMT.webkit])
@pytest.mark.static_browser
@pytest.mark.usefixtures("interactive")
def test_headed_static(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that a headed instance can be spawned, using specific browser instantiation functions.
    """
    playwright_mt.headed = True
    assert perform_headed_test("Headed test (static)", playwright_mt, browser_func, web_server)


@pytest.mark.usefixtures("interactive")
def test_headless_dynamic(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Test that a headless instance can be spawned, using ``launch``.
    """
    playwright_mt.headed = False
    assert not perform_headed_test("Headless test (dynamic)", playwright_mt, PlaywrightMT.launch, web_server)


@pytest.mark.parametrize(("browser_func"), [PlaywrightMT.chromium, PlaywrightMT.firefox, PlaywrightMT.webkit])
@pytest.mark.static_browser
@pytest.mark.usefixtures("interactive")
def test_headless_static(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that a headless instance can be spawned, using specific browser instantiation functions.
    """
    playwright_mt.headed = False
    assert not perform_headed_test("Headless test (static)", playwright_mt, browser_func, web_server)


@pytest.mark.usefixtures("interactive")
def test_headed_override_dynamic(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Test that a browser can be spawned headed or headless despite the default being different, using ``launch``.
    """
    playwright_mt.headed = True
    assert not perform_headed_test(
        "Headed override test (dynamic)", playwright_mt, PlaywrightMT.launch, web_server, headless=True
    )


@pytest.mark.parametrize(("browser_func"), [PlaywrightMT.chromium, PlaywrightMT.firefox, PlaywrightMT.webkit])
@pytest.mark.static_browser
@pytest.mark.usefixtures("interactive")
def test_headed_override_static(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that a browser can be spawned headed or headless despite the default being different, using specific browser
    instantiation functions.
    """
    playwright_mt.headed = True
    assert not perform_headed_test(
        "Headed override test (static)", playwright_mt, browser_func, web_server, headless=True
    )


def perform_headed_test(
    header: str,
    playwright_mt: PlaywrightMTFixture,
    browser_func: Callable[..., Browser],
    web_server: WebServer,
    **browser_launch_args: bool,
) -> bool:
    """
    Perform a test for the ``--headed`` option.

    This is a helper that implements the common, repetitive task of the headless/headed tests.

    :param header: The header for the test page the user might/should see.
    :param playwright_mt: The plugin's fixture class for the test.
    :param browser_func: The method of ``PlaywightMT`` to call to instantiate the browser.
    :param web_server: The web server that is available in this test.
    :param browser_launch_args: Any additional keyword arguments are passed to ``browser_func``.
    :returns: Whether the user indicated that they saw a browser appear.
    """
    (web_server.pages_dir / "index.html").write_text(
        web_server.basic_html(header, "<p>You should answer Yes if you can read this.</p>")
    )
    with playwright_mt.create_instance() as pw:
        # Instantiate the browser using the passed function and arguments. browser_func is a method of PlaywrightMT, so
        # we pass pw as the first argument (self).
        browser = browser_func(pw, **browser_launch_args)

        browser.new_context().new_page().goto(web_server.url)
        return ask_confirmation(
            f"Do you see a {browser.browser_type.name.capitalize()} browser that popped up for this test?"
        )


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
def test_slowmo_off(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that running without slowmo turned on does not slow things down.
    """
    orig_slowmo = playwright_mt.slowmo
    # orig_slowmo is kept and waited for before and after the actual tests, to provide some form of feedback to the
    # user, if they requested so (especially with something like --headed --slowmo 500)

    cycles = 5
    playwright_mt.slowmo = 0
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context().new_page()
        page.wait_for_timeout(orig_slowmo)

        start = datetime.now(tz=UTC)
        page.goto(f"{web_server.url}counter")
        for _ in range(cycles - 1):
            page.get_by_role("link", name="Increment again").click()

        # No slowmo used, so this must have been fast
        assert datetime.now(tz=UTC) - start < timedelta(milliseconds=(SLOWMO_TEST_DELAY * cycles * 0.8))

        page.wait_for_timeout(orig_slowmo)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
def test_slowmo(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that running with slowmo turned on slows things down.
    """
    orig_slowmo = playwright_mt.slowmo
    # orig_slowmo is kept and waited for before and after the actual tests, to provide some form of feedback to the
    # user, if they requested so (especially with something like --headed --slowmo 500)

    cycles = 5
    playwright_mt.slowmo = SLOWMO_TEST_DELAY
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context().new_page()
        page.wait_for_timeout(orig_slowmo)

        start = datetime.now(tz=UTC)
        page.goto(f"{web_server.url}counter")
        for _ in range(cycles - 1):
            page.get_by_role("link", name="Increment again").click()

        # Slowmo used, so this must have been slow
        assert datetime.now(tz=UTC) - start > timedelta(milliseconds=(SLOWMO_TEST_DELAY * cycles * 0.8))

        page.wait_for_timeout(orig_slowmo)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
def test_slowmo_override(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that slowmo can be turned on explicitly despite being turned off by default.
    """
    orig_slowmo = playwright_mt.slowmo
    # orig_slowmo is kept and waited for before and after the actual tests, to provide some form of feedback to the
    # user, if they requested so (especially with something like --headed --slowmo 500)

    cycles = 5
    playwright_mt.slowmo = SLOWMO_TEST_DELAY
    with playwright_mt.create_instance() as pw:
        browser = browser_func(pw, slow_mo=1)  # override slowmo to be fast again
        page = browser.new_context().new_page()
        page.wait_for_timeout(orig_slowmo)

        start = datetime.now(tz=UTC)
        page.goto(f"{web_server.url}counter")
        for _ in range(cycles - 1):
            page.get_by_role("link", name="Increment again").click()

        # No slowmo used, so this must have been fast
        assert datetime.now(tz=UTC) - start < timedelta(milliseconds=(SLOWMO_TEST_DELAY * cycles * 0.8))

        page.wait_for_timeout(orig_slowmo)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
@pytest.mark.parametrize(
    ("device_name", "expected_width", "expected_height"),
    [
        ("Galaxy S III", 360, 640),
        ("Galaxy S9+", 320, 658),
    ],
)
# ruff: ignore[PLR0913]  # Quite some parametrization and fixtures needed
def test_device(
    *,
    device_name: str,
    expected_width: int,
    expected_height: int,
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    browser_func: Callable[..., Browser],
) -> None:
    """
    Test that the device emulation can be set correctly via the fixture class.

    This test works by emulating devices with different viewports, so it can rely on the viewport of the browser for
    verification. Test data were taken from Playwright's own device descriptors, retrieved 2026-11-01:
    ``https://github.com/microsoft/playwright/blob/main/packages/isomorphic/deviceDescriptorsSource.json``
    """
    (web_server.pages_dir / "index.html").write_text(
        web_server.basic_html("Device emulation", f"<p>Emulated device: {device_name}</p>")
    )

    playwright_mt.device = device_name
    with playwright_mt.create_instance() as pw:
        # First verify the expected width/height against the current Playwright emulation database, so we can detect
        # when our test data becomes outdated
        devices = cast(dict[str, dict[str, Any]], pw.playwright_instance.devices)

        arguments = devices[device_name]
        assert "viewport" in arguments
        assert arguments["viewport"]["width"] == expected_width
        assert arguments["viewport"]["height"] == expected_height

        # Verify that the emulation works in the browser, by observing the viewport it gives us
        page = browser_func(pw).new_context().new_page()
        page.goto(web_server.url)

        assert page.viewport_size == ViewportSize(width=expected_width, height=expected_height)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
@pytest.mark.browser_context_args(viewport=ViewportSize(width=400, height=800))
def test_additional_browser_context_args_1(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that additional browser context arguments are passed on from the pytest markers.

    There are two versions of this test, to prevent success by accidentally matching the default viewport size.
    """
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context().new_page()
        page.goto(f"{web_server.url}counter")

        assert page.viewport_size == ViewportSize(width=400, height=800)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
@pytest.mark.browser_context_args(viewport=ViewportSize(width=800, height=450))
def test_additional_browser_context_args_2(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that additional browser context arguments are passed on from the pytest markers.

    There are two versions of this test, to prevent success by accidentally matching the default viewport size.
    """
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context().new_page()
        page.goto(f"{web_server.url}counter")

        assert page.viewport_size == ViewportSize(width=800, height=450)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
@pytest.mark.browser_context_args(viewport=ViewportSize(width=800, height=450))
def test_additional_browser_context_args_override(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that additional browser context arguments can be overridden.
    """
    playwright_mt.additional_browser_context_args = {"viewport": ViewportSize(width=250, height=670)}
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context().new_page()
        page.goto(f"{web_server.url}counter")

        assert page.viewport_size == ViewportSize(width=250, height=670)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
@pytest.mark.browser_context_args(viewport=ViewportSize(width=800, height=450))
def test_additional_browser_context_args_direct_override(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that additional browser context arguments can be overridden when creating the browser context.

    This validates the order in which arguments from different sources are applied.
    """
    with playwright_mt.create_instance() as pw:
        page = browser_func(pw).new_context(viewport=ViewportSize(width=250, height=670)).new_page()
        page.goto(f"{web_server.url}counter")

        assert page.viewport_size == ViewportSize(width=250, height=670)


@pytest.mark.parametrize(("browser_func"), ALL_BROWSER_FUNCS)
@pytest.mark.mixed_browser
def test_download_path(
    playwright_mt: PlaywrightMTFixture, web_server: WebServer, tmp_path: Path, browser_func: Callable[..., Browser]
) -> None:
    """
    Test that the download path can be set when launching a browser.
    """
    download_path = tmp_path / "downloads"

    (web_server.pages_dir / "download.bin").write_bytes(b"\00This is a test file\r\n" * 1024)
    (web_server.pages_dir / "index.html").write_text(
        web_server.basic_html("Download a file", '<p>Download here: <a href="download.bin" id="clicky">clicky</a></p>')
    )

    with playwright_mt.create_instance() as pw:
        page = browser_func(pw, downloads_path=download_path).new_context().new_page()
        page.goto(web_server.url)
        download: Download | None = None
        with page.expect_download() as download_info:
            page.get_by_role("link", name="clicky").click()
            download = download_info.value
        assert download is not None
        assert download.path().parent == download_path, (
            f"Expected file to be downloaded to {download_path}, but it was downloaded as {download.path()}. This "
            "downloaded file may need manual clearing from your system."
        )
