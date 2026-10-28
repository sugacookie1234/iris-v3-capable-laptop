"""Windows tray lifetime and an opt-in, per-checkout login registration."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


class StartupRegistration:
    RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

    def __init__(self, root, executable, registry=None):
        if registry is None:
            import winreg
            registry = winreg
        self.registry = registry
        root = Path(root).resolve()
        digest = hashlib.sha256(str(root).lower().encode()).hexdigest()[:12]
        self.name = 'IRIS-CapableLaptop-' + digest
        self.command = subprocess.list2cmdline([str(executable), str(root / 'run-iris.pyw')])

    def enabled(self):
        reg = self.registry
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.RUN_KEY) as key:
                value, kind = reg.QueryValueEx(key, self.name)
                return kind == reg.REG_SZ and value == self.command
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        reg = self.registry
        if enabled:
            with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, self.RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.SetValueEx(key, self.name, 0, reg.REG_SZ, self.command)
        elif self.enabled():
            # Remove only the registration for this exact launch command.
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, self.name)


class DesktopTray:
    """Created from before_show; all callbacks run on the WinForms UI thread."""

    def __init__(self, native, forms, drawing, startup):
        self.native, self.forms, self.startup = native, forms, startup
        self.exiting = False
        self.disposed = False
        self.menu = forms.ContextMenuStrip()
        self.icon = forms.NotifyIcon()
        try:
            self.open_item = forms.ToolStripMenuItem('Open IRIS')
            self.open_item.Click += self.open
            self.startup_item = forms.ToolStripMenuItem('Start with Windows')
            self.startup_item.Checked = startup.enabled()
            self.startup_item.Click += self.toggle_startup
            self.quit_item = forms.ToolStripMenuItem('Quit IRIS')
            self.quit_item.Click += self.quit
            for item in (self.open_item, self.startup_item, forms.ToolStripSeparator(), self.quit_item):
                self.menu.Items.Add(item)
            self.icon.Text = 'IRIS — double clap to wake; right-click to open or quit'
            self.icon.Icon = drawing.SystemIcons.Information
            self.icon.ContextMenuStrip = self.menu
            self.icon.DoubleClick += self.open
            self.icon.Visible = True
            native.FormClosing += self.on_closing
            native.FormClosed += self.on_closed
        except Exception:
            self.dispose()
            raise

    def open(self, sender=None, event=None):
        if self.exiting or self.disposed:
            return
        self.native.Show()
        if self.native.WindowState == self.forms.FormWindowState.Minimized:
            self.native.WindowState = self.forms.FormWindowState.Normal
        self.native.Activate()

    def on_closing(self, sender, event):
        # Do not block sign-out, shutdown, or an explicit Quit from the tray.
        if not self.exiting and not self.disposed and event.CloseReason == self.forms.CloseReason.UserClosing:
            event.Cancel = True
            self.native.Hide()

    def quit(self, sender=None, event=None):
        if self.disposed:
            return
        self.exiting = True
        self.native.Close()

    def toggle_startup(self, sender=None, event=None):
        try:
            self.startup.set_enabled(not self.startup.enabled())
            self.startup_item.Checked = self.startup.enabled()
        except OSError:
            self.forms.MessageBox.Show('Windows could not update IRIS login startup. Your current setting was kept.',
                                       'IRIS', self.forms.MessageBoxButtons.OK, self.forms.MessageBoxIcon.Warning)

    def on_closed(self, sender=None, event=None):
        self.dispose()

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.icon.Visible = False
        self.icon.Dispose()
        self.menu.Dispose()


def install_tray(window, root):
    # pythonnet and these assemblies are already initialized by pywebview.
    import sys
    import System.Drawing as drawing
    import System.Windows.Forms as forms
    executable = Path(root) / '.venv' / 'Scripts' / 'pythonw.exe'
    if not executable.is_file():
        executable = Path(sys.executable).with_name('pythonw.exe')
    return DesktopTray(window.native, forms, drawing, StartupRegistration(root, executable))
