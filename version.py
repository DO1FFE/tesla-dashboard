import os
import subprocess


def get_version():
    """Return a version string based on the Git commit count."""
    try:
        root = os.path.dirname(os.path.abspath(__file__))
        count = (
            subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=root)
            .decode()
            .strip()
        )
        return f"1.0.{count}"
    except Exception:
        return "0.0.0"
