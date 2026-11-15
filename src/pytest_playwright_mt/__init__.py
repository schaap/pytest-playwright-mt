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
The primary imports of ``pytest_playwright_mt``

Primary usage of the plugin begins with the ``playwright_mt`` fixture: ::

    from pytest_playwright_mt import PlaywrightMTFixture, playwright_mt


    def test_my_website(playwright_mt: PlaywrightMTFixture) -> None:
        with playwright_mt.create_instance() as pw:
            browser = pw.launch()
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://site.my.test")
"""

from pytest_playwright_mt.artifact_collector import ArtifactCollector, artifact_collector
from pytest_playwright_mt.instrumentation import context_name, page_name
from pytest_playwright_mt.options import BrowserName, RecordingOption
from pytest_playwright_mt.playwright_mt import PlaywrightMT
from pytest_playwright_mt.playwright_mt_fixture import PlaywrightMTFixture, browser_name, playwright_mt

__all__ = [
    "ArtifactCollector",
    "BrowserName",
    "PlaywrightMT",
    "PlaywrightMTFixture",
    "RecordingOption",
    "artifact_collector",
    "browser_name",
    "context_name",
    "page_name",
    "playwright_mt",
]
