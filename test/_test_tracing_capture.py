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
Tests that will or will not capture a trace file. These tests will be run indirectly using pytester.

These tests will be called indirectly via pytester in ``test_tracing.py``
"""

import pytest
from server import WebServer

from pytest_playwright_mt.options import RecordingOption
from pytest_playwright_mt.playwright_mt_fixture import PlaywrightMTFixture


@pytest.mark.parametrize(
    "tracing",
    [
        RecordingOption.ON,
        RecordingOption.RETAIN_ON_FAILURE,
    ],
)
def test_tracing_captures_on_failure(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    tracing: RecordingOption,
) -> None:
    """
    Helper to verify that with tracing set to ``RecordingOption.ON`` or ``RecordingOption.RETAIN_ON_FAILURE``, the
    output is captured even if the test fails.
    """
    playwright_mt.tracing = tracing
    visit_counter_page(playwright_mt, web_server)
    pytest.fail("Supposed to fail")


@pytest.mark.parametrize(
    "tracing",
    [
        RecordingOption.ON,
    ],
)
def test_tracing_captures_on_success(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    tracing: RecordingOption,
) -> None:
    """
    Helper to verify that with tracing set to ``RecordingOption.ON``, the output is captured when the test succeeds.
    """
    playwright_mt.tracing = tracing
    visit_counter_page(playwright_mt, web_server)


@pytest.mark.parametrize(
    "tracing",
    [
        RecordingOption.RETAIN_ON_FAILURE,
        RecordingOption.OFF,
    ],
)
def test_tracing_does_not_capture_on_success(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    tracing: RecordingOption,
) -> None:
    """
    Helper to verify that with tracing set to ``RecordingOption.RETAIN_ON_FAILURE`` or ``RecordingOption.OFF``, the
    output is not captured when the test succeeds.
    """
    playwright_mt.tracing = tracing
    visit_counter_page(playwright_mt, web_server)


@pytest.mark.parametrize(
    "tracing",
    [
        RecordingOption.OFF,
    ],
)
def test_tracing_does_not_capture_on_failure(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    tracing: RecordingOption,
) -> None:
    """
    Helper to verify that with tracing set to ``RecordingOption.OFF``, the output is not captured when the test fails.
    """
    playwright_mt.tracing = tracing
    visit_counter_page(playwright_mt, web_server)
    pytest.fail("Supposed to fail")


def visit_counter_page(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Visit the counter page of the webserver in a newly created Playwright instance.

    This is the common, repetitive task performed by all the tests in this module. The difference is in how they
    configure trace recording and whether the test succeeds or fails.

    :param playwright_mt: The ``PlaywrightMTFixture`` for the test.
    :param web_server: The ``WebServer`` to visit.
    """
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_context().new_page()
        page.goto(f"{web_server.url}counter")
        page.get_by_role("link", name="Increment again")
