"""
Summarize Black runs to users.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Union

from click import style

from black.output import err, out

ReportType = Union["JunitReport", "Report"]

class Changed(Enum):
    NO = 0
    CACHED = 1
    YES = 2


class NothingChanged(UserWarning):
    """Raised when reformatted code is the same as source."""


@dataclass
class Report:
    """Provides a reformatting counter. Can be rendered with `str(report)`."""

    check: bool = False
    diff: bool = False
    quiet: bool = False
    verbose: bool = False
    change_count: int = 0
    same_count: int = 0
    failure_count: int = 0

    def done(self, src: Path, changed: Changed) -> None:
        """Increment the counter for successful reformatting. Write out a message."""
        if changed is Changed.YES:
            reformatted = "would reformat" if self.check or self.diff else "reformatted"
            if self.verbose or not self.quiet:
                out(f"{reformatted} {src}")
            self.change_count += 1
        else:
            if self.verbose:
                if changed is Changed.NO:
                    msg = f"{src} already well formatted, good job."
                else:
                    msg = f"{src} wasn't modified on disk since last run."
                out(msg, bold=False)
            self.same_count += 1

    def failed(self, src: Path, message: str) -> None:
        """Increment the counter for failed reformatting. Write out a message."""
        err(f"error: cannot format {src}: {message}")
        self.failure_count += 1

    def path_ignored(self, path: Path, message: str) -> None:
        if self.verbose:
            out(f"{path} ignored: {message}", bold=False)

    @property
    def return_code(self) -> int:
        """Return the exit code that the app should use.

        This considers the current state of changed files and failures:
        - if there were any failures, return 123;
        - if any files were changed and --check is being used, return 1;
        - otherwise return 0.
        """
        # According to http://tldp.org/LDP/abs/html/exitcodes.html starting with
        # 126 we have special return codes reserved by the shell.
        if self.failure_count:
            return 123

        elif self.change_count and self.check:
            return 1

        return 0

    def __str__(self) -> str:
        """Render a color report of the current state.

        Use `click.unstyle` to remove colors.
        """
        if self.check or self.diff:
            reformatted = "would be reformatted"
            unchanged = "would be left unchanged"
            failed = "would fail to reformat"
        else:
            reformatted = "reformatted"
            unchanged = "left unchanged"
            failed = "failed to reformat"
        report = []
        if self.change_count:
            s = "s" if self.change_count > 1 else ""
            report.append(
                style(f"{self.change_count} file{s} ", bold=True, fg="blue")
                + style(f"{reformatted}", bold=True)
            )

        if self.same_count:
            s = "s" if self.same_count > 1 else ""
            report.append(style(f"{self.same_count} file{s} ", fg="blue") + unchanged)
        if self.failure_count:
            s = "s" if self.failure_count > 1 else ""
            report.append(style(f"{self.failure_count} file{s} {failed}", fg="red"))
        return ", ".join(report) + "."

@dataclass
class JunitReport:
    """Provides a JunitXml formatted string that can be saved to a file"""

    check: bool = False
    diff: bool = False
    quiet: bool = False
    verbose: bool = False
    change_count: int = 0
    same_count: int = 0
    skipped_count: int = 0
    failure_count: int = 0
    error_count: int = 0
    tests: List[str] = field(default_factory=list)

    BODY = """<?xml version="1.0" encoding="utf-8"?>
<testsuite failures="{failed}" errors="{errors}" name="black"
skipped="{skipped}" tests="{combined}">
{tests}</testsuite>"""
    PASS_MSG = """\t<testcase classname="black" file="{file}"
    name="black-{file}"></testcase>\n"""
    SKIP_MSG = """\t<testcase classname="black" file="{file}"
    name="black-{file}">
            <skipped message="{msg}" />
    </testcase>\n"""
    FAIL_MSG = """\t<testcase classname="black" file="{file}"
    name="black-{file}">
            <failure message="{msg}" />
    </testcase>\n"""
    ERROR_MSG = """\t<testcase classname="black" file="{file}"
    name="black-{file}">
            <error message="{msg}" />
    </testcase>\n"""

    def done(self, src: Path, changed: Changed) -> None:
        """Increments the failure_counter if a file would be changed
        and append the testcase section to the tests summary.
        If the File would not be changed because already good formatted
        or not changed since last run.
        It creates a Pass testcase section in the tests summary
        and increment same_counter"""
        if changed is Changed.YES:
            reformatted = "would reformat" if self.check or self.diff else "reformatted"
            if self.verbose or not self.quiet:
                self.tests.append(self.FAIL_MSG.format(file=src, msg=reformatted))
            self.change_count = 1
        else:
            if changed is Changed.NO:
                msg = f"{src} already well formatted, good job."
                self.tests.append(self.PASS_MSG.format(file=src, msg=msg))
            else:
                msg = f"{src} wasn't modified on disk since last run."
                self.tests.append(self.PASS_MSG.format(file=src, msg=msg))
            self.same_count = 1

    def failed(self, src: Path, message: str) -> None:
        """Increment the counter for error reformatting.
        Adds a error Testcase section in tests summary."""
        self.tests.append(
            self.ERROR_MSG.format(
                file=src, msg=f"error: cannot format {src}: {message}"
            )
        )
        self.failure_count = 1

    def path_ignored(self, path: Path, message: str) -> None:
        """Increment the counter for skipped reformatting.
        Adds a skipped Testcase section in tests summary."""
        if self.verbose:
            self.tests.append(
                self.SKIP_MSG.format(file=path, msg=f"{path} ignored: {message}")
            )
            self.skipped_count += 1

    @property
    def return_code(self) -> int:
        """Return the exit code that the app should use.

        This considers the current state of changed files and failures:
        - if there were any failures, return 123;
        - if any files were changed and --check is being used, return 1;
        - otherwise return 0.
        """
        # According to http://tldp.org/LDP/abs/html/exitcodes.html starting with
        # 126 we have special return codes reserved by the shell.
        if self.failure_count:
            return 123

        elif self.change_count and self.check:
            return 1

        return 0

    def __str__(self) -> str:
        """
        Combines the Body with the testcases sections to a JunitXML and returns it.
        """
        combined_tests = (
            self.change_count
            + self.same_count
            + self.failure_count
            + self.skipped_count
        )
        report = [
            self.BODY.format(
                failed=self.change_count,
                errors=self.failure_count,
                skipped=self.skipped_count,
                combined=combined_tests,
                tests="".join(self.tests),
            )
        ]
        return "".join(report)

    def summary(self) -> str:
        """Render a color report of the current state.

        Use `click.unstyle` to remove colors.
        """
        if self.check or self.diff:
            reformatted = "would be reformatted"
            unchanged = "would be left unchanged"
            failed = "would fail to reformat"
        else:
            reformatted = "reformatted"
            unchanged = "left unchanged"
            failed = "failed to reformat"
        report = []
        if self.change_count:
            s = "s" if self.change_count > 1 else ""
            report.append(
                style(f"{self.change_count} file{s} {reformatted}", bold=True)
            )
        if self.same_count:
            s = "s" if self.same_count > 1 else ""
            report.append(f"{self.same_count} file{s} {unchanged}")
        if self.failure_count:
            s = "s" if self.failure_count > 1 else ""
            report.append(style(f"{self.failure_count} file{s} {failed}", fg="red"))
        return ", ".join(report) + "."
