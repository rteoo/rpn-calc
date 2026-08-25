"""Host-platform facts. No Qt: this module has to import on iOS too."""

from __future__ import annotations

import pytest

from rpncalc import host


class TestCurrentHost:
    def test_exactly_one_desktop_or_mobile_os(self):
        flags = (host.is_windows(), host.is_macos(), host.is_linux(), host.is_ios())
        assert sum(flags) == 1

    def test_mobile_implies_no_window_geometry(self):
        if host.is_mobile():
            assert host.remembers_window_geometry() is False
            assert host.has_pointer_hover() is False
        else:
            assert host.remembers_window_geometry() is True
            assert host.has_pointer_hover() is True


class TestIosDetection:
    def test_pep_730_platform(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "ios")
        assert host.is_ios() is True
        assert host.is_macos() is False
        assert host.is_mobile() is True
        assert host.remembers_window_geometry() is False
        assert host.has_pointer_hover() is False

    def test_tvos_is_mobile_apple(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "tvos")
        assert host.is_ios() is True
        assert host.is_mobile() is True

    def test_beeware_style_iphone_machine(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "darwin")
        monkeypatch.setattr(host.platform, "machine", lambda: "iPhone14,2")
        monkeypatch.setattr(host.sysconfig, "get_config_var", lambda name: None)
        assert host.is_ios() is True
        assert host.is_macos() is False

    def test_ipad_machine(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "darwin")
        monkeypatch.setattr(host.platform, "machine", lambda: "iPad13,4")
        monkeypatch.setattr(host.sysconfig, "get_config_var", lambda name: None)
        assert host.is_ios() is True

    def test_python_apple_support_deployment_target(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "darwin")
        monkeypatch.setattr(host.platform, "machine", lambda: "arm64")
        monkeypatch.setattr(
            host.sysconfig,
            "get_config_var",
            lambda name: "15.0" if name == "IPHONEOS_DEPLOYMENT_TARGET" else None,
        )
        assert host.is_ios() is True
        assert host.is_macos() is False

    def test_a_mac_is_not_ios(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "darwin")
        monkeypatch.setattr(host.platform, "machine", lambda: "arm64")
        monkeypatch.setattr(host.sysconfig, "get_config_var", lambda name: None)
        assert host.is_ios() is False
        assert host.is_macos() is True
        assert host.is_mobile() is False


class TestOtherPlatforms:
    def test_windows(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "win32")
        assert host.is_windows() is True
        assert host.is_macos() is False
        assert host.is_ios() is False
        assert host.is_linux() is False
        assert host.is_mobile() is False
        assert host.remembers_window_geometry() is True

    def test_linux(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "linux")
        assert host.is_linux() is True
        assert host.is_windows() is False
        assert host.is_macos() is False
        assert host.is_ios() is False

    def test_android_is_mobile(self, monkeypatch):
        monkeypatch.setattr(host.sys, "platform", "android")
        assert host.is_mobile() is True
        assert host.is_ios() is False
        assert host.remembers_window_geometry() is False
        assert host.has_pointer_hover() is False
