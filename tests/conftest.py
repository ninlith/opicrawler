"""Test configurations."""

import pytest


def pytest_addoption(parser):
    """Add custom command-line options to pytest."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests",
    )
    parser.addoption(
        "--extra",
        action="store",
        help="extra option for tests",
    )


@pytest.fixture(scope="session")
def extra(pytestconfig):
    """Add fixture for the extra option."""
    return pytestconfig.getoption("extra")


def pytest_configure(config):
    """Add integration marker."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test, only run with --integration",
    )


def pytest_collection_modifyitems(config, items):
    """Make integration tests opt-in."""
    # https://til.simonwillison.net/pytest/only-run-integration
    if config.getoption("--integration"):
        return
    skip_integration = pytest.mark.skip(reason="use --integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
