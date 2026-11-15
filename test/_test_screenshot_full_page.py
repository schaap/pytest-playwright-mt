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
Tests that show a specific page, ready for screenshotting

These tests will be called indirectly via pytester in ``test_screenshot.py``

Note that the two tests are identical. pytester will be called twice, once with full page screenshotting, and once
without. This would work just fine if it were one test, but it's much easier to distinguish between the two runs'
artifacts if the tests that are run have a different name.
"""

import shutil

from playwright.sync_api import ViewportSize
from server import WebServer

from pytest_playwright_mt import PlaywrightMTFixture


def test_screenshot_not_full_page(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Helper to verify that full page screenshots work.
    """
    shutil.copy("index.html", web_server.pages_dir)
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_context(viewport=ViewportSize(width=300, height=300)).new_page()
        page.goto(web_server.url)


def test_screenshot_full_page(playwright_mt: PlaywrightMTFixture, web_server: WebServer) -> None:
    """
    Helper to verify that full page screenshots work.
    """
    shutil.copy("index.html", web_server.pages_dir)
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_context(viewport=ViewportSize(width=300, height=300)).new_page()
        page.goto(web_server.url)
