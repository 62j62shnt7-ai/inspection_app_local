"""Native folder selection without optional Python GUI dependencies."""
import subprocess
import sys


def choose_folder(platform=None):
    platform = platform or sys.platform
    if platform == 'win32':
        script = """Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose an independent backup folder'
try {
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Write($dialog.SelectedPath)
    }
} finally { $dialog.Dispose() }
"""
        command = ['powershell.exe', '-NoProfile', '-STA', '-Command', script]
    elif platform == 'darwin':
        command = ['osascript', '-e', 'POSIX path of (choose folder with prompt "Choose an independent backup folder")']
    else:
        raise ValueError('The folder chooser supports Windows and macOS.')
    try:
        result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Unable to open the folder chooser. Try browsing again.') from exc
    if result.returncode:
        if platform == 'darwin' and '(-128)' in result.stderr:
            return None
        raise ValueError('Unable to open the folder chooser. Try browsing again.')
    return result.stdout.strip() or None
