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
Primary pytest fixture for Playwright MT

This module provides the ``playwright_mt`` fixture and the class it yields, ``PlaywrightMTFixture``. It is also the
primary entry point for the module, collecting all the hooks and fixtures from the other modules to fully set the plugin
up.
"""

from __future__ import annotations

import shutil
import warnings
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

import pytest

from pytest_playwright_mt.artifact_collector import (
    artifact_collector,  # ruff: ignore[F401]  # Fixture
    pytest_runtest_makereport,  # ruff: ignore[F401]  # pytest hook, needs importing to make sure it activates
)
from pytest_playwright_mt.artifact_collector import (
    # ruff: ignore[F401]  # pytest hook, needs importing to make sure it activates
    pytest_addoption as pytest_addoption_artifact_collector,
)
from pytest_playwright_mt.artifact_collector import (
    # ruff: ignore[F401]  # pytest hook, needs importing to make sure it activates
    pytest_configure as pytest_config_artifact_collector,
)
from pytest_playwright_mt.options import (
    BrowserName,
    BrowserUse,
    PlaywrightMTOptions,
    additional_browser_context_arguments,
    declared_browser_use,
    only_browser,
    parse_options,
    parse_requested_browsers,
    pytest_addoption,  # ruff: ignore[F401]  # pytest hook, needs importing to make sure it activates
    skip_browsers,
)
from pytest_playwright_mt.options import (
    # ruff: ignore[F401]  # pytest hook, needs importing to make sure it activates
    pytest_configure as pytest_configure_options,
)
from pytest_playwright_mt.playwright_mt import PlaywrightMT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from os import PathLike
    from pathlib import Path

    from pytest_playwright_mt.artifact_collector import ArtifactCollector


class PlaywrightMTFixture:
    """
    Access Playwright from multi-threaded contexts in a pytest test.

    This is the primary access point from which (not thread-safe) Playwright instances can be spawned, each wrapped in
    a ``PlaywrightMT`` instance.

    The members of this class can be updated. Changes will not affect previously created ``PlaywrightMT`` instances.
    This is not the most common usage pattern, but most usage scenarios will not want to programmatically change any of
    the options. Test developers are encouraged, rather, to rely on the values provided by the user calling pytest. If
    values do need to be set programmatically, it is expected that those will be the same for all ``PlaywrightMT``
    instances. Requiring passing of the argument to ``create_instance`` for each instance is mainly cumbersome.
    """

    # ruff: ignore[PLR0913]  # This object is complex, needs a lot of input data
    def __init__(
        self,
        *,
        default_browser: BrowserName,
        browser_use: BrowserUse,
        artifact_collector: ArtifactCollector,  # ruff: ignore[F811]  # clashes with the imported fixture
        plugin_options: PlaywrightMTOptions,
        artifact_temporary_storage_root: Path,
        additional_browser_context_args: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a ``PlaywrightMTFixture``. It is strongly encouraged to use the ``playwright_mt`` fixture to obtain
        an instance of ``PlaywrightMTFixture``, instead.

        :param default_browser: The default browser to use.
        :param browser_use: The way the test function has declared it will create browsers.
        :param artifact_collector: The ``ArtifactCollector`` instance to use for artifacts created by browsers that
                                   spring from this fixture.
        :param plugin_options: The plugin's options as parsed from the pytest configuration.
        :param artifact_temporary_storage_root: Root folder for temporary storage of artifacts.
        :param additional_browser_context_args: Additional arguments to pass to ``Browser.new_context``.
        """
        self.default_browser = default_browser
        """The browser to use by default."""

        self.headed = plugin_options.headed
        """Whether to use headed browsers."""

        self.browser_channel = plugin_options.browser_channel
        """The browser channel to use. ``None`` for no specific channel."""

        self.slowmo = plugin_options.slowmo
        """Have the browser run in slow motion, with a given number of milliseconds between interactions."""

        self.device = plugin_options.device
        """The device to emulate. ``None`` for no device emulation."""

        self.tracing = plugin_options.tracing
        """Whether to enable tracing in the browser."""

        self.video = plugin_options.video
        """Whether to enable video recording in the browser."""

        self.screenshot = plugin_options.screenshot
        """Whether to automatically take a screenshot at the end of each browser page's lifetime."""

        self.full_page_screenshot = plugin_options.full_page_screenshot
        """
        Whether automatic screenshots (see ``screenshot``) will screenshot the entire page instead of only the browser's
        viewport.
        """

        self.additional_browser_context_args: dict[str, Any] = additional_browser_context_args or {}
        """Additional arguments to pass to ``Browser.new_context``."""

        self.artifact_temporary_storage_root: Path = artifact_temporary_storage_root
        """
        Root folder for temporary storage of artifacts. The caller is responsible for cleaning up the temporary storage.
        By default, this plugin's fixture will use a temporary directory provided by pytest's ``tmp_path_factory``.
        """

        self.artifact_move_func: Callable[[Path, Path], PathLike[str] | str | None] | None = None
        """
        The function to use for moving artifacts in the child ``ArtifactCollector`` instances used for Playwright
        instances. This has the same semantics as ``shutil.move``. Leave this as ``None`` to inherit the function from
        ``self.artifact_collector``.

        See ``ArtifactCollector.default_artifact_move_func`` for more information on additional override options.
        """

        self._artifact_collector: ArtifactCollector = artifact_collector
        self._browser_use = browser_use

    @property
    def artifact_collector(self) -> ArtifactCollector:
        """
        The artifcat collector to submit artifacts to for storage.

        Test developers that need to secure artifacts can rely on this, as well. Register additional artifacts using
        ``ArtifactCollector.add_artifact`` and they will be secured just like the artifacts created by the Playwright
        browsers would.
        """
        return self._artifact_collector

    @contextmanager
    def create_instance(self, name: str = "playwright") -> Generator[PlaywrightMT, None, None]:
        """
        Initialize a Playwright instance for use (exclusively!) in the current thread.

        This will instantiate a new ``PlayrightMT`` instance with its attributes set to the current values of the
        attributes present in this object.

        Basic usage: ::

            def my_test(playwright_mt: PlayrightMTFixture) -> None:
                with playwright_mt.create_instance() as pw:
                    browser = pw.launch()  # This returns a Playwright Browser object
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto("https://your.website.test/")

        :param name: If not empty, gives a name to the Playwright instance. This is used as a base name for artifact
                     storage.
        """
        with PlaywrightMT(
            name=name,
            default_browser=self.default_browser,
            headed=self.headed,
            browser_channel=self.browser_channel,
            slowmo=self.slowmo,
            device=self.device,
            tracing=self.tracing,
            video=self.video,
            screenshot=self.screenshot,
            full_page_screenshot=self.full_page_screenshot,
            additional_browser_context_args=self.additional_browser_context_args,
            artifact_temporary_storage=self.artifact_temporary_storage_root / name,
            artifact_collector=self._artifact_collector.create_child_collector(
                artifact_move_func=self.artifact_move_func
            ),
            browser_use=self._browser_use,
        ) as pw:
            yield pw


