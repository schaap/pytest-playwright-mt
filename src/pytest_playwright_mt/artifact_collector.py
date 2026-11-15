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
Artifact collector

This module contains the ``ArtifactCollector`` class, where artifacts from Playwright browsers can be registered for
securing after the test has finished.

A child collector can be obtained, which will secure its artifacts to an intermediate location and then register those
intermediately secured artifacts with its parent collector for later, further securing. Child collectors are
intended to be used for per-thread ``PlaywrightMT`` instances, while the main collector spans the entire test.

The fixture to obtain the main collector and attach it to the pytest.Item for the test is also included, as well as
the pytest hook that will secure the artifacts registered in that main collector after the test has finished.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from contextlib import suppress
from os import PathLike
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, NamedTuple, cast

import pytest

from pytest_playwright_mt.options import RecordingOption

if TYPE_CHECKING:
    from collections.abc import Generator

_OUTPUT_OPTION: Final[str] = "--output"
_DEFAULT_OUTPUT_LOCATION: Final[Path] = Path("test-results/")

_ARTIFACT_MOVE_FUNC_MARKER: Final[str] = "artifact_move_func"

_ITEM_ARTIFACT_COLLECTOR_ATTR: Final[str] = "playwright_mt_articact_collector"


class _ArtifactData(NamedTuple):
    """Data about a single artifact."""

    location: Path
    """The current location of the artifact."""

    partial_location: Path
    """The additional relative path to use when securing the artifact."""

    option: RecordingOption
    """When the artifact is to be secured.s"""


