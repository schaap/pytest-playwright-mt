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
Tests for instantiating Playwright instances from a ``PlaywrightMTFixture``
"""

import re
from pathlib import Path
from threading import Barrier, Thread
from typing import Any, cast

import pytest
from playwright.sync_api import Browser, Playwright, expect
from server import WebServer

from pytest_playwright_mt import ArtifactCollector, BrowserName, PlaywrightMT, PlaywrightMTFixture, RecordingOption
from pytest_playwright_mt.playwright_mt_fixture import BrowserUse


def test_parallel_instances(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Verify that we can instantiate multiple Playwright instances and have them run in parallel.

    This test ensures the parallelism by having them interact with each other via the web server.
    """
    start_barrier = Barrier(2)
    pass_barrier = Barrier(2)
    finish_barrier = Barrier(2)

    # How long it takes to reach each barrier depends on how quickly Playwright goes through the actions. This is
    # affected by the slowmo option, so we'll adjust the timeout for that option: heuristically add the additional time
    # for 3 Playwright actions.
    # The timeout is not critical for the test. It just provides some safety against a hanging test if a barrier is
    # never reached.
    barrier_timeout = 0.5 + (3 * playwright_mt.slowmo / 1000)

    one_or_two = re.compile(r"[12]")

    def thread_one() -> None:
        """
        The first thread running Playwright.

        This thread will be first to visit the counter page again after both threads have made their initial visit.
        """
        with playwright_mt.create_instance() as pw:
            page = pw.launch().new_context().new_page()
            page.goto(f"{web_server.url}counter")
            expect(page.get_by_test_id("counter")).to_have_text(one_or_two)

            # Wait until both browers have navigated to the counter page
            start_barrier.wait(timeout=barrier_timeout)

            page.get_by_role("link", name="Increment again").click()
            expect(page.get_by_test_id("counter")).to_have_text("3")

            # Signal thread_two that the counter page has been retrieved again
            pass_barrier.wait(timeout=barrier_timeout)

    def thread_two() -> None:
        """
        The first thread running Playwright.

        This thread will be second to visit the counter page again after both threads have made their initial visit.
        """
        with playwright_mt.create_instance() as pw:
            page = pw.launch().new_context().new_page()
            page.goto(f"{web_server.url}counter")
            expect(page.get_by_test_id("counter")).to_have_text(one_or_two)

            # Wait until both browers have navigated to the counter page
            start_barrier.wait(timeout=barrier_timeout)

            # Wait for thread_one to visit the counter page again
            pass_barrier.wait(timeout=barrier_timeout)

            page.get_by_role("link", name="Increment again").click()
            expect(page.get_by_test_id("counter")).to_have_text("4")

            # Signal main thread that we're done
            finish_barrier.wait(barrier_timeout)

    # Spin up both threads, they'll do the work for us
    t1 = Thread(target=thread_one)
    t2 = Thread(target=thread_two)
    t1.start()
    t2.start()

    # Wait for the two threads to finish. This will pass three barriers, so just go for thrice the barrier timeout.
    finish_barrier.wait(barrier_timeout * 3)

    # Clean up the threads. That really should just succeed by now.
    for thread in (t1, t2):
        thread.join(0.5)
        assert not thread.is_alive()


def test_multiple_exit_allowed(tmp_path: Path, artifact_collector: ArtifactCollector) -> None:
    """
    Verify that ``PlaywrightMT.__exit__`` may be called multiple times.
    """
    pw = create_pw_mt(tmp_path, artifact_collector)

    # __exit__ without __enter__ is okay
    pw.__exit__(None, None, None)

    # double __exit__ after __enter__ is okay
    with pw:
        pass
    pw.__exit__(None, None, None)


@pytest.mark.parametrize(
    "browser_to_use",
    [
        "chromium",
        "firefox",
        "webkit",
    ],
)
def test_launch_specific_browser(browser_to_use: str, tmp_path: Path, artifact_collector: ArtifactCollector) -> None:
    """
    Verify that an instantiated Playwright can launch a specific browser.
    """
    # Make sure to choose a different default browser than the one that will be launched explicilty
    default_browser = BrowserName.FIREFOX if browser_to_use == BrowserName.CHROMIUM.value else BrowserName.CHROMIUM

    pw = create_pw_mt(tmp_path, artifact_collector, default_browser=default_browser)

    with pw:
        browser = cast(Browser, getattr(pw, browser_to_use)())
        assert browser.browser_type.name == browser_to_use


