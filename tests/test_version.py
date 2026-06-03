"""The wrapper exposes a single, well-formed version string."""

import re

from claude_wrapper import __version__


def test_version_is_semver_like():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_health_reports_version():
    # claude_health returns wrapper_version from the package __version__.
    from claude_wrapper import server
    assert server.__version__ == __version__
