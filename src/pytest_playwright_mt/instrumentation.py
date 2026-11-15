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
Instrumentation for Playwright objects, applied by monkey-patching them

The instrumentation is internal to the plugin, although users can inspect their contexts' and page's unique(ish)
names, because why not.
"""

from collections.abc import Callable
from contextlib import suppress
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from playwright.sync_api import Browser, BrowserContext, Page

from pytest_playwright_mt.options import RecordingOption

if TYPE_CHECKING:
    from pytest_playwright_mt.playwright_mt import PlaywrightMT

# Names of additional attributes on Browser
_BROWSER_CONTEXTS_ATTR: Final[str] = "playwright_mt_contexts"

# Names of additional attributes on BrowserContext
_BROWSER_CONTEXT_CLOSED_ATTR: Final[str] = "playwright_mt_closed"
_BROWSER_CONTEXT_NAME_ATTR: Final[str] = "playwright_mt_context_name"
_BROWSER_CONTEXT_PAGES_ATTR: Final[str] = "playwright_mt_pages"

# Names of additional attributes on Page
_PAGE_CLOSED_ATTR: Final[str] = "playwright_mt_closed"
_PAGE_CONTEXT_NAME_ATTR: Final[str] = "playwright_mt_context_name"
_PAGE_NAME_ATTR: Final[str] = "playwright_mt_page_name"
_PAGE_DEDICATED_CONTEXT_ATTR: Final[str] = "playwright_mt_dedicated_context"


def instrument_playwright_object(obj: Browser | BrowserContext | Page, parent: "PlaywrightMT") -> None:
    """
    Instrument a Playwright object.

    Instrumentation is done by monkey-patching methods and attaching additional attributes.

    :param obj: The Playwright object to instrument.
    :param parent: The ``PlaywrightMT`` instance that manages the Playwright instance that ``obj`` belongs to.
    """
    if isinstance(obj, Browser):
        obj.new_context = _browser_new_context_wrapper(obj, parent)  # type: ignore[method-assign]
        obj.close = _browser_close_wrapper(obj, parent)  # type: ignore[method-assign]
        obj.new_page = _browser_new_page_replacement(obj)  # type: ignore[method-assign]
    elif isinstance(obj, BrowserContext):
        obj.new_page = _browser_context_new_page_wrapper(obj, parent)  # type: ignore[method-assign]
        obj.close = _browser_context_close_wrapper(obj, parent)  # type: ignore[method-assign]
    else:
        obj.close = _page_close_wrapper(obj, parent)  # type: ignore[method-assign]


def context_name(context: BrowserContext | Page) -> str:
    """
    Extract the pytest-session unique context name from an instrumented ``BrowserContext`` or ``Page``.

    :param context: The ``BrowserContext`` to get the name for. May also be a ``Page``, in which case the name of its
                    context will be returned.
    :returns: The context name of the browser context.
    """
    if isinstance(context, BrowserContext):
        return getattr(context, _BROWSER_CONTEXT_NAME_ATTR)
    return getattr(context, _PAGE_CONTEXT_NAME_ATTR)


def page_name(page: Page) -> str:
    """
    Extract the context-unique name from an instrumented ``Page``.

    To get a pytest-session unique name, combine this with ``context_name(page)``.

    :param page: The ``Page`` to get the name for.
    :returns: The name of the page.
    """
    return getattr(page, _PAGE_NAME_ATTR)


def _browser_close_wrapper(browser: Browser, parent: "PlaywrightMT") -> Callable[..., None]:
    """
    Create a wrapper for ``Browser.close``.
    """

    @wraps(browser.close)
    # ruff: ignore[ANN401]  # This is a wrapper
    def close(**kwargs: Any) -> None:
        """
        A wrapper that first closes the browser contexts associated with the browser.
        """
        # Close all registered BrowserContext instances, first
        reason = {"reason": kwargs.get("reason")}
        contexts = cast(list[BrowserContext], getattr(browser, _BROWSER_CONTEXTS_ATTR, []))
        for context in list(contexts):
            # ruff: ignore[S101]  # We're guarding against programming errors, here
            assert isinstance(context, BrowserContext)
            context.close(**reason)

        parent.unregister_browser_for_close(browser)

        return Browser.close(browser, **kwargs)

    return close


def _browser_new_context_wrapper(browser: Browser, parent: "PlaywrightMT") -> Callable[..., BrowserContext]:
    """
    Create a wrapper for ``Browser.new_context``.
    """

    @wraps(browser.new_context)
    # ruff: ignore[ANN401]  # This is a wrapper
    def new_context_wrapper(**kwargs: Any) -> BrowserContext:
        """
        A wrapper for ``new_context`` that injects arguments that were provided via pytest, enables the tracing and
        video recording on the context, and instruments the new ``BrowserContext``.
        """
        # Determine the name of the context
        context_name = parent.create_new_context_name(parent.name)

        # Arguments to use. The arguments will be added from each source to this dict in order of increasing importance.
        arguments: dict[str, Any] = {}

        # 1) Device emulation passed at pytest level
        if parent.device is not None:
            # Extract a fully typed reference to the devices array, so the rest of the code can be correctly typed
            devices = cast(dict[str, dict[str, Any]], parent.playwright_instance.devices)
            arguments = devices[parent.device]

        # 2) Arguments passed at pytest level
        if parent.video is not RecordingOption.OFF:
            recording_location = parent.artifact_temporary_storage / context_name / "video_scratch"
            recording_location.mkdir(parents=True, exist_ok=True)
            arguments["record_video_dir"] = str(recording_location)

        # 3) Additional browser context arguments passed via the marker
        arguments.update(parent.additional_browser_context_args)

        # 4) Additional arguments passed directly to this method
        arguments.update(kwargs)

        # Call upon the original, wrapped method for all the heavy lifting of creating the instance
        browser_context = Browser.new_context(browser, **arguments)
        try:  # ruff: ignore[PLW0717]  # Defensively coded, with cleanup
            # Assign the name of the context
            setattr(browser_context, _BROWSER_CONTEXT_NAME_ATTR, context_name)

            # Tracing can only be enabled after the context has been created
            if parent.tracing is not RecordingOption.OFF:
                browser_context.tracing.start(
                    title=context_name,
                    screenshots=True,
                    snapshots=True,
                    sources=True,
                )

            # Instrument and register the BrowserContext
            instrument_playwright_object(browser_context, parent)
            contexts = getattr(browser, _BROWSER_CONTEXTS_ATTR, [])
            contexts.append(browser_context)
            setattr(browser, _BROWSER_CONTEXTS_ATTR, contexts)
        except:
            browser_context.close()
            raise

        return browser_context

    return new_context_wrapper


def _browser_new_page_replacement(browser: Browser) -> Callable[..., Page]:
    """
    Create a replacement for ``Browser.new_page``.
    """

    @wraps(browser.new_page)
    # ruff: ignore[ANN401]  # This is (technically) a wrapper
    def new_page(**kwargs: Any) -> Page:
        """
        Replacement implementation that defines ``Browser.new_page`` in terms of ``Browser.new_context`` and
        ``BrowserContext.new_page``, with minimal glue to automatically close the context when the page closes.
        """
        # Note that the newly constructed objects are *not* instrumented here. The new_context and new_page calls we use
        # are already instrumented, and will instrument the objects the create.

        context = browser.new_context()
        # new_page currently has no kwargs, but this is future-proof
        page = context.new_page(**kwargs)

        # Register the dedicated context on the page object
        setattr(page, _PAGE_DEDICATED_CONTEXT_ATTR, context)

        return page

    return new_page


def _browser_context_close_wrapper(context: BrowserContext, parent: "PlaywrightMT") -> Callable[..., None]:
    """
    Create a wrapper for ``BrowserContext.close``.
    """

    @wraps(context.close)
    # ruff: ignore[ANN401]  # This is a wrapper
    def close(**kwargs: Any) -> None:
        """
        A wrapper for close that finalizes tracing and secures videos, and explicitly closes pages in the context before
        closing the context itself.
        """
        # Only close the context once. Self-tracked to prevent including a back-references to the Browser.
        if getattr(context, _BROWSER_CONTEXT_CLOSED_ATTR, False):
            return
        setattr(context, _BROWSER_CONTEXT_CLOSED_ATTR, True)

        # Close all the pages first
        pages = cast(list[Page], getattr(context, _BROWSER_CONTEXT_PAGES_ATTR, []))
        for page in pages:
            # ruff: ignore[S101]  # We're guarding against programming errors, here
            assert isinstance(page, Page)
            page.close(**kwargs)

        # Tracing must be finished before we close the context
        if parent.tracing is not RecordingOption.OFF:
            name = context_name(context)
            trace_path = parent.artifact_temporary_storage / name / "trace.zip"
            context.tracing.stop(path=trace_path)
            parent.artifact_collector.add_artifact(trace_path, Path("traces") / f"{name}.zip", parent.tracing)

        BrowserContext.close(context, **kwargs)

        # Store the videos of all the pages *after* the browser context with those pages has been closed. The videos are
        # only finalized and stable on disk after the pages have been closed (according to the original plugin code).
        if parent.video is not RecordingOption.OFF:
            name = context_name(context)
            videos_path = parent.artifact_temporary_storage / name / "videos"
            videos_path.mkdir(parents=True, exist_ok=True)
            for ctr, page in enumerate(pages):
                if not page.video:
                    continue
                video_path = videos_path / f"page_{ctr}.webm"
                page.video.save_as(videos_path / f"page_{ctr}.webm")
                with suppress(Exception):
                    # Remove the temporary internal storage of the video
                    page.video.delete()
                    # We suppress any Exception here. Removing is strictly best-effort.
                parent.artifact_collector.add_artifact(
                    video_path, Path("videos") / name / video_path.name, parent.video
                )

        return

    return close


def _browser_context_new_page_wrapper(context: BrowserContext, parent: "PlaywrightMT") -> Callable[..., Page]:
    """
    Creates a wrapper for ``BrowserContext.new_page``.
    """

    @wraps(context.new_page)
    # ruff: ignore[ANN401]  # This is a wrapper
    def new_page(**kwargs: Any) -> Page:
        """
        A wrapper for ``new_page`` that instruments and tracks the pages in their browser context.
        """
        # new_page currently has no kwargs, but this is future-proof
        page = BrowserContext.new_page(context, **kwargs)

        # Instrument the page and register it with its context
        instrument_playwright_object(page, parent)
        pages = cast(list[Page], getattr(context, _BROWSER_CONTEXT_PAGES_ATTR, []))
        pages.append(page)
        setattr(context, _BROWSER_CONTEXT_PAGES_ATTR, pages)

        # Track both the context's name and a context-unique name for the page on the Page itself
        setattr(page, _PAGE_CONTEXT_NAME_ATTR, context_name(context))
        setattr(page, _PAGE_NAME_ATTR, f"page{len(pages)}")

        return page

    return new_page


def _page_close_wrapper(page: Page, parent: "PlaywrightMT") -> Callable[..., None]:
    """
    Creates a wrapper for ``Page.close``.
    """

    @wraps(Page.close)
    # ruff: ignore[ANN401]  # This is a wrapper
    def close(**kwargs: Any) -> None:
        """
        A wrapper for ``close`` that takes a screenshot, if needed. Also handles closing any dedicated context.
        """
        # Only close the page once. Self-tracked to prevent including back-references to the BrowserContext, here.
        if getattr(page, _PAGE_CLOSED_ATTR, False):
            return
        setattr(page, _PAGE_CLOSED_ATTR, True)

        # If requested, take a screenshot right before closing the page
        if parent.screenshot is not RecordingOption.OFF:
            page_context_name = context_name(page)
            name = page_name(page)
            screenshots_path = parent.artifact_temporary_storage / page_context_name / "screenshots"
            screenshots_path.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshots_path / f"{name}.png"
            page.screenshot(
                timeout=5000,
                path=screenshot_path,
                type="png",
                full_page=parent.full_page_screenshot,
            )
            parent.artifact_collector.add_artifact(
                screenshot_path, Path("screenshots") / page_context_name / screenshot_path.name, parent.screenshot
            )

        # Note: The page is *not* deregistered from its context. The pages may still need to be accessed after the
        # context has been closed for securing some of the artifacts.

        Page.close(page, **kwargs)

        # Close a dedicated context, if the page had one (e.g. it was created via BrowserContext.new_page)
        context = cast(BrowserContext | None, getattr(page, _PAGE_DEDICATED_CONTEXT_ATTR, None))
        if context is not None:
            context.close(**kwargs)
            # Help the garbage collector by removing the circular reference
            delattr(page, _PAGE_DEDICATED_CONTEXT_ATTR)

    return close
