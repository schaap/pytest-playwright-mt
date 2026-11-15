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
Tests that will or will not capture a video file. These tests will be run indirectly using pytester.

These tests will be called indirectly via pytester in ``test_video.py``
"""

import pytest
from server import WebServer

from pytest_playwright_mt.options import RecordingOption
from pytest_playwright_mt.playwright_mt_fixture import PlaywrightMTFixture


@pytest.mark.parametrize(
    "video",
    [
        RecordingOption.ON,
        RecordingOption.RETAIN_ON_FAILURE,
    ],
)
def test_video_captures_on_failure(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    video: RecordingOption,
) -> None:
    """
    Helper to verify that with video set to ``RecordingOption.ON`` or ``RecordingOption.RETAIN_ON_FAILURE``, the
    output is captured even if the test fails.
    """
    playwright_mt.video = video
    visit_counter_page(playwright_mt, web_server)
    pytest.fail("Supposed to fail")


@pytest.mark.parametrize(
    "video",
    [
        RecordingOption.ON,
    ],
)
def test_video_captures_on_success(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    video: RecordingOption,
) -> None:
    """
    Helper to verify that with video set to ``RecordingOption.ON``, the output is captured when the test succeeds.
    """
    playwright_mt.video = video
    visit_counter_page(playwright_mt, web_server)


@pytest.mark.parametrize(
    "video",
    [
        RecordingOption.RETAIN_ON_FAILURE,
        RecordingOption.OFF,
    ],
)
def test_video_does_not_capture_on_success(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    video: RecordingOption,
) -> None:
    """
    Helper to verify that with video set to ``RecordingOption.RETAIN_ON_FAILURE`` or ``RecordingOption.OFF``, the
    output is not captured when the test succeeds.
    """
    playwright_mt.video = video
    visit_counter_page(playwright_mt, web_server)


@pytest.mark.parametrize(
    "video",
    [
        RecordingOption.OFF,
    ],
)
def test_video_does_not_capture_on_failure(
    playwright_mt: PlaywrightMTFixture,
    web_server: WebServer,
    video: RecordingOption,
) -> None:
    """
    Helper to verify that with video set to ``RecordingOption.OFF``, the output is not captured when the test fails.
    """
    playwright_mt.video = video
    visit_counter_page(playwright_mt, web_server)
    pytest.fail("Supposed to fail")


def visit_counter_page(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Visit the counter page of the webserver a few times in a newly created Playwright instance.

    This is the common, repetitive task performed by all the tests in this module. The difference is in how they
    configure video recording and whether the test succeeds or fails.

    :param playwright_mt: The ``PlaywrightMTFixture`` for the test.
    :param web_server: The ``WebServer`` to visit.
    """
    playwright_mt.slowmo = 50
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_context().new_page()
        page.goto(f"{web_server.url}counter")
        page.get_by_role("link", name="Increment again").click()
        page.get_by_role("link", name="Increment again").click()
        page.get_by_role("link", name="Increment again")