@pytest.mark.parametrize(
    "browser_to_use",
    list(BrowserName),
)
def test_launch_default_browser(
    browser_to_use: BrowserName, tmp_path: Path, artifact_collector: ArtifactCollector
) -> None:
    """
    Verify that an instantiated Playwright can launch the default browser.
    """
    pw = create_pw_mt(tmp_path, artifact_collector, default_browser=browser_to_use)

    with pw:
        browser = pw.launch()
        assert browser.browser_type.name == browser_to_use.value


def test_direct_access(tmp_path: Path, artifact_collector: ArtifactCollector) -> None:
    """
    Verify that the instantiated Playwright object can be accessed directly, if truly needed.
    """
    pw = create_pw_mt(tmp_path, artifact_collector)

    instance1: object | None = None
    instance2: object | None = None

    with pw:
        instance1 = pw.playwright_instance
        assert isinstance(instance1, Playwright)

    with pw:
        instance2 = pw.playwright_instance
        assert isinstance(instance2, Playwright)

    assert instance1 is not instance2


@pytest.fixture
def artifact_collector() -> ArtifactCollector:
    """A neutered artifact collector."""

    # ruff: ignore[ANN401]  # We need to catch all arguments for correctness
    def do_nothing(*_: Any, **__: Any) -> None:
        """Does nothing."""
        return

    ac = ArtifactCollector()
    ac.secure_artifacts = do_nothing  # type: ignore[method-assign]  # Monkey-patched
    return ac


# ruff: ignore[PLR0913]  # Many arguments makes sense for this test function
def create_pw_mt(
    tmp_path: Path,
    artifact_collector: ArtifactCollector,
    /,
    *,
    name: str = "test",
    default_browser: BrowserName | None = None,
    headed: bool = False,
    browser_channel: str | None = None,
    slowmo: int = 0,
    device: str | None = None,
    tracing: RecordingOption = RecordingOption.OFF,
    video: RecordingOption = RecordingOption.OFF,
    screenshot: RecordingOption = RecordingOption.OFF,
    full_page_screenshot: bool = False,
    additional_browser_context_args: dict[str, Any] | None = None,
    artifact_temporary_storage: Path | None = None,
) -> PlaywrightMT:
    """
    Create a ``PlaywrightMT instance``, filling in defaults for options not passed.

    :param tmp_path: The path provided by the ``tmp_path`` fixture of pytest.
    :param artifact_collector: The artifact collector to use.
    :param name: A name for this playwright instance. This is used as a base name for artifact storage directories.
    :param default_browser: The browser to default to.
    :param headed: Whether to use a headed browser.
    :param browser_channel: The browser channel to use.
    :param slowmo: Have the browser run in slow motion, with a given number of milliseconds between interactions.
    :param device: The device to emulate.
    :param tracing: Whether to enable tracing in the browser.
    :param video: Whether the enable video recording in the browser.
    :param screenshot: Whether to automatically take a screenshot at the end of each browser page's lifetime.
    :param full_page_screenshot: Whether automatic screenshots (see ``screenshot``) will screenshot the entire page.
    :param additional_browser_context_args: Additional arguments to pass to ``Browser.new_context()``. Defaults to
                                            ``{}``.
    :param artifact_temporary_storage: Directory where artifacts will be stored while the browser contexts exist.
                                       Defaults to path pointed to by the ``tmp_path`` fixture.
    """
    return PlaywrightMT(
        artifact_collector=artifact_collector,
        name=name,
        default_browser=default_browser,
        headed=headed,
        browser_channel=browser_channel,
        slowmo=slowmo,
        device=device,
        tracing=tracing,
        video=video,
        screenshot=screenshot,
        full_page_screenshot=full_page_screenshot,
        additional_browser_context_args=dict(additional_browser_context_args or {}),
        artifact_temporary_storage=artifact_temporary_storage if artifact_temporary_storage is not None else tmp_path,
        browser_use=BrowserUse.MIXED,
    )