class ArtifactCollector:
    """
    Collect and secure artifacts from Playwright browsers.
    """

    default_artifact_move_func: ClassVar[Callable[[Path, Path], PathLike[str] | str | None]] = shutil.move
    """
    The function to use for moving artifacts in ``ArtifactCollector`` instances. This has the same semantics as
    ``shutil.move``, which is also its default value.

    This class variable provides the default for all instances. If you need to use a different function in a specific
    test, then add the ``pytest.mark.artifact_move_func`` on your test, instead. If you need to use a different function
    for only a specific Playwright instance within a test, you can set ``PlaywrightMTFixture.artifact_move_func`` before
    creating that instance.
    """

    def __init__(
        self,
        *,
        parent: ArtifactCollector | None = None,
        artifact_move_func: Callable[[Path, Path], PathLike[str] | str | None] | None = None,
    ) -> None:
        """
        Create a new ``ArtifactCollector``.

        :param parent: If set, artifacts that have been secured by this ``ArtifactCollector`` will be registered with
                       the parent ``ArtifactCollector`` for later securing to another location. See
                       ``create_child_collector`` for more information.
        :param artifact_move_func: The function to call for moving around artifacts in the artifact collector. This has
                                   the same semantics as ``shutil.move``. It defaults to
                                   ``ArtifactCollector.default_artifact_move_func``.
        """

        self._parent = parent
        """The parent artifact collector, if any."""

        self._artifacts: list[_ArtifactData] = []
        """The list of registered artifacts."""

        self._destination_root: Path | None = None
        """The root folder to which the artifacts will be secured, if set."""

        self._artifact_move_func: Callable[[Path, Path], PathLike[str] | str | None] = (
            artifact_move_func or ArtifactCollector.default_artifact_move_func
        )
        """The function to use when moving artifacts."""

        self._lock = Lock()
        """Lock for synchronizing this class."""

    def add_artifact(self, location: Path, filename: Path, option: RecordingOption) -> None:
        """
        Add an artifact to this test.

        :param location: The file or directory that needs to be secured. This does not need to exist, yet, and may not
                         even exist when the test finishes (nothing will be secured, then).
        :param filename: The final name of the artifact when secured. This must be a relative path and may be prefixed
                         with directories.
        :param option: When the artifact is to be stored in the test results. If this is ``RecordingOption.OFF`` then
                       the artifact trace is simply not registered.
        """
        if filename.is_absolute():
            raise ValueError("The filename must not be an absolute path.")
        with self._lock:
            if option is RecordingOption.OFF:
                return
            self._artifacts.append(_ArtifactData(location, filename, option))

    def create_child_collector(
        self, artifact_move_func: Callable[[Path, Path], PathLike[str] | str | None] | None = None
    ) -> ArtifactCollector:
        """
        Create a child artifact collector that collects a child collection of artifacts.

        This is particularly useful when the child collection needs an additional intermediate storage location. The
        plugin itself is the primary user of child collectors, creating a child artifact collector for each Playwright
        instance from its own main collector.

        :param artifact_move_func: The function to call for moving around artifacts in the child artifact collector.
                                   This has the same semantics as ``shutil.move``. Defaults to the same function as
                                   is used in this instance.
        :returns: The new artifact collector that will add artifacts to a separate collection.
        """
        with self._lock:
            return ArtifactCollector(parent=self, artifact_move_func=artifact_move_func or self._artifact_move_func)

    def set_destination_root(self, root: Path) -> None:
        """
        Set the root folder to which the artifacts will be secured.

        :param root: The root folder to which the artifacts will be secured.
        """
        with self._lock:
            self._destination_root = root

    def _secure_artifact(
        self, root: Path, artifact: _ArtifactData, result: Literal["passed", "failed", "skipped"] | None
    ) -> Path | None:
        """
        Secure a single artifact previously collected by this ``ArtifactCollector``.

        The caller is responsible for attaining ``self._lock`` before calling this.

        :param root: The root folder to which the artifacts will be secured.
        :param artifact: The artifact to secure.
        :param result: If set, the result of the test. Artifacts may be removed depending on the test result and their
                       recording option.
        :returns: The full path to which the artifact was secured, or None if the artifact was not secured.
        """
        # Skip a pre-registered but non-existing artifact
        if not artifact.location.exists():
            return None

        # Delete the artifact if needed when the result is known
        delete = False
        if result == "passed":
            delete = artifact.option in {RecordingOption.OFF, RecordingOption.RETAIN_ON_FAILURE}
        elif result == "failed":
            delete = artifact.option == RecordingOption.OFF
        if delete:
            with suppress(Exception):
                if artifact.location.is_dir():
                    shutil.rmtree(artifact.location)
                else:
                    artifact.location.unlink()
                # We will suppress any Exception here. Removing is strictly best-effort.
            return None

        # Construct the destination and move the artifact
        destination = root / artifact.partial_location
        return self._move_artifact(artifact.location, destination)

    def _move_artifact(self, source: Path, destination: Path) -> Path:
        """
        Move a single artifact file or directory.

        Moving directories onto existing directories will merge them. Moving a file onto an existing directory will
        fail: the file will not be moved *into* the directory and the directory will not be removed to be 'overwritten'
        by the file.

        The caller is responsible for attaining ``self._lock`` before calling this.

        :param source: The source file or directory to move.
        :param destination: The location to move the source to.
        :returns: The actual destination after moving.
        """
        if destination.exists() and destination.is_dir():
            if not source.is_dir():
                raise RuntimeError(
                    f"Attempted to secure a file ({source}) to a location that is an existing directory "
                    f"({destination}). Preventing the move of the file *into* the directory and refusing to remove an "
                    "entire directory to 'overwrite' it with a file."
                )
            # Merge the contents of the two directories
            for child in source.iterdir():
                self._move_artifact(child, destination / child.name)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = Path(self._artifact_move_func(source, destination) or destination)
        return destination

    def secure_artifacts(
        self, root: Path | None, *, result: Literal["passed", "failed", "skipped"] | None = None
    ) -> None:
        """
        Secure all artifacts previously collected by this ArtifactCollector.

        :param root: The root folder to which the artifacts will be secured. May be ``None`` if a root folder has
                     previously been set via ``set_destination_root``.
        :param result: If set, the result of the test. Artifacts may be removed depending on the test result and their
                       recording option.
        """
        with self._lock:
            if root is None:
                root = self._destination_root
            if root is None:
                raise RuntimeError(
                    "A destination for securing the artifacts to must be set, either via set_destination_root or by "
                    "passing the root argument to this method."
                )
            root.mkdir(parents=True, exist_ok=True)

            for artifact in self._artifacts:
                secured_location = self._secure_artifact(root, artifact, result)

                # Register the artifact with the parent artifact collector, if any
                if secured_location is not None and self._parent is not None:
                    self._parent.add_artifact(secured_location, artifact.partial_location, artifact.option)
            self._artifacts = []

    @staticmethod
    def from_request_node(node: pytest.Item | pytest.Collector) -> ArtifactCollector | None:
        """
        Attempt to obtain the ``ArtifactCollector`` attached to a pytest node.

        :param node: The node to obtain the ``ArtifactCollector`` from.
        :returns: The ArtifactCollector that was attached to ``node``, or ``None``.
        """
        return getattr(node, _ITEM_ARTIFACT_COLLECTOR_ATTR, None)