@pytest.fixture
def playwright_mt(
    pytestconfig: pytest.Config,
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
    artifact_collector: ArtifactCollector,  # ruff: ignore[F811]  # imported fixture
    browser_name: BrowserName,
) -> PlaywrightMTFixture:
    """
    Activate the Playwright pytest plugin for multi-threaded environments. Request this fixture to get an object from
    which Playwright instances can be created, each of which will be single threaded.

    Usage: ::

        def test_my_stuff(playwright_mt: PlaywrightMTFixture) -> None:
            def thread1() -> None:
                with playwright_mt.create_instance() as pw:
                    browser = pw.launch()  # This returns a Playwright Browser object
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto("https://your.website.test/chat")
                    # Start a chat conversation with thread 2 here

            def thread2() -> None:
                with playwright_mt.create_instance() as pw:
                    browser = pw.launch()  # This returns a Playwright Browser object
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto("https://your.website.test/chat")
                    # Start a chat conversation with thread 1 here

            # Launch two separate threads in parallel, one running thread1, one running thread2. The two threads can
            # communicate directly as normal, and their Playwright browsers could communicate via a website, for example
            # to have a chat conversation with each other, sending messages and waiting upon each other as they go. The
            # Playwright instances in the two threads are entirely independent. They are linked to (and run inside)
            # their respective threads.
            #
            # It is up to the caller to make sure that the threads have finished, or at least the Playwright instances
            # created through ``playwright_mt.create_instance()`` have been cleaned up, before the test is left.
            # Failure to do so (for example when an exception is raised or an assert somewhere fails) may cause
            # artifacts like screenshots, videos and traces to not be stored.

    :param pytestconfig: The pytest configuration object.
    :param tmp_path_factory: A temporary path factory provided by pytest.
    :param request: The pytest request object, providing access to data about the current test.
    :param artifact_collector: The artifact collector fixture, which provides the top level artifact collector to use.
    :param browser_name: The name of the browser for which the current test call has been parametrized.
    :yields: The ``PlaywrightMTFixture`` instance from which Playwright instances can be created.
    """
    plugin_options = parse_options(pytestconfig)

    # Extract the request's node, which is untyped for the generic case, but *will* be a pytest.Node in this context.
    # That type, however, is kept entirely internal to pytest. At the same time it's an abstract base to exactly two
    # subtypes, which *are* externally visible: Collector and Item.
    request_node = cast(pytest.Collector | pytest.Item, request.node)

    browser_use = declared_browser_use(request_node) if isinstance(request_node, pytest.Item) else BrowserUse.DYNAMIC

    artifact_tmp_path = tmp_path_factory.mktemp("playwright_artifacts_tmp")
    try:
        instance = PlaywrightMTFixture(
            default_browser=browser_name,
            browser_use=browser_use,
            artifact_collector=artifact_collector,
            plugin_options=plugin_options,
            additional_browser_context_args=additional_browser_context_arguments(request),
            artifact_temporary_storage_root=artifact_tmp_path,
        )
    finally:
        shutil.rmtree(artifact_tmp_path)

    return instance


