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
A wrapper around pytester for use with our plugin. Contains some conveniences and ensures that Playwright can find its
installed browsers.
"""

import os
import shutil
import sys
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from pytest_playwright_mt import BrowserName

_BROWSERS_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"


@dataclass(frozen=True)
class PlaywrightPytester:
    """
    A ``pytest.Pytester`` instance prepared for use with Playwright.

    This includes some conveniences, such as an artifact output directory and ``--browser`` forwarding.

    Example usage: ::

        def test_your_stuff(playwright_pytester: PlaywrightTester) -> None:
            playwright_pytester.copy_test_file("sibling_to_this_module.py")
            results = playwright_pytester.runpytest(*playwright_pytester.params)
            # Artifacts from the Pytester test run are now in playwright_pytester.output_dir
    """

    pytester: pytest.Pytester
    """The ``pytest.Pytester`` instance."""

    output_dir: Path
    """
    The output directory passed to ``pytest_playwright_mt`` if ``output_params`` is included when running the
    ``pytest.Pytester``. This is a temporary path, a subdirectory of pytest's ``tmp_path``.
    """

    output_params: Iterable[str]
    """
    Additional parameters to pass to ``pytest.Pytester`` to have ``pytest_playwright_mt`` write all artifacts to
    ``output_dir``. Relies on the ``--output`` option, so do not include these if you wish to test that.
    """

    caller_parent_directory: Path
    """
    The parent directory of the test module that called upon the ``playwright_pytester`` fixture.
    """

    browser_params: Iterable[str]
    """
    Additional parameters to pass to ``pytest.Pytester`` to have ``pytest_playwright_mt`` parametrize for the same
    browser as the calling test is currently parametrized for. This effectively forwards the currently active
    ``--browser`` option.
    """

    @property
    def params(self) -> Iterable[str]:
        """
        All the parameters for ``pytest.Pytester`` rolled together. This is a convenience that just includes the
        specific parameter properties in one ``Iterable``.
        """
        return (*self.output_params, *self.browser_params)

    def copy_local_conftest(self, *, additions: str = "") -> None:
        """
        Copy the ``conftest.py`` from the parent directory of the calling test.

        :param additions: This will be appended to the created ``conftest.py`` file.
        """
        existing_conftest = self.caller_parent_directory / "conftest.py"
        # ruff: ignore[PT018]  # It's more helpful if the two stay together
        assert existing_conftest.exists() and existing_conftest.is_file(), (
            f"No conftest.py was found at {existing_conftest}."
        )
        self.pytester.makeconftest(existing_conftest.read_text() + "\n" + additions + "\n")

    def copy_local_file(self, relative_path: Path | str) -> None:
        """
        Copy a local file as-is to a ``pytester``'s environment.

        :param relative_path: Path to the existing file, relative to the parent directory of the calling test.
        """
        existing_file = self._absolute_file(relative_path)
        dest = self.pytester.path / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(existing_file, dest)

    def copy_test_file(self, relative_path: Path | str) -> None:
        """
        Copy a python file to the ``pytester``'s environment.

        :param relative_path: Path to the existing test file, relative to the parent directory of the calling test.
        """
        existing_test_file = self._absolute_file(relative_path)
        self.pytester.makepyfile(existing_test_file.read_text())

    def _absolute_file(self, relative_path: Path | str) -> Path:
        """
        Determine the absolute path to a local file.

        :param relative_path: Path to the existing file, relative to the parent directory of the calling test.
        :returns: The absolute path to the file.
        """
        relative_path = Path(relative_path)
        assert not relative_path.is_absolute()
        existing_file = self.caller_parent_directory / relative_path
        # ruff: ignore[PT018]  # It's more helpful if the two stay together
        assert existing_file.exists() and existing_file.is_file(), (
            f"File {relative_path} (absolute path: {existing_file}) does not exist."
        )
        return existing_file


@pytest.fixture
def playwright_pytester(
    pytester: pytest.Pytester,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    original_home: Path,
    browser_name: BrowserName,
) -> Generator[PlaywrightPytester, None, None]:
    """
    Setup a ``pytest.Pytester`` instance that has been prepared to work with Playwright running inside it.

    See ``pytest.Pytester`` for more information.

    :yields: The wrapped ``pytest.Pytester`` instance.
    """
    output_dir = tmp_path / "pytester_output"

    # pytester will overwrite $HOME, which is normally used to find the Playwright browsers. Playwright allows explicit
    # specification of a location in the PLAYWRIGHT_BROWSERS_PATH environment variable, removing its dependence on
    # whatever is set in $HOME. If no explicit location is set, yet, we will pass the correct location ourselves.
    playwright_browser_location_override = False
    if _BROWSERS_PATH_ENV not in os.environ:
        if sys.platform in {"linux", "freebsd", "cygwin"}:
            playwright_browser_location = original_home / ".cache" / "ms-playwright"
        elif sys.platform in {"ios", "darwin"}:
            playwright_browser_location = original_home / "Library" / "Caches" / "ms-playwright"
        elif sys.platform in ("win32"):
            playwright_browser_location = original_home / "AppData" / "Local" / "ms-playwright"
        else:
            pytest.fail(
                f"Platform {sys.platform} is not supported for automatic Playwright browser location fixing. "
                f"Please provide the location of the installed Playwright browsers in the {_BROWSERS_PATH_ENV} "
                "environment variable."
            )
        # ruff: ignore[PT018]  # It's more helpful for the user to keep these together
        assert playwright_browser_location.exists() and playwright_browser_location.is_dir(), (
            f"Could not find default Playwright browser location at {playwright_browser_location}. Please provide the "
            f"location of the installed Playwright browsers in the {_BROWSERS_PATH_ENV} environment variable."
        )
        playwright_browser_location_override = True
        os.environ[_BROWSERS_PATH_ENV] = str(playwright_browser_location)

    # Find the file the calling test was defined in. Fall back to this file, if needed.
    node = cast(pytest.Item | pytest.Collector, request.node)
    file_node = node.getparent(pytest.File)  # type: ignore[type-abstract]  # mypy is plain wrong on this one
    caller_parent_directory = file_node.path.parent if file_node is not None else Path(__file__).parent

    try:
        yield PlaywrightPytester(
            pytester=pytester,
            output_dir=output_dir,
            output_params=("--output", str(output_dir)),
            caller_parent_directory=caller_parent_directory,
            browser_params=("--browser", browser_name.value),
        )
    finally:
        if playwright_browser_location_override:
            os.environ.pop(_BROWSERS_PATH_ENV)


def pytester_artifacts(
    playwright_pytester: PlaywrightPytester, test_name: str, parameters: str | Iterable[str], glob: str
) -> list[Path]:
    """
    Find artifacts stored by a specific test run of ``pytest.Pytester``.

    The specification of the test must be unique: it is an error if multiple test directories are found based on the
    test name and parameters. See ``name_matches_test`` for the matching algorithm.

    :param playwright_pytest: The ``PlaywrightPytester`` instance that was used for running the tests. It is assumed
                              that the provided output directory was passed when running the pytester.
    :param test_name: The name of the test for which artifacts are to be collected.
    :param parameters: Parameters that must be set in the parametrized test. This is checked with simple string
                       occurrence, so trivial parameters introduce a high likelihood for ambiguity. Pass an empty list
                       to not match any parameters. Pass ``[""]`` to require the test to be parametrized without
                       actually matching any parameters.
    :param glob: A glob to search for within the test's own output directory.
    :returns: The paths matching the glob. If no test directory was found, an empty list is returned, as well.
    """
    found_dirs = [
        d for d in playwright_pytester.output_dir.glob(f"{test_name}*") if name_matches_test(d, test_name, parameters)
    ]

    if not found_dirs:
        return []

    assert len(found_dirs) == 1, f"Expected at most one output directory, found {len(found_dirs)}"
    return list(found_dirs[0].glob(glob))


def name_matches_test(check: Path, test_name: str, parameters: str | Iterable[str]) -> bool:
    """
    Check whether a given path's ``name`` seems to match a test with specific parametrization.

    This basically tests whether ``check.name`` is in the form ``test_name[param1-param2]``.

    :param check: The path to check.
    :param test_name: The name of the test that should be the start of the name.
    :param parameters: Parameters that must be set in the parametrized test. This is checked with simple string
                       occurrence, so trivial parameters introduce a high likelihood for ambiguity. Pass an empty list
                       to not match any parameters. Pass ``[""]`` to require the test to be parametrized without
                       actually matching any parameters.
    :returns: Whether the name of ``check`` matches the (parametrized) test.
    """
    if isinstance(parameters, str):
        parameters = [parameters]

    # The name must begin with the test name
    if not check.name.startswith(test_name):
        return False

    # The name of the test must exactly match the start of the path's name: it's either completely equal, or immediately
    # followed by the parameters.
    listed_parameters = check.name[len(test_name) :]
    if len(listed_parameters) and listed_parameters[0] != "[":
        return False

    # If there are no parameters, we don't test for them
    if not parameters:
        return True

    # We have parameters to test for, the test must be parametrized
    if len(listed_parameters) == 0:
        return False

    # Each parameter must be contained in the name.
    # Simple string occurrence is sufficient for the parameters we actually use.
    return all(parameter in listed_parameters for parameter in parameters)
