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
pytest command line options and markers for the plugin
"""

from enum import Enum
from typing import Any, Final, NamedTuple, cast

import pytest

# The names of the original pytest plugin for Playwright. The two (three?) plugins are presumably mutually exclusive.
_PW_ASYNC_CANONICAL_NAME: Final[str] = "pytest_playwright_asyncio.pytest_playwright"
_PW_SYNC_CANONICAL_NAME: Final[str] = "pytest_playwright.pytest_playwright"

# The names of all the command line options
_BROWSER_OPTION: Final[str] = "--browser"
_HEADED_OPTION: Final[str] = "--headed"
_BROWSER_CHANNEL_OPTION: Final[str] = "--browser-channel"
_SLOWMO_OPTION: Final[str] = "--slowmo"
_DEVICE_OPTION: Final[str] = "--device"
_TRACING_OPTION: Final[str] = "--tracing"
_VIDEO_OPTION: Final[str] = "--video"
_SCREENSHOT_OPTION: Final[str] = "--screenshot"
_FULLPAGE_SCREENSHOT_OPTION: Final[str] = "--full-page-screenshot"

# The names of all the markers related to the options
_BROWSER_CONTEXT_ARG_MARKER: Final[str] = "browser_context_args"
_ONLY_BROWSER_MARKER: Final[str] = "only_browser"
_SKIP_BROWSER_MARKER: Final[str] = "skip_browser"
_STATIC_BROWSER_MARKER: Final[str] = "static_browser"
_MIXED_BROWSER_MARKER: Final[str] = "mixed_browser"


class BrowserName(Enum):
    """Browsers supported by Playwright."""

    CHROMIUM = "chromium"
    """Chromium. The browser channel can be used to target propietary versions such as Chrome or Edge."""

    FIREFOX = "firefox"
    """Firefox, the open source browser developed by Mozilla."""

    WEBKIT = "webkit"
    """Webkit, the underlying engine of, among others, Apple's Safari browser."""


class RecordingOption(Enum):
    """Options for recording functionality, such as tracing, video capture and automatic screenshots."""

    OFF = "off"
    """Recording function is disabled."""

    ON = "on"
    """Recording function is always enabled."""

    RETAIN_ON_FAILURE = "retain-on-failure"
    """Recording function is enabled, but results will only be retained on test failure."""


class BrowserUse(Enum):
    """How a test has declared that it will create browsers."""

    DYNAMIC = 0
    """No declaration given, only dynamic browsers (``launch``) allowed."""

    STATIC = 1
    """The test has declared it will only use static browsers (no ``launch`` allowed)."""

    MIXED = 2
    """The test has declared it will mix and match browsers. Everything is allowed."""


class PlaywrightMTOptions(NamedTuple):
    """A set of parsed options for this plugin."""

    headed: bool
    """Whether to use a headed browser."""

    browser_channel: str | None
    """The browser channel to use. ``None`` for no specific channel."""

    slowmo: int
    """Have the browser run in slow motion, with a given number of milliseconds between interactions."""

    device: str | None
    """The device to emulate. ``None`` for no device emulation."""

    tracing: RecordingOption
    """Whether to enable tracing in the browser."""

    video: RecordingOption
    """Whether to enable video recording in the browser."""

    screenshot: RecordingOption
    """Whether to automatically take a screenshot at the end of each browser page's lifetime."""

    full_page_screenshot: bool
    """
    Whether automatic screenshots (see ``screenshot``) will screenshot the entire page instead of only the viewport.
    """


def _check_incompatibility(pluginmanager: pytest.PytestPluginManager) -> None:
    """
    Check for incompatible plugins.

    :param pluginmanager: The pytest plugin manager.
    :raises RuntimeError: If pytest-playwright (or its asynchronous cousin) has been detected.
    """
    # NOTE: This method's functionality is based on pytest_playwright and its asynchronous cousin, but in preliminary
    # testing it did not work. In fact, the original functionality that should warn the user to only use the sync or the
    # async version also seemed to fail.

    # Check for incompatible plugins
    if pluginmanager.has_plugin(_PW_ASYNC_CANONICAL_NAME) or pluginmanager.has_plugin(_PW_SYNC_CANONICAL_NAME):
        raise RuntimeError(
            "Please do not use pytest-playwright or pytest-playwright-asyncio when using pytest-playwright-mt."
        )

    # Check for incompatible plugins by common name
    common_name_plugin_async = pluginmanager.get_plugin("playwright-asyncio")
    common_name_plugin_sync = pluginmanager.get_plugin("playwright")
    if (
        common_name_plugin_async is not None
        and pluginmanager.get_canonical_name(common_name_plugin_async) == _PW_ASYNC_CANONICAL_NAME
    ) or (
        common_name_plugin_sync is not None
        and pluginmanager.get_canonical_name(common_name_plugin_sync) == _PW_SYNC_CANONICAL_NAME
    ):
        raise RuntimeError(
            "Please do not use pytest-playwright or pytest-playwright-asyncio when using pytest-playwright-mt."
        )


