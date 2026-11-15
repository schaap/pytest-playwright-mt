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
Managing class for a single Playwright instance

The ``PlaywrightMT`` class provides a facade for Playwright, instrumenting browsers it launches to provide all of the
functionality of this plugin.
"""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager, suppress
from inspect import Parameter, signature
from threading import Lock
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

from playwright.sync_api import (
    Browser,
    BrowserType,
    Playwright,
    ProxySettings,
    sync_playwright,
)

from pytest_playwright_mt.instrumentation import instrument_playwright_object
from pytest_playwright_mt.options import BrowserName, BrowserUse, RecordingOption

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import timedelta
    from pathlib import Path
    from types import TracebackType

    from pytest_playwright_mt.artifact_collector import ArtifactCollector


class IncorrectBrowserUseError(Exception):
    """
    Exception for incorrect browser use (specific browser instantiation without explicitly marking the test for static
    or mixed use, or ``launch`` in a test marked for static use).
    """


# This class is the one big starting point for most use, basically a facade to Playwright's main class. It also nicely
# exposes its extensive configuration. Yes, it has lots of public methods.
# ruff: ignore[PLR0904]
class PlaywrightMT:
    """
    A single (not thread-safe) Playwright instance, with additional instrumentation to actually handle all the
    Playwright-specific arguments to pytest.

    ``BrowserContext`` and ``Page`` instances that are spawned by the ``Browser`` objects instantiated by this class,
    will be given a name that is unique for the pytest session (``BrowserContext``) or the browser context (``Page``).
    Test developers can use these names after obtaining them via ``context_name`` and ``page_name``.

    THREAD SAFETY: Like the Playwright instance it encapsulates, ``PlayrightMT`` is **not** thread-safe! The caller is
    responsible for ensuring that all calls to this class and the browser(s) it launches are performed from the same
    thread.

    All relevant functionality of the underlying Playwright instance should be directly available through the
    ``PlaywrightMT`` API. If anything is missing, or for advanced use cases, the ``playwright_instance`` is available
    but be sure to read the caveat when using it: that basically bypasses all the pytest integration.
    """

    _context_counter: ClassVar[int] = 0
    """A counter to derive unique identifiers from for each ``BrowserContext``. Guarded by ``_context_counter_lock``."""

    _context_counter_lock: ClassVar[Lock] = Lock()
    """The lock guarding ``_context_counter``."""

    # ruff: ignore[PLR0913]  # This class needs to process a lot of input data. So: many arguments.
    def __init__(
        self,
        *,
        name: str,
        default_browser: BrowserName | None,
        headed: bool,
        browser_channel: str | None,
        slowmo: int,
        device: str | None,
        tracing: RecordingOption,
        video: RecordingOption,
        screenshot: RecordingOption,
        full_page_screenshot: bool,
        additional_browser_context_args: dict[str, Any],
        artifact_temporary_storage: Path,
        artifact_collector: ArtifactCollector,
        browser_use: BrowserUse,
    ) -> None:
        """
        Initialize a ``PlaywrightMT``. It is strongly encouraged to use ``PlaywrightMTFixture.create_instance`` to
        obtain an instance of ``PlaywrightMT``, instead.

        :param parent: The ``PlaywrightMTFixture`` that instantiated this ``PlaywrightMT``.
        :param name: A name for this playwright instance. This is used as a base name for artifact storage.
        :param default_browser: The browser to default to.
        :param headed: Whether to use a headed browser.
        :param browser_channel: The browser channel to use.
        :param slowmo: Have the browser run in slow motion, with a given number of milliseconds between interactions.
        :param device: The device to emulate.
        :param tracing: Whether to enable tracing in the browser.
        :param video: Whether to enable video recording in the browser.
        :param screenshot: Whether to automatically take a screenshot at the end of each browser page's lifetime.
        :param full_page_screenshot: Whether automatic screenshots (see ``screenshot``) will screenshot the entire page,
                                     instead of only the browser viewport.
        :param additional_browser_context_args: Additional arguments to pass to ``Browser.new_context``.
        :param artifact_temporary_storage: Directory where artifacts will be stored while the browser contexts exist.
        :param artifact_collector: The ``ArtifactCollector`` instance to use for artifacts created by browsers that
                                   spring from this instance.
        :param browser_use: The way the test function has declared it will create browsers.
        """
        self._name = name
        self._default_browser = default_browser or BrowserName.CHROMIUM
        self._headed = headed
        self._browser_channel = browser_channel
        self._slowmo = slowmo
        self._device = device
        self._tracing = tracing
        self._video = video
        self._screenshot = screenshot
        self._full_page_screenshot = full_page_screenshot
        self._additional_browser_context_args = dict(additional_browser_context_args)
        self._artifact_temporary_storage = artifact_temporary_storage
        self._artifact_collector = artifact_collector
        self._browser_use = browser_use

        self._context: AbstractContextManager[Playwright] | None = None
        """The context manager created by ``sync_playwright``. We need to track this, so we can exit it again."""
        self._instance: Playwright | None = None
        """The ``Playwright`` instance, the result of entering ``self._context``."""

        self._browsers: list[Browser] = []
        """All the browsers launched by this object."""

    @property
    def name(self) -> str:
        """The name for this playwright instance. This is used as a base name for artifact storage."""
        return self._name

    @property
    def artifact_temporary_storage(self) -> Path:
        """Directory where artifacts will be stored while the browser contexts exist."""
        return self._artifact_temporary_storage

    @property
    def headed(self) -> bool:
        """Whether a headed browser will be used."""
        return self._headed

    @property
    def browser_channel(self) -> str | None:
        """If set, the specific browser channel that will be used."""
        return self._browser_channel

    @property
    def slowmo(self) -> int:
        """The number of milliseconds between Playwright interactions."""
        return self._slowmo

    @property
    def device(self) -> str | None:
        """If set, the device that will be emulated."""
        return self._device

    @property
    def tracing(self) -> RecordingOption:
        """Whether tracing will be enabled in the browser."""
        return self._tracing

    @property
    def video(self) -> RecordingOption:
        """Whether a video will be recorded in the browser."""
        return self._video

    @property
    def screenshot(self) -> RecordingOption:
        """Whether to automatically take a screenshot at the end of each browser page's lifetime."""
        return self._screenshot

    @property
    def full_page_screenshot(self) -> bool:
        """
        Whether automatic screenshots (see ``screenshot``) will screenshot the entire page instead of just the browser
        viewport.
        """
        return self._full_page_screenshot

    @property
    def additional_browser_context_args(self) -> dict[str, Any]:
        """
        Additionl arguments to pass when creating a new browser context.

        This property provides a copy of the internal dictionary.
        """
        return dict(self._additional_browser_context_args)

    @property
    def artifact_collector(self) -> ArtifactCollector:
        """The ``ArtifactCollector`` to submit artifacts to for storage."""
        return self._artifact_collector

    # The name of playwright_instance is intentionally cumbersome (i.e. not just 'instance') to discourage its use and
    # to increase the chances of developers calling it actually reading its documentation.
    @property
    def playwright_instance(self) -> Playwright:
        """
        Most functionality of the ``Playwright`` instance can be accessed directly via the PlaywrightMT object
        (``self``), which is the prefered method.

        If you do find you need direct access to the instance, this property provides it.

        CAVEAT: When calling methods directly on the instance, the caller is responsible for passing any arguments that
        were passed via the ``PlaywrightMT`` instance. In particular the pytest-provided defaults are normally passed
        via the ``PlaywrightMT`` instance. There will also be no instrumentation, so all features provided by the plugin
        basically don't work.
        """
        # ruff: ignore[S101]
        assert self._instance is not None
        return self._instance

    def __enter__(self) -> Self:
        # ruff: ignore[S101]
        assert self._instance is None, "This object has already been entered."
        # ruff: ignore[S101]
        assert not self._artifact_temporary_storage.exists() or self._artifact_temporary_storage.is_dir(), (
            "The directory in which temporary artifacts are to be stored already exists, and is not a directory."
        )

        try:
            self._context = sync_playwright()
            self._instance = self._context.__enter__()
            self._artifact_temporary_storage.mkdir(parents=True, exist_ok=True)
        except Exception:
            self._instance = None
            if self._context is not None:
                context = self._context
                self._context = None
                if not context.__exit__(*sys.exc_info()):
                    raise
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> bool | None:
        self._instance = None

        res: bool | None = None
        try:
            # First close all the browsers
            for browser in list(self._browsers):
                browser.close(reason="PlaywrightMT instance is being closed")
            self._browsers = []

            # Some artifacts may only become available when the browsers were closed, so secure artifacts only after
            # closing them
            self._artifact_collector.secure_artifacts(root=self._artifact_temporary_storage)
        finally:
            # The Playwright instance must be closed last, to prevent artifacts from becoming lost. But it MUST be
            # closed: it has background resources active that can lock things up and/or break other tests.
            if self._context is not None:
                res = self._context.__exit__(exc_type, exc_value, traceback)
        return res

    def register_browser_for_close(self, browser: Browser) -> None:
        """
        Register a browser to be closed when this object is exited.

        :param browser: The browser to close.
        """
        assert self._instance  # ruff: ignore[S101]
        self._browsers.append(browser)

    def unregister_browser_for_close(self, browser: Browser) -> None:
        """
        Remove a previously registered browser from the list of browsers to be closed.

        :param browser: The browser to unregister.
        """
        # NOTE: Do not assert the instance, here! See __exit__'s flow.
        with suppress(ValueError):
            self._browsers.remove(browser)

    @classmethod
    def create_new_context_name(cls, basename: str) -> str:
        """
        Create a new browser context name that is unique for the pytest session.

        :param basename: A name to base the browser context name on.
        :returns: The new browser context name.
        """
        context_counter: int
        with PlaywrightMT._context_counter_lock:
            context_counter = PlaywrightMT._context_counter
            PlaywrightMT._context_counter += 1
        return f"{basename}-context-{context_counter}"

    def _launch_browser(
        self,
        browser_type: BrowserType,
        *,
        headless: bool | None = None,
        channel: str | None = None,
        slow_mo: float | None = None,
        **kwargs: Any,  # ruff: ignore[ANN401]  # We really don't know
    ) -> Browser:
        """
        Launch a ``Browser`` instance.

        This will construct all the launch arguments based on the settings of this object and any settings passed into
        this call. See ``BrowserType.launch`` for details on all possible arguments.

        :param browser_type: The type of browser to launch. Must be obtained from ``self._instance``.
        :param headless: Whether to run browser in headless mode.
        :param channel: Browser distribution channel.
        :param slow_mo: Slows down Playwright operations by the specified amount of milliseconds. Useful so that you can
                        see what is going on.
        :returns: The instantiated, instrumented ``Browser`` object.
        """
        # Construct the arguments to the launch call
        # Initial arguments are based on previously passed settings
        arguments: dict[str, Any] = {
            "headless": not self._headed,
            "channel": self._browser_channel,
            "slow_mo": self._slowmo,
        }

        # Construct a dictionary of the explicitly listed additional arguments
        override_arguments: dict[str, Any | None] = {"headless": headless, "channel": channel, "slow_mo": slow_mo}
        self._verify_arguments_copied(PlaywrightMT._launch_browser, override_arguments)

        # Override constructed arguments with explicitly set arguments and all the additional ones from kwargs
        # Ignore arguments that were passed but not actually set (value is None)
        arguments.update({k: v for (k, v) in override_arguments.items() if v is not None})
        arguments.update({k: v for (k, v) in kwargs.items() if v is not None})

        # Launch the browser
        browser = browser_type.launch(**arguments)

        # Instrument and track the Browser instance
        instrument_playwright_object(browser, self)
        self.register_browser_for_close(browser)

        return browser

    def _assert_static_launch(self, kwargs: dict[str, Any]) -> None:
        """Assert that launching a static browser (i.e. not ``launch``) is allowed."""
        if kwargs.get(_DYNAMIC_BROWSER_LAUNCH) is _DYNAMIC_BROWSER_LAUNCH_VALUE:
            del kwargs[_DYNAMIC_BROWSER_LAUNCH]
            return
        if self._browser_use is BrowserUse.DYNAMIC:
            raise IncorrectBrowserUseError(
                f"Please use {PlaywrightMT.launch.__name__} to instantiate a new browser. This will allow "
                "parametrization of which browser will be used. You can restrict your test to a single browser using "
                "pytest.mark.only_browser or skip specific browsers using pytest.mark.skip_browser. If you do need "
                "to instantiate specific browsers in your test, then use pytest.mark.static_browser to declare this "
                "(your test will no longer be parametrized for the requested browsers), or use "
                "pytest.mark.mixed_browser to declare that you will use a mix of both specific and requested "
                "browsers (your test will be`connect parametrized for the requested browsers)."
            )

    def _assert_dynamic_launch(self) -> None:
        """Assert that launching a dynamic browser (i.e. ``launch``) is allowed."""
        if self._browser_use is BrowserUse.STATIC:
            raise IncorrectBrowserUseError(
                f"It is not allowed to use {PlaywrightMT.launch.__name__} in a test marked by "
                "pytest.mark.static_browser. Remove that marker or, if you wish to use a mix of specific and "
                "requested browsers, replace it with pytest.mark.mixed_browser (your test will become parametrized "
                "for the requested browsers, but can still instantiate specific browsers)."
            )

    # ruff: ignore[PLR0913]  # Yes, many arguments. Blame Playwright (except that it makes sense).
    def chromium(
        self,
        *,
        channel: str | None = None,
        chromium_sandbox: bool | None = None,
        downloads_path: str | Path | None = None,
        env: dict[str, str | float | bool] | None = None,
        headless: bool | None = None,
        proxy: ProxySettings | None = None,
        slow_mo: float | None = None,
        timeout: float | timedelta | None = None,
        **kwargs: Any,  # ruff: ignore[ANN401]  # We really don't know
    ) -> Browser:
        """
        Launch a Chromium browser.

        This bypasses the ``BrowserType`` and immediately launches a new ``Browser`` with non-peristent context.

        Wraps ``BrowserType.launch``. The most common parameters are summarized here, see ``BrowserType.launch`` for all
        parameters and full documentation.

        :param channel: Browser distribution channel.
        :param chromium_sandbox: Enable Chromium sandboxing. Defaults to ``False``.
        :param downloads_path: If specified, accepted downloads are downloaded into this directory. Otherwise, temporary
                               directory is created and is deleted when browser is closed. In either case, the downloads
                               are deleted when the browser context they were created in is closed.
        :param env: Specify environment variables that will be visible to the browser. Defaults to ``process.env``.
        :param headless: Whether to run browser in headless mode.
        :param proxy: Network proxy settings.
        :param slow_mo: Slows down Playwright operations by the specified amount of milliseconds. Useful so that you can
                        see what is going on.
        :param timeout: Maximum time in milliseconds to wait for the browser instance to start. Defaults to ``180000``
                        (3 minutes). Pass ``0`` to disable timeout.
        """
        assert self._instance is not None  # ruff: ignore[S101]
        self._assert_static_launch(kwargs)

        return self._launch_browser(
            self._instance.chromium,
            channel=channel,
            chromium_sandbox=chromium_sandbox,
            downloads_path=downloads_path,
            env=env,
            headless=headless,
            proxy=proxy,
            slow_mo=slow_mo,
            timeout=timeout,
            **kwargs,
        )

    # ruff: ignore[PLR0913]  # Yes, many arguments. Blame Playwright (except that it makes sense).
    def firefox(
        self,
        *,
        channel: str | None = None,
        downloads_path: str | Path | None = None,
        env: dict[str, str | float | bool] | None = None,
        firefox_user_prefs: dict[str, str | float | bool] | None = None,
        headless: bool | None = None,
        proxy: ProxySettings | None = None,
        slow_mo: float | None = None,
        timeout: float | timedelta | None = None,
        **kwargs: Any,  # ruff: ignore[ANN401]  # We really don't know
    ) -> Browser:
        """
        Launch a Firefox browser.

        This bypasses the ``BrowserType`` and immediately launches a new ``Browser`` with non-peristent context.

        Wraps ``BrowserType.launch``. The most common parameters are summarized here, see ``BrowserType.launch`` for all
        parameters and full documentation.

        :param channel: Browser distribution channel.
        :param downloads_path: If specified, accepted downloads are downloaded into this directory. Otherwise, temporary
                               directory is created and is deleted when browser is closed. In either case, the downloads
                               are deleted when the browser context they were created in is closed.
        :param env: Specify environment variables that will be visible to the browser. Defaults to ``process.env``.
        :param firefox_user_prefs: Firefox user preferences.
        :param headless: Whether to run browser in headless mode.
        :param proxy: Network proxy settings.
        :param slow_mo: Slows down Playwright operations by the specified amount of milliseconds. Useful so that you can
                        see what is going on.
        :param timeout: Maximum time in milliseconds to wait for the browser instance to start. Defaults to ``180000``
                        (3 minutes). Pass ``0`` to disable timeout.
        -----

        """
        assert self._instance is not None  # ruff: ignore[S101]
        self._assert_static_launch(kwargs)

        return self._launch_browser(
            self._instance.firefox,
            channel=channel,
            downloads_path=downloads_path,
            env=env,
            firefox_user_prefs=firefox_user_prefs,
            headless=headless,
            proxy=proxy,
            slow_mo=slow_mo,
            timeout=timeout,
            **kwargs,
        )

    # ruff: ignore[PLR0913]  # Yes, many arguments. Blame Playwright (except that it makes sense).
    def webkit(
        self,
        *,
        channel: str | None = None,
        downloads_path: str | Path | None = None,
        env: dict[str, str | float | bool] | None = None,
        headless: bool | None = None,
        proxy: ProxySettings | None = None,
        slow_mo: float | None = None,
        timeout: float | timedelta | None = None,
        **kwargs: Any,  # ruff: ignore[ANN401]  # We really don't know
    ) -> Browser:
        """
        Launch a Webkit browser.

        This bypasses the ``BrowserType`` and immediately launches a new ``Browser`` with non-peristent context.

        Wraps ``BrowserType.launch``. The most common parameters are summarized here, see ``BrowserType.launch`` for all
        parameters and full documentation.

        :param channel: Browser distribution channel.
        :param downloads_path: If specified, accepted downloads are downloaded into this directory. Otherwise, temporary
                               directory is created and is deleted when browser is closed. In either case, the downloads
                               are deleted when the browser context they were created in is closed.
        :param env: Specify environment variables that will be visible to the browser. Defaults to ``process.env``.
        :param headless: Whether to run browser in headless mode.
        :param proxy: Network proxy settings.
        :param slow_mo: Slows down Playwright operations by the specified amount of milliseconds. Useful so that you can
                        see what is going on.
        :param timeout: Maximum time in milliseconds to wait for the browser instance to start. Defaults to ``180000``
                        (3 minutes). Pass ``0`` to disable timeout.
        """
        assert self._instance is not None  # ruff: ignore[S101]
        self._assert_static_launch(kwargs)

        return self._launch_browser(
            self._instance.webkit,
            channel=channel,
            downloads_path=downloads_path,
            env=env,
            headless=headless,
            proxy=proxy,
            slow_mo=slow_mo,
            timeout=timeout,
            **kwargs,
        )

    # ruff: ignore[PLR0913]  # Yes, many arguments. Blame Playwright (except that it makes sense).
    def launch(
        self,
        *,
        channel: str | None = None,
        chromium_sandbox: bool | None = None,
        downloads_path: str | Path | None = None,
        env: dict[str, str | float | bool] | None = None,
        firefox_user_prefs: dict[str, str | float | bool] | None = None,
        headless: bool | None = None,
        proxy: ProxySettings | None = None,
        slow_mo: float | None = None,
        timeout: float | timedelta | None = None,
        **kwargs: Any,  # ruff: ignore[ANN401]  # We really don't know
    ) -> Browser:
        """
        Launch a browser. This will use any pytest-provided arguments to determine the browser to launch, falling back
        to Chromium if nothing is specified.

        This bypasses the ``BrowserType`` and immediately launches a new ``Browser`` with non-peristent context.

        Wraps ``BrowserType.launch``. The most common parameters are summarized here, see ``BrowserType.launch`` for all
        parameters and full documentation.

        :param channel: Browser distribution channel.
        :param chromium_sandbox: Enable Chromium sandboxing. Defaults to ``False``.
        :param downloads_path: If specified, accepted downloads are downloaded into this directory. Otherwise, temporary
                               directory is created and is deleted when browser is closed. In either case, the downloads
                               are deleted when the browser context they were created in is closed.
        :param env: Specify environment variables that will be visible to the browser. Defaults to ``process.env``.
        :param firefox_user_prefs: Firefox user preferences.
        :param headless: Whether to run browser in headless mode.
        :param proxy: Network proxy settings.
        :param slow_mo: Slows down Playwright operations by the specified amount of milliseconds. Useful so that you can
                        see what is going on.
        :param timeout: Maximum time in milliseconds to wait for the browser instance to start. Defaults to ``180000``
                        (3 minutes). Pass ``0`` to disable timeout.
        """
        self._assert_dynamic_launch()
        # ruff: ignore[S101]  # This guards against a serious programming error.
        assert _DYNAMIC_BROWSER_LAUNCH not in kwargs

        # Check the typing of all the explicit parameters to this method by calling on BrowserType.launch() directly,
        # but only in type-checking mode. This makes static checkers work for us, while ignoring this at runtime.
        if TYPE_CHECKING:
            assert self._instance
            self._instance.chromium.launch(
                channel=channel,
                chromium_sandbox=chromium_sandbox,
                downloads_path=downloads_path,
                env=env,
                firefox_user_prefs=firefox_user_prefs,
                headless=headless,
                proxy=proxy,
                slow_mo=slow_mo,
                timeout=timeout,
            )

        # Roll all the explicitly listed arguments into kwargs, so we don't need to repeat them three more times
        additional_args: dict[str, Any] = {}
        additional_args["channel"] = channel
        additional_args["chromium_sandbox"] = chromium_sandbox
        additional_args["downloads_path"] = downloads_path
        additional_args["env"] = env
        additional_args["firefox_user_prefs"] = firefox_user_prefs
        additional_args["headless"] = headless
        additional_args["proxy"] = proxy
        additional_args["slow_mo"] = slow_mo
        additional_args["timeout"] = timeout
        kwargs = dict(kwargs)
        kwargs.update(additional_args)
        self._verify_arguments_copied(PlaywrightMT.launch, additional_args)

        # Launch the correct browser
        kwargs[_DYNAMIC_BROWSER_LAUNCH] = _DYNAMIC_BROWSER_LAUNCH_VALUE
        if self._default_browser is BrowserName.FIREFOX:
            return self.firefox(**kwargs)
        if self._default_browser is BrowserName.WEBKIT:
            return self.webkit(**kwargs)
        # Chromium is the preferred (fallback) default for Playwright testing
        return self.chromium(**kwargs)

    @staticmethod
    def _verify_arguments_copied(
        func: Callable[..., Any], argument_copy: dict[str, Any], ignore_args: Iterable[str] = ()
    ) -> None:
        """
        Assert that all explicit keyword-only arguments to a function are listed in a dictionary.

        Validation is performed on the given function itself, *without* following any wrapping. Inspection is based on
        the result of calling ``inspect.signature``.

        :param func: The function of which all keyword-only arguments must have been listed.
        :param argument_copy: The dictionary of which the keys must match the exact list of the keyword-only arguments
                              of ``func``.
        :param ignore_args: The names of keyword-only arguments that are expected not to be in ``argument_copy``.
        """
        sig = signature(func, follow_wrapped=False)
        explicit_keys = [
            name
            for name, param in sig.parameters.items()
            if param.kind == Parameter.KEYWORD_ONLY and name not in ignore_args
        ]
        copied_keys = argument_copy.keys()
        # ruff: ignore[S101]  # This function tests correctness and completeness of dynamic typing. Yes, assert.
        assert all(k in explicit_keys for k in copied_keys)
        # ruff: ignore[S101]
        assert all(k in copied_keys for k in explicit_keys)


# To encourage good user behaviour, the browser launch methods are guarded against less-then-stellar use. However, we
# define the preferred dynamic launch method (launch) in terms of the specific methods (chromium, firefox, etc). The
# latter are normally guarded against being used. An internal sentinel is used to let launch bypass this protection.
# Using a sentinel value was chosen over extracting the actual launch code into internal methods: this way prevents a
# lot of duplication of code that primarily helps the user write their tests (full featured signatures, for example) and
# also prevents mistakes when developing the plugin itself.


class _DynamicBrowserToken:
    """Empty class used as the internal dynamic launch sentinel value."""


_DYNAMIC_BROWSER_LAUNCH: Final[str] = "_playwright_mt_dynamic_browser"
"""Keyword argument name for passing the internal dynamic launch sentinel."""

_DYNAMIC_BROWSER_LAUNCH_VALUE: Final[_DynamicBrowserToken] = _DynamicBrowserToken()
"""Static dynamic launch sentinel value for internal use."""
