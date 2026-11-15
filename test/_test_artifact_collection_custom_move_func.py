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
Tests for the use of custom artifact move functions

These tests will be called indirectly via pytester in ``test_artifact_collection.py``
"""

from functools import partial

import pytest
from helpers import move_with_prefix
from server import WebServer

from pytest_playwright_mt import PlaywrightMTFixture, RecordingOption


@pytest.mark.static_browser
def test_custom_move_global(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Nothing special. Uses the global default artifact move function.
    """
    playwright_mt.tracing = RecordingOption.ON
    with playwright_mt.create_instance() as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")


@pytest.mark.artifact_move_func(func=partial(move_with_prefix, prefix="onetestonly_"))
@pytest.mark.static_browser
def test_custom_move_test(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Use a custom artifact move function for the entire test.
    """
    playwright_mt.tracing = RecordingOption.ON
    with playwright_mt.create_instance() as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")

    # Check that the test-wide artifact move function is inherited by the Playwright instance
    assert any(playwright_mt.artifact_temporary_storage_root.glob("*/*/onetestonly_*"))


@pytest.mark.static_browser
def test_custom_move_instance(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Use a custom artifact move function for each Playwright instance.
    """
    playwright_mt.tracing = RecordingOption.ON
    playwright_mt.artifact_move_func = partial(move_with_prefix, prefix="oneinstanceonly_")
    with playwright_mt.create_instance() as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")

    playwright_mt.artifact_move_func = partial(move_with_prefix, prefix="twoinstanceonly_")
    with playwright_mt.create_instance() as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")

    # The Playwright instance specific artifact move functions will only be used for their temporary storage, so we can
    # observe the effect *only* within this test function.
    assert any(playwright_mt.artifact_temporary_storage_root.glob("*/*/oneinstanceonly_*"))
    assert any(playwright_mt.artifact_temporary_storage_root.glob("*/*/twoinstanceonly_*"))
