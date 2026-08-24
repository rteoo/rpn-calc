"""Shared test setup.

Two things have to be true for the whole session, not just for the tests that
remember to ask:

- Qt runs offscreen, so a test run never opens a window on somebody's desktop.
- QSettings writes to a temporary directory. `rpncalc.__main__.start` sets the
  real organisation and application names, so without this a startup test would
  read and overwrite the user's actual saved window geometry and modes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolate_qt_settings(tmp_path_factory):
    """Keep every QSettings write inside the test run."""
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path_factory.mktemp("qsettings")),
    )
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.SystemScope,
        str(tmp_path_factory.mktemp("qsettings-system")),
    )


@pytest.fixture(scope="session")
def qt_app(isolate_qt_settings):
    """The one QGuiApplication a process is allowed to have."""
    app = QGuiApplication.instance() or QGuiApplication([])
    QCoreApplication.setOrganizationName("rpncalc-tests")
    QCoreApplication.setApplicationName("suite")
    return app


@pytest.fixture
def clean_settings(qt_app):
    """A blank slate for anything that reads saved state at construction."""
    QSettings().clear()
    QSettings().sync()
    return QSettings()
