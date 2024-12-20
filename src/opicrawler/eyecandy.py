"""Eye candy."""

import atexit
import rich
from rich.console import Group
from rich.live import Live
from rich.padding import Padding
from rich.progress import Progress, BarColumn, SpinnerColumn, MofNCompleteColumn
from rich.text import Text


# Source code for Progress and BarColumn:
# https://github.com/Textualize/rich/blob/master/rich/progress.py

class CustomProgress(Progress):
    """Extended Progress that supports DualBarColumn."""

    def reset(self, task_id, **kwargs):
        """Extend the reset method to support a secondary progress bar."""
        task = self._tasks[task_id]
        task.fields["secondary_progress"] = 0
        super().reset(task_id, **kwargs)

    def update(self, task_id, advance=0, advance_secondary=0, **kwargs):
        """Extend the update method to support a secondary progress bar."""
        task = self._tasks[task_id]
        if advance_secondary:
            task.fields["secondary_progress"] = min(
                task.fields.get("secondary_progress", 0) + advance_secondary,
                task.total
            )
        super().update(task_id, advance=advance, **kwargs)


class DualBarColumn(BarColumn):
    """Extended BarColumn with a secondary progress bar."""

    def render(self, task):
        bar_length = self.bar_width
        primary_completed = task.completed
        secondary_completed = task.fields.get("secondary_progress", 0)
        primary_ratio = primary_completed/task.total if task.total else 0
        secondary_ratio = secondary_completed/task.total if task.total else 0
        primary_length = int(bar_length*primary_ratio)
        secondary_length = max(
            0,
            int(bar_length*secondary_ratio) - primary_length,
        )
        return Text.assemble(
            (f"{'━'*primary_length}", "magenta"),
            (f"{'─'*secondary_length}", "grey23"),
            (f"{'╶'*(bar_length - primary_length - secondary_length)}", "grey23"),
        )


def setup_eyecandy():
    """Compose a live display with a padded render group."""
    (default_description, _default_bar, default_completion,
        default_estimation) = Progress.get_default_columns()
    progress_bar = CustomProgress(
        SpinnerColumn(finished_text="[green]⠿[/]"),
        default_description,
        DualBarColumn(),
        default_completion,
        MofNCompleteColumn(),
        default_estimation,
    )
    progress_status = Progress(
        SpinnerColumn(),
        default_description,
    )
    progress_group = Padding(
        Group(
            progress_status,
            progress_bar,
        ),
        (1, 2),
    )
    live_display = Live(progress_group, transient=True, refresh_per_second=10)
    live_display.start()
    atexit.register(lambda: rich.get_console().show_cursor(show=True))
    return progress_bar, progress_status, live_display
