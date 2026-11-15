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
Tests for the primary pytest fixture, ``playwright_mt``.
"""

from pathlib import Path

import pytest
from playwright_pytester import PlaywrightPytester, name_matches_test, pytester_artifacts

from pytest_playwright_mt import BrowserName, PlaywrightMTFixture, RecordingOption


def test_fixture(playwright_mt: PlaywrightMTFixture) -> None:
    """
    Test that a ``PlaywrightMTFixture`` instance can be obtained via the fixture.
    """
    assert isinstance(playwright_mt, PlaywrightMTFixture)
    # Check for the only expected default value we can be sure of
    assert not playwright_mt.additional_browser_context_args


@pytest.mark.parametrize(
    ("arguments", "member_name", "expected_member_value"),
    [
        ([], "headed", False),
        (["--headed"], "headed", True),
        ([], "browser_channel", None),
        (["--browser-channel", ""], "browser_channel", None),
        (["--browser-channel", "does-not-exist"], "browser_channel", '"does-not-exist"'),
        ([], "slowmo", 0),
        (["--slowmo", "0"], "slowmo", 0),
        (["--slowmo", "100"], "slowmo", 100),
        ([], "device", None),
        (["--device", ""], "device", None),
        (["--device", "iphone"], "device", '"iphone"'),
        ([], "tracing", RecordingOption.OFF),
        (["--tracing", RecordingOption.OFF.value], "tracing", RecordingOption.OFF),
        (["--tracing", RecordingOption.ON.value], "tracing", RecordingOption.ON),
        (
            ["--tracing", RecordingOption.RETAIN_ON_FAILURE.value],
            "tracing",
            RecordingOption.RETAIN_ON_FAILURE,
        ),
        ([], "video", RecordingOption.OFF),
        (["--video", RecordingOption.OFF.value], "video", RecordingOption.OFF),
        (["--video", RecordingOption.ON.value], "video", RecordingOption.ON),
        (["--video", RecordingOption.RETAIN_ON_FAILURE.value], "video", RecordingOption.RETAIN_ON_FAILURE),
        ([], "screenshot", RecordingOption.OFF),
        (["--screenshot", RecordingOption.OFF.value], "screenshot", RecordingOption.OFF),
        (["--screenshot", RecordingOption.ON.value], "screenshot", RecordingOption.ON),
        (["--screenshot", RecordingOption.RETAIN_ON_FAILURE.value], "screenshot", RecordingOption.RETAIN_ON_FAILURE),
        ([], "full_page_screenshot", False),
        (["--full-page-screenshot"], "full_page_screenshot", True),
    ],
)
@pytest.mark.static_browser
def test_fixture_configuration(
    *,
    playwright_pytester: PlaywrightPytester,
    arguments: list[str],
    member_name: str,
    expected_member_value: str | bool | RecordingOption | None,
) -> None:
    """
    Test that a ``PlaywrightMTFixture`` can be obtained via the fixture, with configuration provided on the command line

    :param arguments: Command line options to inject
    :param member_name: The name of the member of ``PlaywrightMTFixture`` to inspect
    :param expected_member_value: The expected value of the inspected member
    """
    # The test file needs construction, as somehow sending all the data to the subprocess would be quite the burden
    playwright_pytester.pytester.makepyfile(
        "import pytest\n"
        "from pytest_playwright_mt.options import RecordingOption\n"
        "from pytest_playwright_mt.playwright_mt_fixture import PlaywrightMTFixture\n"
        "@pytest.mark.static_browser\n"
        "def test_fixture_configuration_option(playwright_mt: PlaywrightMTFixture) -> None:\n"
        f'    assert getattr(playwright_mt, "{member_name}") == {expected_member_value}\n'
        "    with playwright_mt.create_instance() as pw:"
        f'        assert getattr(pw, "{member_name}") == {expected_member_value}\n'
    )

    result = playwright_pytester.pytester.runpytest_inprocess(*arguments)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    "browsers",
    [
        [],  # No --browser
        *[[browsername] for browsername in BrowserName],  # A single --browser, try each browser
        list(BrowserName),  # All browsers passed via --browser in one pytest call
    ],
)
@pytest.mark.static_browser
def test_browser_selection(playwright_pytester: PlaywrightPytester, browsers: list[BrowserName]) -> None:
    """
    Test that browser selection using the ``--browser`` command line argument works correctly.
    """
    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file(Path("_test_fixture_browser_selection.py"))

    # Construct our expectations based on the browsers we'll be passing.
    # Tuples:
    #   - test name
    #   - parametrized browser
    #   - mapping from expected artifact filename to expected contents (only for expected_pass)
    expected_pass: list[tuple[str, BrowserName, dict[str, str]]] = [
        # pytest.mark.static_browser marked tests are always 'parametrized' with the default browser only
        ("test_default_browser_static", BrowserName.CHROMIUM, {}),
    ]
    expected_skip: list[tuple[str, BrowserName]] = []
    expected_fail: list[tuple[str, BrowserName]] = [
        # pytest.mark.static_browser marked tests are always 'parametrized' with the default browser only
        ("test_default_browser_static_fail", BrowserName.CHROMIUM),
    ]

    for browser in browsers or [BrowserName.CHROMIUM]:
        will_run: dict[str, bool | type[Exception]] = {}
        will_run_silent: dict[str, bool | type[Exception]] = {}  # Will not produce any artifacts

        # Decide for each test in ``_test_fixture_browser_selection.py`` whether we expect it to:
        #   - run (True)
        #   - skip (False)
        #   - fail (Exception)
        will_run["test_default_browser_explicit"] = True
        will_run["test_default_browser_implict"] = True
        will_run["test_default_browser_skip_firefox"] = browser is not BrowserName.FIREFOX
        will_run["test_default_browser_skip_chromium"] = browser is not BrowserName.CHROMIUM
        will_run["test_default_browser_only_firefox"] = browser is BrowserName.FIREFOX
        will_run["test_default_browser_only_chromium"] = browser is BrowserName.CHROMIUM
        will_run["test_default_browser_always_skip"] = False
        will_run["test_default_browser_multiskip_combined"] = browser not in {BrowserName.CHROMIUM, BrowserName.FIREFOX}
        will_run["test_default_browser_multiskip_stacked"] = browser not in {BrowserName.CHROMIUM, BrowserName.FIREFOX}
        # test_default_browser_static is not parametrized
        # test_default_browser_static_fail is not parametrized
        will_run_silent["test_default_browser_mixed"] = True
        will_run_silent["test_default_browser_mixed_fail"] = Exception
        will_run["test_default_browser_mixed_and_only"] = browser is BrowserName.FIREFOX
        will_run["test_default_browser_mixed_and_skip"] = browser is not BrowserName.FIREFOX

        # Expand will_run and will_run-silent to tuples in the expected_ lists
        expected_pass.extend((
            *(
                (test_name, browser, {"launched_browser": browser.value})
                for test_name, runs in will_run.items()
                if runs is True
            ),
            *((test_name, browser, {}) for test_name, runs in will_run_silent.items() if runs is True),
        ))
        expected_skip.extend((
            *((test_name, browser) for test_name, runs in will_run.items() if runs is False),
            *((test_name, browser) for test_name, runs in will_run_silent.items() if runs is False),
        ))
        expected_fail.extend((
            *((test_name, browser) for test_name, runs in will_run.items() if runs is Exception),
            *((test_name, browser) for test_name, runs in will_run_silent.items() if runs is Exception),
        ))

    # Run pytester with the given browsers
    result = playwright_pytester.pytester.runpytest(
        *playwright_pytester.output_params,
        *(argument for browser in browsers for argument in ("--browser", browser.value)),
    )
    result.assert_outcomes(passed=len(expected_pass), skipped=len(expected_skip), failed=len(expected_fail))

    # Check that all expected files are there, and have the expected contents
    for test_name, browser, files in expected_pass:
        for filename, contents in files.items():
            found_files = pytester_artifacts(
                playwright_pytester, test_name, [str(browser)] if browser else [], filename
            )
            assert found_files[0].read_text() == contents

    # Check that all expected absent files are not there
    for test_name, browser in expected_skip:
        assert not any(pytester_artifacts(playwright_pytester, test_name, [str(browser)] if browser else [], "*"))

    # Check that there are no unexpected output directories. This basically says that every directory in the pytester's
    # output directory must match an entry in the lists of expected tests.
    all_tests = [
        *[(test_name, [str(browser)]) for test_name, browser, _ in expected_pass],
        *[(test_name, [str(browser)]) for test_name, browser in expected_skip + expected_fail],
    ]
    assert not [
        directory
        for directory in playwright_pytester.output_dir.glob("*")
        if not any(name_matches_test(directory, test_name, params) for test_name, params in all_tests)
    ], "Found unexpected output directories"


@pytest.mark.parametrize(
    ("test_file"),
    [
        Path("_test_fixture_browser_selection_collection_fail_1.py"),
        Path("_test_fixture_browser_selection_collection_fail_2.py"),
        Path("_test_fixture_browser_selection_collection_fail_3.py"),
    ],
)
@pytest.mark.static_browser
def test_browser_marker_incompatibilities(playwright_pytester: PlaywrightPytester, test_file: Path) -> None:
    """
    Verify that some combinations of markers are not allowed.
    """
    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file(test_file)
    result = playwright_pytester.pytester.runpytest(*playwright_pytester.output_params)
    result.assert_outcomes(errors=1)