@pytest.fixture
def artifact_collector(request: pytest.FixtureRequest) -> ArtifactCollector:
    """
    Fixture to obtain the ``ArtifactCollector`` for the current test.
    """
    request_node = cast(pytest.Collector | pytest.Item, request.node)

    # Check whether the test declares a different artifact move function to use
    artifact_move_func: Callable[[Path, Path], PathLike[str] | str | None] | None = None
    marker = request_node.get_closest_marker(_ARTIFACT_MOVE_FUNC_MARKER)
    if marker:
        if not callable(marker.kwargs["func"]):
            raise ValueError(
                f"The value to pytest.mark.{_ARTIFACT_MOVE_FUNC_MARKER}(func=) must be a function matching the "
                "signature of shutil.move"
                # Note that the check is not complete: we don't actually check the full signature. It'd be quite the
                # reflection effort with very, very little gain over letting the developer just run into it.
            )
        artifact_move_func = cast(Callable[[Path, Path], PathLike[str] | str | None], marker.kwargs["func"])

    artifact_collector = ArtifactCollector(artifact_move_func=artifact_move_func)

    # Set the location where artifacts for this test will eventually be stored
    output_location = cast(Path, request.config.getoption(_OUTPUT_OPTION)) or _DEFAULT_OUTPUT_LOCATION
    artifact_collector.set_destination_root(output_location / Path(request_node.name))

    # Attach the artifact collector to the test node, so it can be obtained in the hook below.
    setattr(request_node, _ITEM_ARTIFACT_COLLECTOR_ATTR, artifact_collector)

    return artifact_collector


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[Any]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """
    pytest hook

    The first time that the final result of running a test is known, is when the report for that test is made: this
    hook. This is the point that we can secure all the artifacts to their final location, taking the result of the test
    into account (this is needed for ``RecordingOption.RETAIN_ON_FAILURE``).
    """
    report = yield

    # Only operate after the call phase, which is when the test function has actually been run
    if call.when != "call":
        return report

    # See if there's an artifact collector attached to the node. If so, secure its artifacts.
    artifact_collector = ArtifactCollector.from_request_node(item)
    if artifact_collector is not None:
        artifact_collector.secure_artifacts(root=None, result=report.outcome)

    return report


@pytest.hookimpl(specname="pytest_addoption")
# ruff: ignore[ARG001]  # This is a hook
def pytest_addoption(parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager) -> None:
    """
    pytest hook

    Add `ArtifactCollector` command line options for pytest.
    """
    group = parser.getgroup("artifact-collector", "Artifact Collector")

    group.addoption(
        _OUTPUT_OPTION,
        default=_DEFAULT_OUTPUT_LOCATION,
        type=Path,
        help=f"Directory for artifacts produced by tests, defaults to {_DEFAULT_OUTPUT_LOCATION}.",
    )


@pytest.hookimpl(specname="pytest_configure")
def pytest_configure(config: pytest.Config) -> None:
    """
    pytest hook

    During this hook configuration can be added. The marker for the ``ArtifactCollector`` is added here.
    """

    config.addinivalue_line(
        "markers",
        (
            f"{_ARTIFACT_MOVE_FUNC_MARKER}(func=func): provide the default artifact move function for the test. The "
            "single keyword argument func= must a valid value for ArtifactCollect.default_artifact_move_func."
        ),
    )
