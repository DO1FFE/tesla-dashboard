"""Netzlose Testumgebung ohne Produktivdaten, Zugangsdaten oder Schreibzugriff."""


def testbefehl(projekt, kopie):
    return [
        "/usr/bin/bwrap", "--unshare-all", "--die-with-parent",
        "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/root",
        "--tmpfs", "/tmp", "--tmpfs", "/run", "--proc", "/proc", "--dev", "/dev",
        "--ro-bind", str(projekt / ".venv"), "/tmp/venv",
        "--bind", str(kopie), "/tmp/pruefung", "--chdir", "/tmp/pruefung",
        "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1",
        "--setenv", "GIT_AUTHOR_NAME", "Dashboard Test",
        "--setenv", "GIT_COMMITTER_NAME", "Dashboard Test",
        "--setenv", "GIT_AUTHOR_EMAIL", "test@example.invalid",
        "--setenv", "GIT_COMMITTER_EMAIL", "test@example.invalid",
        "/tmp/venv/bin/python", "-m", "pytest", "-q",
    ]


# © 2026 Erik Schauer, do1ffe@darc.de
