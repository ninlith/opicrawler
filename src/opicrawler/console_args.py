"""Command-line interface."""

import argparse
import logging
from opicrawler import __version__, PACKAGE_NAME


def parse_arguments():
    """Parse command-line arguments."""

    def formatter(prog):
        """Increase space between parameter and description."""
        return argparse.HelpFormatter(prog, max_help_position=35)

    parser = argparse.ArgumentParser(prog=PACKAGE_NAME, formatter_class=formatter)
    optional = parser._action_groups.pop()  # move to bottom later
    input_group = parser.add_argument_group("input options")
    input_exclusives = input_group.add_mutually_exclusive_group()
    input_exclusives.add_argument(
        "--domains",
        help="input file (or '-' for stdin) with one 'id domain' entry per "
             "line",
        type=argparse.FileType("r", encoding="UTF-8"),
        metavar="FILE",
    )
    input_exclusives.add_argument(
        "--responses",
        help="load previous responses from a pickle file",
        type=argparse.FileType("rb"),
        metavar="PKL",
    )
    input_exclusives.add_argument(
        "--database",
        help="use existing database data",
        action="store_true",
    )
    output_group = parser.add_argument_group("output options")
    output_group.add_argument(
        "--output",
        help="directory to save the generated files (default: %(default)s)",
        default="./output",
        metavar="DIR",
        dest="output",
    )
    fetching_group = parser.add_argument_group("fetching options")
    fetching_group.add_argument(
        "--fetching-concurrency",
        help="maximum simultaneous tasks (default: %(default)s)",
        default=100,
        type=int,
        metavar="INT",
    )
    fetching_group.add_argument(
        "--fetching-spawn-rate",
        help="maximum tasks spawned per second (default: %(default)s)",
        default=50,
        type=int,
        metavar="INT",
    )
    data_extraction_group = parser.add_argument_group("data extraction options")
    data_extraction_group.add_argument(
        "--extraction-concurrency",
        help="maximum simultaneous tasks (default: %(default)s)",
        default=100,
        type=int,
        metavar="INT",
    )
    data_extraction_group.add_argument(
        "--extraction-spawn-rate",
        help="maximum tasks spawned per second (default: %(default)s)",
        default=50,
        type=int,
        metavar="INT",
    )
    data_extraction_group.add_argument(
        "--openai-model",
        help="OpenAI model (default: %(default)s)",
        default="gpt-4o-mini",
        metavar="MODEL",
    )
    data_extraction_group.add_argument(
        "--no-extraction",
        help="omit data extraction",
        action="store_true",
    )
    screenshot_group = parser.add_argument_group("screenshot related options")
    screenshot_group.add_argument(
        "--screenshot-concurrency",
        help="maximum simultaneous tasks (default: %(default)s)",
        default=25,
        type=int,
        metavar="INT",
    )
    screenshot_group.add_argument(
        "--screenshot-spawn-rate",
        help="maximum tasks spawned per second (default: %(default)s)",
        default=10,
        type=int,
        metavar="INT",
    )
    screenshot_group.add_argument(
        "--browser-window",
        help="launch browser window for manual interaction",
        action="store_true",
    )
    screenshot_group.add_argument(
        "--render-wait",
        help="delay in milliseconds before capturing (default: %(default)s)",
        default=2000,
        type=int,
        metavar="MILLISECONDS",
    )
    screenshot_group.add_argument(
        "--filetype",
        help="image file format (default: %(default)s)",
        choices=["png", "jpeg"],
        default="jpeg",
    )
    screenshot_group.add_argument(
        "--resolutions",
        help="page viewport resolutions (default: %(default)s)",
        nargs="+",
        default=["1280x720", "430x932"],
        type=list,
        metavar="WIDTHxHEIGHT",
    )
    screenshot_group.add_argument(
        "--full-page",
        help="capture the entire scrollable area",
        action="store_true",
    )
    screenshot_group.add_argument(
        "--no-screenshots",
        help="omit taking screenshots",
        action="store_true",
    )
    parser._action_groups.append(optional)  # move to bottom
    parser._optionals.title = "other options"
    parser.add_argument(
        "--debug",
        help="enable console DEBUG logging level",
        action="store_const",
        const=logging.DEBUG,
        default=logging.INFO,
        dest="loglevel",
    )
    parser.add_argument(
        "--version",
        help="print version and exit",
        action="version",
        version=__version__,
    )
    return parser.parse_args()
