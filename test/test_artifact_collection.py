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
Tests for the customization of artifact collection.

Note that most of ``ArtifactCollector`` is well exercised and, indirectly, verified by other tests.
"""

import shutil
from pathlib import Path

import pytest
from playwright_pytester import PlaywrightPytester, pytester_artifacts

from pytest_playwright_mt import ArtifactCollector, RecordingOption


@pytest.mark.static_browser
def test_collection_by_instance_name(playwright_pytester: PlaywrightPytester) -> None:
    """
    Verify that the final location where artifacts are collected includes the name provided for the Playwright instance.
    """
    playwright_pytester.copy_local_conftest()
    playwright_pytester.copy_test_file("_test_artifact_collection_multiple_instance.py")
    res = playwright_pytester.pytester.runpytest_inprocess(*playwright_pytester.output_params)
    res.assert_outcomes(passed=1)

    assert any(
        pytester_artifacts(
            # One instance is called "first"
            playwright_pytester,
            "test_artifacts_for_multiple_instances",
            [],
            "traces/*first*",
        )
    )
    assert any(
        pytester_artifacts(
            # The other instance is called "second"
            playwright_pytester,
            "test_artifacts_for_multiple_instances",
            [],
            "traces/*second*",
        )
    )


@pytest.mark.static_browser
def test_custom_artifact_move_functions(playwright_pytester: PlaywrightPytester) -> None:
    """
    Test that custom artifact move functions can be injected at different levels.
    """
    playwright_pytester.copy_local_conftest(
        additions=(
            "from pytest_playwright_mt.artifact_collector import ArtifactCollector\n"
            "import helpers\n"
            # The default artifact move function will be changed to move_with_prefix
            "ArtifactCollector.default_artifact_move_func = helpers.move_with_prefix\n"
        )
    )
    playwright_pytester.copy_local_file("helpers.py")
    playwright_pytester.copy_local_file("playwright_pytester.py")
    playwright_pytester.copy_local_file("server.py")
    playwright_pytester.copy_test_file("_test_artifact_collection_custom_move_func.py")

    # Run pytester in a subprocess, as we will be adjusting global variables.
    res = playwright_pytester.pytester.runpytest_subprocess(*playwright_pytester.output_params)
    res.assert_outcomes(passed=3)
    # Double-check that we haven't inadvertently influenced our own process
    assert ArtifactCollector.default_artifact_move_func == shutil.move

    # Observe that the global customized artifact move function was used
    assert any(pytester_artifacts(playwright_pytester, "test_custom_move_global", [], "traces/prefixed_*"))
    # Observe that the test-specific (via marker) customized artifact move function was used, even for the final step
    assert any(pytester_artifacts(playwright_pytester, "test_custom_move_test", [], "traces/onetestonly_*"))
    # The artifact move function that was only customized on a specific instance did not perform the final move, so we
    # again expect to see the global customized move function in action
    assert any(pytester_artifacts(playwright_pytester, "test_custom_move_instance", [], "traces/prefixed_*"))


def test_add_artifact_recording_off(tmp_path: Path) -> None:
    """
    Test that adding an artifact with ``RecordingOption.OFF`` is allowed and does not secure the artifact.
    """
    source = tmp_path / "src"
    source.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()

    secure_me = source / "secure_me.txt"
    secure_me.write_text("Should be secured")
    ignore_me = source / "ignore_me.txt"
    ignore_me.write_text("Should be ignored")

    artifact_collector = ArtifactCollector()
    artifact_collector.add_artifact(secure_me, Path(secure_me.name), RecordingOption.ON)
    artifact_collector.add_artifact(ignore_me, Path(ignore_me.name), RecordingOption.OFF)
    artifact_collector.secure_artifacts(dest)

    assert (dest / secure_me.name).exists()
    assert not (dest / ignore_me.name).exists()


def test_add_artifact_before_exists(tmp_path: Path) -> None:
    """
    Test that adding an artifact that does not and will not exist is okay.
    """
    source = tmp_path / "src"
    source.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()

    extra_dir = source / "some_dir"
    extra_dir.mkdir()

    artifact_collector = ArtifactCollector()
    artifact_collector.add_artifact(source / "does_not_exist", Path("does_not_exist_1"), RecordingOption.ON)
    artifact_collector.add_artifact(extra_dir / "does_not_exist", Path("does_not_exist_2"), RecordingOption.ON)
    artifact_collector.add_artifact(source / "also" / "does_not_exist", Path("does_not_exist_3"), RecordingOption.ON)
    artifact_collector.secure_artifacts(dest)

    assert not any(dest.iterdir())


def test_directory_as_artifact(tmp_path: Path) -> None:
    """
    Test directories as artifacts. These should be moved in their entirety, possibly merged with existing directory on
    the destination.
    """
    source = tmp_path / "src"
    dest = tmp_path / "dest"

    # The three directories that will be added as artifacts
    artifact_dir_one = Path("artifact_one")
    artifact_dir_two = Path("artifact_two")
    artifact_dir_remove = Path("artifact_three")

    # Set up a somewhat complex hierarchy of artifacts. Artifact directories 'one' and 'two' will be secured to the same
    # location, which should cause them to be merged. Artifact directory 'remove' should be removed, as it's added with
    # RETAIN_ON_FAILURE as recording option and we will secure artifacts as if the test passed.
    artifact_dir_one_sub = artifact_dir_one / "sub"
    artifact_dir_one_sub2 = artifact_dir_one / "sub2"
    artifact_dir_two_sub = artifact_dir_two / "sub"
    artifact_dir_remove_sub = artifact_dir_remove / "sub"

    artifacts = [  # These are expected to be secured
        # The order of artifact1 and artifact1 is significant, indicating that artifact_one/artifact1 will be
        # overwritten by artifact_two/artifact1 when securing the artifacts
        artifact_dir_one_sub / "artifact1",
        artifact_dir_two_sub / "artifact1",
        artifact_dir_one_sub / "artifact2",
        artifact_dir_two_sub / "artifact3",
        artifact_dir_one_sub2 / "artifact4",
        artifact_dir_two / "artifact7",
    ]

    remove_artifacts = [  # These are expected to be removed
        artifact_dir_remove / "artifact5",
        artifact_dir_remove_sub / "artifact6",
    ]

    # Create all the artifacts, the contents of each artifact file is simply its relative path
    for artifact in (*artifacts, *remove_artifacts):
        (source / artifact).parent.mkdir(parents=True, exist_ok=True)
        (source / artifact).write_text(str(artifact))

    # Collect and secure the artifacts
    artifact_collector = ArtifactCollector()
    artifact_collector.add_artifact(source / artifact_dir_one, Path("artifact_dir"), RecordingOption.ON)
    artifact_collector.add_artifact(source / artifact_dir_two, Path("artifact_dir"), RecordingOption.ON)
    artifact_collector.add_artifact(
        source / artifact_dir_remove, artifact_dir_remove, RecordingOption.RETAIN_ON_FAILURE
    )
    artifact_collector.secure_artifacts(dest, result="passed")

    # Calculate expected artifacts, then check that they're all there
    expected_artifacts: dict[Path, str] = {}
    for artifact in artifacts:
        expected_artifact = dest / "artifact_dir" / "/".join(artifact.parts[1:])
        expected_artifacts[expected_artifact] = str(artifact)

    for expected_artifact, expected_contents in expected_artifacts.items():
        assert expected_artifact.read_text() == expected_contents

    # Check that none of the artifacts to be removed have been secured
    for remove_artifact in remove_artifacts:
        assert not (dest / remove_artifact).exists()

    # Check that all artifacts have been removed from source
    for artifact_dir in (artifact_dir_one, artifact_dir_two, artifact_dir_remove):
        assert not artifact_dir.exists()


def test_secure_refuses_to_overwrite_directory(tmp_path: Path) -> None:
    """
    Test that securing artifacts will not overwrite an existing directory with a file.
    """
    source = tmp_path / "src"
    source.mkdir()

    dest = tmp_path / "dest"
    existing = dest / "existing"
    existing.mkdir(parents=True)

    artifact = source / existing.name
    artifact.write_text("This should not be moved")

    artifact_collector = ArtifactCollector()
    artifact_collector.add_artifact(artifact, Path(existing.name), RecordingOption.ON)
    with pytest.raises(RuntimeError):
        artifact_collector.secure_artifacts(dest)


def test_secure_requires_root(tmp_path: Path) -> None:
    """
    Test that attempting to secure artifacts fails when no root directory to secure them to has been provided.
    """
    source = tmp_path / "src"
    source.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()

    artifact = source / "artifact"
    artifact.write_text("This should not be moved")

    artifact_collector = ArtifactCollector()
    artifact_collector.add_artifact(artifact, Path(artifact.name), RecordingOption.ON)
    with pytest.raises(RuntimeError):
        artifact_collector.secure_artifacts(None)


def test_add_artifact_absolute_path(tmp_path: Path) -> None:
    """
    Test that adding an artifact with an absolute path as name fails.
    """
    assert tmp_path.is_absolute()

    dest = tmp_path / "dest"
    dest.mkdir()

    artifact_collector = ArtifactCollector()
    with pytest.raises(ValueError, match="The filename must not be an absolute path"):
        artifact_collector.add_artifact(tmp_path / "src" / "artifact", dest / "artifact", RecordingOption.ON)
