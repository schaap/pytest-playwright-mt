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
conftest to import the fixtures
This mainly prevents a lot of linter errors

The official recommendation by pytest is to write fixtures in a conftest altogether. We choose to keep them more
organized, but then import them here.
"""

from playwright_pytester import playwright_pytester  # ruff: ignore[F401]  # Fixtures
from server import web_server  # ruff: ignore[F401]  # Fixtures

from pytest_playwright_mt import browser_name, playwright_mt  # ruff: ignore[F401]  # Fixtures
