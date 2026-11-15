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
Tests for the collection of artifacts in differently named playwright instances

These tests will be called indirectly via pytester in ``test_artifact_collection.py``
"""

import pytest
from server import WebServer

from pytest_playwright_mt import PlaywrightMTFixture, RecordingOption


@pytest.mark.static_browser
def test_artifacts_for_multiple_instances(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Collect some artifacts for differently names instances.
    """
    playwright_mt.tracing = RecordingOption.ON

    with playwright_mt.create_instance("first") as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")

    with playwright_mt.create_instance("second") as pw:
        pw.chromium().new_page().goto(f"{web_server.url}counter")
