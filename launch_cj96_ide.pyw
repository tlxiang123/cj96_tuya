"""Start the CJ96 APP IDE with its PowerShell startup workaround."""

import ctypes
import os
from pathlib import Path
import subprocess


def main():
    executable = Path(r"C:\Program Files\Tuya MiniApp IDE\Tuya MiniApp IDE.exe")
    if not executable.is_file():
        ctypes.windll.user32.MessageBoxW(
            None, f"找不到涂鸦开发工具：\n{executable}", "CJ96 APP", 0x10
        )
        return
    environment = os.environ.copy()
    environment["POWERSHELL_UPDATECHECK"] = "Off"
    try:
        subprocess.Popen(
            [str(executable)], cwd=str(executable.parent), env=environment
        )
    except OSError as error:
        ctypes.windll.user32.MessageBoxW(None, str(error), "CJ96 APP", 0x10)


if __name__ == "__main__":
    main()