@pytest.fixture(scope="session")
def browser_name(pytestconfig: pytest.Config, request: pytest.FixtureRequest) -> BrowserName:
    """
    The name of the currently selected browser.

    This fixture is mostly a placeholder: your test will usually obtain ``browser_name`` by being parametrized on it.
    The fixture still exists, so you can obtain that parametrized version.

    Usage: ::

        def test_fail_if_not_firefox(browser_name: BrowserName) -> None:
            assert browser_name is BrowserName.FIREFOX  # Silly, but it demonstrates the use.
    """
    if hasattr(request, "param"):
        return cast(BrowserName, request.param)

    # When using unittest.TestCase it won't use pytest_generate_tests
    # For that we still try to give the user a slightly less feature-rich experience
    browser_names = parse_requested_browsers(pytestconfig)
    if len(browser_names) == 0:
        return BrowserName.CHROMIUM
    if len(browser_names) == 1:
        return browser_names[0]
    warnings.warn("When using unittest.TestCase specifying multiple browsers is not supported", stacklevel=2)
    return browser_names[0]


# Fixtures defined by this plugin that (transitively) require a browser and therefore "browser_name". When one of them
# is requested through a user override of e.g. the "page" fixture, some pytest versions drop "browser_name" from the
# fixture closure, which would silently disable running the test against multiple browsers.
# https://github.com/microsoft/playwright-pytest/issues/172
_BROWSER_FIXTURES = ("playwright_mt",)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """
    pytest hook

    To allow running tests on multiple browsers, those tests that require it will be parametrized for the requested
    browser, via the ``browser_name`` fixture. This parametrization is dynamic and is performed in this hook, which runs
    during test collection.
    """
    # Append the browser_name fixture name to the fixtures if it's not already there but will (indirectly) be requested
    if browser_name.__name__ not in metafunc.fixturenames and any(
        name in metafunc.fixturenames for name in _BROWSER_FIXTURES
    ):
        metafunc.fixturenames.append(browser_name.__name__)

    # If the browser_name fixture is requested, parametrize the function for the requested browsers, but only if the
    # test function has not declared itself independent of that parametrization.
    if browser_name.__name__ in metafunc.fixturenames:
        if declared_browser_use(metafunc.definition) is BrowserUse.STATIC:
            # Tests marked with pytest.mark.static_browser still need to be parametrized for browser_name, just to make
            # sure they don't fall into the unittest.TestCase fallback for the browser_name fixture. We'll just
            # 'parametrize' them with only the default.
            browsers = [BrowserName.CHROMIUM]
        else:
            browsers = [
                BrowserName(browser) for browser in metafunc.config.option.browser or [BrowserName.CHROMIUM.value]
            ]
        metafunc.parametrize(browser_name.__name__, browsers, scope="session", indirect=True)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """
    pytest hook

    This hook is run during the setup phase for each test. Here we can decide to skip a test if it is about to run for a
    browser that it has declared it doesn't want to run on (via pytest.mark.only_browser or pytest.mark.skip_browser).
    """
    # Only process parametrized test calls. Note that, even if item is a Function, the callspec member does not even
    # *exist* if the call is not parametrized.
    if not isinstance(item, pytest.Function):
        return
    if not hasattr(item, "callspec"):
        return

    browser = cast(BrowserName | None, item.callspec.params.get(browser_name.__name__))
    if not browser:
        return

    restrict_browser = only_browser(item)
    if restrict_browser is not None and browser != restrict_browser:
        pytest.skip(f"Skipped for {browser}")

    if browser in skip_browsers(item):
        pytest.skip(f"Skipped for {browser}")
