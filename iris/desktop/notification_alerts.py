"""Best-effort Windows reminder balloon, with text kept out of shell code."""
from __future__ import annotations

import json
import os
import subprocess


_SCRIPT = r"""$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notice = [Console]::In.ReadToEnd() | ConvertFrom-Json
$icon = New-Object System.Windows.Forms.NotifyIcon
try {
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.Visible = $true
    $icon.BalloonTipTitle = [string]$notice.title
    $icon.BalloonTipText = [string]$notice.body
    $icon.ShowBalloonTip(10000)
    Start-Sleep -Seconds 12
} finally { $icon.Dispose() }
"""


def notify(title: str, body: str) -> bool:
    """Called on a background worker; Windows notification settings still apply."""
    if os.name != 'nt':
        return False
    payload = json.dumps({'title': str(title)[:63], 'body': str(body)[:255]}, ensure_ascii=True)
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _SCRIPT],
            input=payload, text=True, encoding='utf-8', timeout=20,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
