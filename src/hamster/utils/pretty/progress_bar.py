

"""
Fancy Progress Bar
"""
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    SpinnerColumn,
    TimeElapsedColumn,
    MofNCompleteColumn,
    TimeRemainingColumn,
)


# pylint: disable=too-few-public-methods
class ProgressBarFactory:
    """Produces a fancy progress bar"""

    @classmethod
    def get_progress_bar(cls):
        """Returns the progress bar"""
        progress_bar = Progress(
            SpinnerColumn(),
            TextColumn("•"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            BarColumn(),
            TextColumn("• Completed/Total:"),
            MofNCompleteColumn(),
            TextColumn("• Elapsed:"),
            TimeElapsedColumn(),
            TextColumn("• Remaining:"),
            TimeRemainingColumn(),
        )
        return progress_bar
