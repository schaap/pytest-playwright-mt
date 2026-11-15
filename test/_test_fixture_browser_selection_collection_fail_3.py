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
A test for browser selection that fails during the collection phase due to incompatible markers.

These tests will be called indirectly via pytester in ``test_fixture.py``
"""

import pytest

from pytest_playwright_mt import BrowserName, PlaywrightMTFixture


@pytest.mark.static_browser
@pytest.mark.skip_browser(BrowserName.FIREFOX)
def test_default_browser_static_and_skip_fail(playwright_mt: PlaywrightMTFixture) -> None:
    """
    Helper to test the ``static_browser`` and ``skip_browser`` markers. This test fails on having both.
    """


def test_detects_failure_by_succeeding() -> None:
    """
    Detector test: this test will only show up in the statistics when the collection phase succeeds, which is exactly
    where the above test is expected to fail.
    """
