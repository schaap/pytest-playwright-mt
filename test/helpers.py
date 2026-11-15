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
Generic helpers for tests
"""

import shutil
from os import PathLike
from pathlib import Path
from typing import Final

import pytest

_ASK_CONFIRMATION_ATTEMPTS: Final[int] = 5


def ask_confirmation(question: str) -> bool:
    """
    Ask the human tester for confirmation.

    When calling this, be sure to request the ``interactive`` fixture in your test.

    :param question: The yes/no question to pose to the tester.
    :returns: True iff the tester replied with Yes or a similar positive answer.
    """
    accept = ("yes", "yarp", "good", "okay", "ok", "y", "true", "1")
    reject = ("no", "narp", "bad", "n", "false", "0")
    instructions = "Please answer Yes or No and press Enter to confirm your answer."
    # ruff: ignore[T201]  # Print is very intentional, here
    print("\n\n== INTERACTIVE QUESTION ==\n\n" + question)
    for _ in range(_ASK_CONFIRMATION_ATTEMPTS):
        answer = input(instructions + "\n")
        if answer.lower() in accept:
            return True
        if answer.lower() in reject:
            return False
        # ruff: ignore[T201]  # Print is very intentional, here
        print(f"Your answer was not recognized: {answer}")
    pytest.fail("You did not provide a recognizable answer.")


def move_with_prefix(src: PathLike[str] | str, dest: PathLike[str] | str, *, prefix: str = "prefixed_") -> Path:
    """
    Move a file, like ``shutil.move``, but prefix the destination with ``prefixed_``.

    :param src: The source file or directory to move.
    :param dest: The destination to move the file or directory to.
    :returns: The final destination.
    """
    dest = Path(dest)
    dest = dest.parent / f"{prefix}{dest.name}"
    return Path(shutil.move(src, dest) or dest)
