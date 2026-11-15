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
Tests for the video feature
"""

from playwright_pytester import PlaywrightPytester, name_matches_test, pytester_artifacts

from pytest_playwright_mt.options import RecordingOption


def test_video_captures(playwright_pytester: PlaywrightPytester) -> None:
    """
    Verify that videos can be captured, and that capture observes the set ``RecordingOption``.
    """

    # The tests that are expected to store a video
    expected_videos = [
        ("test_video_captures_on_success", RecordingOption.ON),
        ("test_video_captures_on_failure", RecordingOption.ON),
        ("test_video_captures_on_failure", RecordingOption.RETAIN_ON_FAILURE),
    ]

    # The tests that are expected to run but must not store a video (their output directory *may* be present)
    expected_no_videos = [
        ("test_video_does_not_capture_on_success", RecordingOption.OFF),
        ("test_video_does_not_capture_on_success", RecordingOption.RETAIN_ON_FAILURE),
        ("test_video_does_not_capture_on_failure", RecordingOption.OFF),
    ]

    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file("_test_video_capture.py")

    result = playwright_pytester.pytester.runpytest_inprocess(*playwright_pytester.params)
    result.assert_outcomes(passed=3, failed=3)

    # Check that all expected videos are there
    for test_name, option in expected_videos:
        assert any(pytester_artifacts(playwright_pytester, test_name, [str(option)], "videos/*/*.webm"))

    # Check that all expected absent videos are not there
    for test_name, option in expected_no_videos:
        assert not any(pytester_artifacts(playwright_pytester, test_name, [str(option)], "videos/*/*"))

    # Check that there are no unexpected output directories. This basically says that every directory in the pytester's
    # output directory must match an entry in the expected videos and expected no-videos lists.
    all_tests = [(test_name, [str(option)]) for test_name, option in [*expected_videos, *expected_no_videos]]
    assert not [
        directory
        for directory in playwright_pytester.output_dir.glob("*")
        if not any(name_matches_test(directory, test_name, params) for test_name, params in all_tests)
    ], "Found unexpected output directories"
