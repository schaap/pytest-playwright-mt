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
Simple conftest for some testing necessities:
  - Introduces the --interactive flag and accompanying fixture
  - Enables the pytester plugin, needed for some of the plugin's tests
  - Enables the original_home fixture, for bypassing pytest's $HOME isolation
"""

from pathlib import Path
from typing import Final

import pytest

pytest_plugins = ["pytester"]

_orig_home: Final[Path] = Path.home()


# ruff: ignore[ARG001]  # This is a hook
def pytest_addoption(parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager) -> None:
    parser.addoption(
        "--interactive",
        help=(
            "Run interactive tests. Some tests require the user to verify some steps, usually by watching what happens "
            "in a headed browser. These tests will only be run on demand, as they can't really be fully automated."
        ),
        default=False,
        action="store_true",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("interactive") and config.getoption("capture") != "no":
        raise RuntimeError("--interactive also requires -s")


@pytest.fixture
def interactive(pytestconfig: pytest.Config) -> None:
    """Request this fixture to automatically skip your test if interactive tests weren't enabled."""

    if not pytestconfig.getoption("interactive", default=False):
        pytest.skip("Interactive tests are not enabled")


@pytest.fixture
def original_home() -> Path:
    """
    The original result of ``Path.home()`` before pytest overwrites it.

    Use with care! There's a reason pytest overwritest it!

    :returns: The actual user's home directory.
    """
    return _orig_home