def add_options_to_parser(group: pytest.OptionGroup) -> None:
    """
    Add all the options for this plugin to an option group.

    :param group: The group to add all the options to.
    """
    group.addoption(
        _BROWSER_OPTION,
        action="append",
        default=[],
        help="Browser engine to use for tests.",
        choices=[browser.value for browser in BrowserName],
    )
    group.addoption(
        _HEADED_OPTION,
        action="store_true",
        default=False,
        help="Run tests in headed mode.",
    )
    group.addoption(
        _BROWSER_CHANNEL_OPTION,
        action="store",
        default=None,
        help="Browser channel to be used.",
    )
    group.addoption(
        _SLOWMO_OPTION,
        default=0,
        type=int,
        help="Run tests with a delay between each Playwright action. Value in milliseconds (0 for none).",
    )
    group.addoption(
        _DEVICE_OPTION,
        default=None,
        action="store",
        help="Device to be emulated.",
    )

    # Note: no support, yet, for API request tracing (requires advanced bookkeeping and internal knowledge)
    group.addoption(
        _TRACING_OPTION,
        default=RecordingOption.OFF,
        type=RecordingOption,
        help="Whether to record a trace for each test.",
    )

    group.addoption(
        _VIDEO_OPTION,
        default=RecordingOption.OFF,
        type=RecordingOption,
        help="Whether to record video for each test.",
    )

    group.addoption(
        _SCREENSHOT_OPTION,
        default=RecordingOption.OFF,
        type=RecordingOption,
        help="Whether to automatically take a screenshot at the end of each browser page's lifetime.",
    )
    group.addoption(
        _FULLPAGE_SCREENSHOT_OPTION,
        default=False,
        action="store_true",
        help=(
            "Whether automatic screenshots (--screenshot) will screenshot the entire page instead of only the browser "
            "viewport."
        ),
    )


def pytest_addoption(parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager) -> None:
    """
    pytest hook

    Add Playwright specific command line options for pytest.
    """
    _check_incompatibility(pluginmanager)

    group = parser.getgroup("playwright-mt", "Playwright for Multi-Threaded Environments")

    add_options_to_parser(group)


def parse_options(pytestconfig: pytest.Config) -> PlaywrightMTOptions:
    """
    Read all the plugin's options from a pytest configuration.

    :param pytestconfig: The pytest configuration to read the options from.
    :returns: This plugin's options, with defaults already filled in.
    """
    return PlaywrightMTOptions(
        headed=cast(bool | None, pytestconfig.getoption(_HEADED_OPTION)) or False,
        browser_channel=cast(str | None, pytestconfig.getoption(_BROWSER_CHANNEL_OPTION)) or None,
        slowmo=cast(int | None, pytestconfig.getoption(_SLOWMO_OPTION)) or 0,
        device=cast(str | None, pytestconfig.getoption(_DEVICE_OPTION)) or None,
        tracing=cast(RecordingOption | None, pytestconfig.getoption(_TRACING_OPTION)) or RecordingOption.OFF,
        video=cast(RecordingOption | None, pytestconfig.getoption(_VIDEO_OPTION)) or RecordingOption.OFF,
        screenshot=cast(RecordingOption | None, pytestconfig.getoption(_SCREENSHOT_OPTION)) or RecordingOption.OFF,
        full_page_screenshot=cast(bool | None, pytestconfig.getoption(_FULLPAGE_SCREENSHOT_OPTION)) or False,
    )


def parse_requested_browsers(pytestconfig: pytest.Config) -> list[BrowserName]:
    """
    Read which browsers were requested in the pytest configuration.

    :param pytestconfig: The pytest configuration to read the browsers from.
    :returns: The list of explicitly requested browsers. This may be empty.
    """
    browser_names = cast(list[str], pytestconfig.getoption(_BROWSER_OPTION, []))
    return [BrowserName(name) for name in set(browser_names)]


@pytest.hookimpl(specname="pytest_configure")
def pytest_configure(config: pytest.Config) -> None:
    """
    pytest hook

    During this hook configuration can be added. We add the option-related markers defined by this plugin.
    """
    config.addinivalue_line(
        "markers", f"{_SKIP_BROWSER_MARKER}({BrowserName.__name__}): mark test to be skipped on a specific browser."
    )
    config.addinivalue_line(
        "markers", f"{_ONLY_BROWSER_MARKER}({BrowserName.__name__}): mark test to run only on a specific browser."
    )
    config.addinivalue_line(
        "markers",
        f"{_STATIC_BROWSER_MARKER}: mark test to not use dynamic browser selection. The test will not be "
        f"parametrized for {_BROWSER_OPTION} selections. You may still see a parametrization show up, listing the "
        "default browser: your test may still be parametrized for a selected browser with this marker, but it will "
        "always be set to just the one default value. Your test will not run multiple times even if multiple browsers "
        "have been selected for testing.",
    )
    config.addinivalue_line(
        "markers",
        f"{_MIXED_BROWSER_MARKER}: mark test to use mixed browser selection. Your test will be parametrized for the "
        f"{_BROWSER_OPTION} selections as usual, but you are allowed to call on the specific browser instantiation "
        "methods, as well.",
    )

    config.addinivalue_line(
        "markers",
        f"{_BROWSER_CONTEXT_ARG_MARKER}(**kwargs): provide additional arguments to browser.new_context().",
    )


