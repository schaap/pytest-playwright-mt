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
Tests that simply depend on which browser is running.

These tests will be called indirectly via pytester in ``test_fixture.py``
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from pytest_playwright_mt import BrowserName, PlaywrightMT, PlaywrightMTFixture, RecordingOption


def test_default_browser_explicit(
    playwright_mt: PlaywrightMTFixture, browser_name: BrowserName, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test default browser selection when it includes a explicit request for the ``browser_name`` fixture.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) == browser_name


def test_default_browser_implict(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test default browser selection, without explicitly requested browser_name.

    This also verifies that dynamically requesting the ``browser_name`` fixture later on still yields correct results.
    """
    assert do_launch_test(playwright_mt, tmp_path, request)


@pytest.mark.skip_browser(BrowserName.FIREFOX)
def test_default_browser_skip_firefox(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``skip_browser`` marker.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) != BrowserName.FIREFOX


@pytest.mark.skip_browser(BrowserName.CHROMIUM)
def test_default_browser_skip_chromium(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``skip_browser`` marker, which should also skip on the default browser selection.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) != BrowserName.CHROMIUM


@pytest.mark.only_browser(BrowserName.FIREFOX)
def test_default_browser_only_firefox(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``only_browser`` marker.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) == BrowserName.FIREFOX


@pytest.mark.only_browser(BrowserName.CHROMIUM)
def test_default_browser_only_chromium(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``only_browser`` marker, which should also work on the default browser.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) == BrowserName.CHROMIUM


@pytest.mark.only_browser(BrowserName.FIREFOX)
@pytest.mark.skip_browser(BrowserName.FIREFOX)
def test_default_browser_always_skip(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``only_browser`` and ``skip_browser`` markers. This test will always skip due to its combination.
    """
    do_launch_test(playwright_mt, tmp_path, request)


@pytest.mark.skip_browser(BrowserName.CHROMIUM, BrowserName.CHROMIUM, BrowserName.FIREFOX)
def test_default_browser_multiskip_combined(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``skip_browser`` marker. This test uses multiple arguments on the marker.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) not in {BrowserName.CHROMIUM, BrowserName.FIREFOX}


@pytest.mark.skip_browser(BrowserName.CHROMIUM)
@pytest.mark.skip_browser(BrowserName.FIREFOX)
@pytest.mark.skip_browser(BrowserName.CHROMIUM)
def test_default_browser_multiskip_stacked(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``skip_browser`` marker. This test uses multiple markers.
    """
    assert do_launch_test(playwright_mt, tmp_path, request) not in {BrowserName.CHROMIUM, BrowserName.FIREFOX}


@pytest.mark.static_browser
def test_default_browser_static(playwright_mt: PlaywrightMTFixture) -> None:
    """
    Helper to test the ``static_browser`` marker. This test should not be parametrized at all (except for technically
    being parametrized, for the default only).
    """
    with playwright_mt.create_instance() as pw:
        pw.chromium()


@pytest.mark.static_browser
def test_default_browser_static_fail(playwright_mt: PlaywrightMTFixture) -> None:
    """
    Helper to test enforcement of the ``static_browser`` marker. This test should not be parametrized at all (except for
    technically being parametrized, for the default only), and will fail because it uses ``launch``.
    """
    with playwright_mt.create_instance() as pw:
        pw.launch()


@pytest.mark.mixed_browser
def test_default_browser_mixed(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``mixed_browser`` marker. This test will be parametrized. Also verifies the independence of
    ``launch`` of a specific browser call (``firefox``, in this case).
    """
    do_launch_test(playwright_mt, tmp_path, request, extra_steps=lambda pw: pw.firefox())


def test_default_browser_mixed_fail(playwright_mt: PlaywrightMTFixture) -> None:
    """
    Helper to test the enforcement of the ``mixed_browser`` and ``static_browser`` marker. This test will be
    parametrized and will fail because it uses a static browser without declaring so.
    """
    with playwright_mt.create_instance() as pw:
        pw.chromium()


@pytest.mark.mixed_browser
@pytest.mark.only_browser(BrowserName.FIREFOX)
def test_default_browser_mixed_and_only(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``mixed_browser`` and ``only_browser`` markers. The latter should still apply.
    """
    # No actual mixed use, but that is not the point of the test
    assert do_launch_test(playwright_mt, tmp_path, request) == BrowserName.FIREFOX


@pytest.mark.mixed_browser
@pytest.mark.skip_browser(BrowserName.FIREFOX)
def test_default_browser_mixed_and_skip(
    playwright_mt: PlaywrightMTFixture, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """
    Helper to test the ``mixed_browser`` and ``skip_browser`` markers. The latter should still apply.
    """
    # No actual mixed use, but that is not the point of the test
    assert do_launch_test(playwright_mt, tmp_path, request) != BrowserName.FIREFOX


def do_launch_test(
    playwright_mt: PlaywrightMTFixture,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    extra_steps: Callable[[PlaywrightMT], Any] | None = None,
) -> BrowserName:
    """
    Launch a browser using ``launch`` on a newly created Playwright instance, record its browser type in an artifact,
    and verify that it matches the dynamically requested ``browser_name`` fixture.

    This is basically the content of just about every test in this module. The important testing is in the different
    signatures of the test functions (the markers and requested fixtures). This helper takes care of the common,
    repetitive part.

    :param playwright_mt: The PlaywrightMTFixture.
    :param tmp_path: Temporary path provided by pytest.
    :param request: The pytest request object.
    :param extra_steps: If set, this will be called with the ``PlaywrightMT`` instance as soon as it has been made.
    :returns: The name of the type of the browser that was launched.
    """
    launched_browser_file = tmp_path / "launched_browser"
    playwright_mt.artifact_collector.add_artifact(
        launched_browser_file, Path(launched_browser_file.name), RecordingOption.ON
    )

    with playwright_mt.create_instance() as pw:
        if extra_steps is not None:
            extra_steps(pw)
        browser = pw.launch()
        launched_browser_file.write_text(browser.browser_type.name)

        browser_name = cast(BrowserName | None, request.getfixturevalue("browser_name"))
        assert browser_name is not None
        assert browser_name.value == browser.browser_type.name

        return BrowserName(browser.browser_type.name)
