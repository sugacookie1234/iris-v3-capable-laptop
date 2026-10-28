"""Tray close/open/quit behavior and narrow Windows login registration."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest

from iris.desktop.tray import DesktopTray, StartupRegistration


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def emit(self, event=None):
        for handler in self.handlers:
            handler(None, event)


class Component:
    def __init__(self, text=''):
        self.Text = text
        self.Click = Event()
        self.DoubleClick = Event()
        self.Items = SimpleNamespace(Add=lambda item: None)
        self.disposals = 0

    def Dispose(self):
        self.disposals += 1


class Native:
    def __init__(self):
        self.FormClosing, self.FormClosed = Event(), Event()
        self.visible = True
        self.closed = False
        self.WindowState = 'minimized'

    def Show(self):
        self.visible = True

    def Hide(self):
        self.visible = False

    def Activate(self):
        self.activated = True

    def Close(self, reason='user'):
        event = SimpleNamespace(CloseReason=reason, Cancel=False)
        self.FormClosing.emit(event)
        if not event.Cancel:
            self.closed = True
            self.FormClosed.emit()


def fixture():
    native = Native()
    forms = SimpleNamespace(ContextMenuStrip=Component, NotifyIcon=Component, ToolStripMenuItem=Component,
                            ToolStripSeparator=Component, CloseReason=SimpleNamespace(UserClosing='user'),
                            FormWindowState=SimpleNamespace(Minimized='minimized', Normal='normal'))
    startup = SimpleNamespace(value=False)
    startup.enabled = lambda: startup.value
    startup.set_enabled = lambda value: setattr(startup, 'value', value)
    tray = DesktopTray(native, forms, SimpleNamespace(SystemIcons=SimpleNamespace(Information=object())), startup)
    return native, tray, startup


class TrayTests(unittest.TestCase):
    def test_close_hides_open_restores_and_quit_releases_resources(self):
        native, tray, _ = fixture()
        native.Close()
        self.assertFalse(native.visible)
        self.assertFalse(native.closed)
        self.assertTrue(tray.icon.Visible)
        tray.open_item.Click.emit()
        self.assertTrue(native.visible)
        self.assertTrue(native.activated)
        self.assertEqual(native.WindowState, 'normal')
        native.Close()
        tray.icon.DoubleClick.emit()
        self.assertTrue(native.visible)
        tray.quit_item.Click.emit()
        self.assertTrue(native.closed)
        self.assertFalse(tray.icon.Visible)
        self.assertEqual(tray.icon.disposals, 1)
        self.assertEqual(tray.menu.disposals, 1)
        tray.dispose()
        self.assertEqual(tray.icon.disposals, 1)

    def test_shutdown_is_not_cancelled(self):
        native, tray, _ = fixture()
        native.Close('shutdown')
        self.assertTrue(native.closed)
        self.assertTrue(tray.disposed)

    def test_login_startup_is_opt_in_and_reversible(self):
        _, tray, startup = fixture()
        self.assertFalse(startup.value)
        tray.startup_item.Click.emit()
        self.assertTrue(startup.value)
        self.assertTrue(tray.startup_item.Checked)
        tray.startup_item.Click.emit()
        self.assertFalse(startup.value)
        self.assertFalse(tray.startup_item.Checked)


class Registry:
    HKEY_CURRENT_USER, REG_SZ, KEY_SET_VALUE = object(), 1, 2

    def __init__(self):
        self.values = {'another-app': ('keep this', self.REG_SZ)}

    def OpenKey(self, hive, path, *args):
        assert hive is self.HKEY_CURRENT_USER
        assert path == StartupRegistration.RUN_KEY
        return nullcontext(self)

    CreateKeyEx = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        del self.values[name]


class StartupTests(unittest.TestCase):
    def test_only_own_exact_registration_is_removed(self):
        reg = Registry()
        startup = StartupRegistration('D:/IRIS Project', 'D:/IRIS Project/.venv/Scripts/pythonw.exe', reg)
        self.assertFalse(startup.enabled())
        startup.set_enabled(True)
        self.assertTrue(startup.enabled())
        self.assertIn('"D:/IRIS Project/.venv/Scripts/pythonw.exe"', startup.command)
        self.assertIn('run-iris.pyw"', startup.command)
        startup.set_enabled(False)
        self.assertFalse(startup.enabled())
        self.assertEqual(reg.values, {'another-app': ('keep this', reg.REG_SZ)})
        reg.values[startup.name] = ('a different launch command', reg.REG_SZ)
        startup.set_enabled(False)
        self.assertIn(startup.name, reg.values)

    def test_each_checkout_has_a_separate_registration(self):
        reg = Registry()
        one = StartupRegistration('D:/IRIS One', 'pythonw.exe', reg)
        two = StartupRegistration('D:/IRIS Two', 'pythonw.exe', reg)
        self.assertNotEqual(one.name, two.name)


if __name__ == '__main__':
    unittest.main()