def _request_node(request: pytest.FixtureRequest) -> pytest.Collector | pytest.Item:
    """
    Extract the node of a request. This simply applies typing to ``request.node``.

    :param request: The request to retrieve the node from.
    :returns: The value of ``request.node``, but typed.
    """
    # Extract the request's node, which is untyped for the generic case, but *will* be a pytest.Node in this context.
    # That type, however, is kept entirely internal to pytest. At the same time it's an abstract base to exactly two
    # subtypes, which *are* externally visible: Collector and Item.
    return cast(pytest.Collector | pytest.Item, request.node)


def additional_browser_context_arguments(request: pytest.FixtureRequest) -> dict[str, Any]:
    """
    Obtain the additional arguments for creating browser contexts, as specified in a pytest test's markers.

    :param request: The ``FixtureRequest`` for the test being inspected.
    :returns: The dictionary of additional keyword-arguments to use when creating browser contexts.
    """
    request_node = _request_node(request)

    # Collect additional browser context arguments from the markers on the current pytest test
    additional_browser_context_args: dict[str, Any] = {}
    for marker in request_node.iter_markers(_BROWSER_CONTEXT_ARG_MARKER):
        if len(marker.args) > 0:
            raise ValueError(f"Only keyword arguments are allowed on marker {_BROWSER_CONTEXT_ARG_MARKER}")
        additional_browser_context_args.update(marker.kwargs)

    return additional_browser_context_args


def only_browser(item: pytest.Item) -> BrowserName | None:
    """
    Obtain the browser a test is restricted to, as specified in a pytest test's markers.

    :param item: The ``Item`` for the test being inspected.
    :returns: The browser to which the test is restricted, or ``None`` if that restriction is not set.
    """
    only_marker = item.get_closest_marker(_ONLY_BROWSER_MARKER)
    if not only_marker:
        return None

    if len(only_marker.args) != 1:
        raise ValueError(f"You must provide exactly one argument to pytest.mark.{_ONLY_BROWSER_MARKER}")
    arg = only_marker.args[0]
    if not isinstance(arg, BrowserName):
        raise TypeError(f"The argument to pytest.mark.{_ONLY_BROWSER_MARKER} must be a {BrowserName.__name__}")
    return arg


def skip_browsers(item: pytest.Item) -> set[BrowserName]:
    """
    Obtain the list of browsers to skip this test for, as specified in a pytest test's markers.

    :param item: The ``Item`` for the test being inspected.
    :returns: The browsers for which this test should be skipped.
    """
    skip_markers = [*item.iter_markers(_SKIP_BROWSER_MARKER)]

    skip_browsers: set[BrowserName] = set()
    for skip_marker in skip_markers:
        for arg in skip_marker.args:
            if not isinstance(arg, BrowserName):
                raise TypeError(
                    f"The arguments to pytest.mark.{_SKIP_BROWSER_MARKER} must be of type {BrowserName.__name__}"
                )
            skip_browsers.add(arg)
    return skip_browsers


def declared_browser_use(item: pytest.Item) -> BrowserUse:
    """
    Inspect how the current test has declared it will create browsers.

    :param item: The ``Item`` for the test being inspected.
    :returns: How the test has declared it will create browsers.
    """
    is_static = item.get_closest_marker(_STATIC_BROWSER_MARKER) is not None
    if is_static:
        if item.get_closest_marker(_MIXED_BROWSER_MARKER):
            raise RuntimeError(
                f"Use at most one of pytest.mark.{_STATIC_BROWSER_MARKER} and pytest.mark.{_MIXED_BROWSER_MARKER}"
            )
        if only_browser(item) is not None:
            raise RuntimeError(
                f"pytest.mark.{_ONLY_BROWSER_MARKER} is not allowed if pytest.mark.{_STATIC_BROWSER_MARKER} is used"
            )
        if any(skip_browsers(item)):
            raise RuntimeError(
                f"pytest.mark.{_SKIP_BROWSER_MARKER} is not allowed if pytest.mark.{_STATIC_BROWSER_MARKER} is used"
            )
        return BrowserUse.STATIC

    if item.get_closest_marker(_MIXED_BROWSER_MARKER) is not None:
        return BrowserUse.MIXED

    return BrowserUse.DYNAMIC
