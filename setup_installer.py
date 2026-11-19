import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import winreg


APP_NAME = "UNIVERSAL CONVERTER"
APP_EXECUTABLE = "UniversalConverter.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UniversalConverter"
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
DEFAULT_INSTALL_DIR = LOCAL_APP_DATA / "Programs" / "Universal Converter"


def bundle_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def powershell_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(shortcut_path, executable):
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut({powershell_literal(shortcut_path)}); "
        f"$shortcut.TargetPath = {powershell_literal(executable)}; "
        f"$shortcut.WorkingDirectory = {powershell_literal(executable.parent)}; "
        f"$shortcut.IconLocation = {powershell_literal(str(executable) + ',0')}; "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def write_uninstaller(install_dir):
    uninstaller = install_dir / "Uninstall.bat"
    uninstaller.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"INSTALL_DIR=%~dp0\"\r\n"
        f'reg delete "HKCU\\{UNINSTALL_KEY}" /f >nul 2>&1\r\n'
        "start \"\" /b powershell.exe -NoProfile -WindowStyle Hidden -Command \"Start-Sleep -Seconds 2; $start = Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\Universal Converter'; Remove-Item -LiteralPath $start -Recurse -Force -ErrorAction SilentlyContinue; $desktop = [Environment]::GetFolderPath('Desktop'); Remove-Item -LiteralPath (Join-Path $desktop 'Universal Converter.lnk') -Force -ErrorAction SilentlyContinue; Set-Location $env:TEMP; Remove-Item -LiteralPath $env:INSTALL_DIR -Recurse -Force\"\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )


def register_uninstaller(install_dir, executable):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        values = {
            "DisplayName": (APP_NAME, winreg.REG_SZ),
            "DisplayVersion": ("1.0.0", winreg.REG_SZ),
            "Publisher": ("SURJO LIVE", winreg.REG_SZ),
            "InstallLocation": (str(install_dir), winreg.REG_SZ),
            "DisplayIcon": (str(executable), winreg.REG_SZ),
            "UninstallString": (f'"{install_dir / "Uninstall.bat"}"', winreg.REG_SZ),
            "NoModify": (1, winreg.REG_DWORD),
            "NoRepair": (1, winreg.REG_DWORD),
        }
        for name, (value, value_type) in values.items():
            winreg.SetValueEx(key, name, 0, value_type, value)


class SetupWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Install {APP_NAME}")
        self.root.geometry("560x430")
        self.root.minsize(520, 400)
        self.root.configure(bg="#f1f5f2")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.install_path = tk.StringVar(value=str(DEFAULT_INSTALL_DIR))
        self.create_desktop_shortcut = tk.BooleanVar(value=True)
        self.launch_after_install = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Choose where to install the application.")
        self.events = queue.Queue()
        self.installing = False

        style = ttk.Style(self.root)
        style.configure("Install.Horizontal.TProgressbar", troughcolor="#d8e2db", background="#ff8a66")

        body = ttk.Frame(self.root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=APP_NAME, font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(body, text="Install the local desktop application", foreground="#66766d").pack(anchor="w", pady=(3, 18))

        ttk.Label(body, text="Installation folder").pack(anchor="w")
        path_row = ttk.Frame(body)
        path_row.pack(fill="x", pady=(6, 12))
        ttk.Entry(path_row, textvariable=self.install_path).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Browse", command=self.browse).pack(side="left", padx=(8, 0))

        ttk.Checkbutton(body, text="Create a desktop shortcut", variable=self.create_desktop_shortcut).pack(anchor="w", pady=2)
        ttk.Checkbutton(body, text="Launch UNIVERSAL CONVERTER after installation", variable=self.launch_after_install).pack(anchor="w", pady=2)
        ttk.Label(body, text="Uploads and settings are kept separately in your Local AppData.", foreground="#66766d").pack(anchor="w", pady=(4, 12))

        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100, style="Install.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(2, 6))
        ttk.Label(body, textvariable=self.status).pack(anchor="w", pady=(0, 7))
        self.log = tk.Listbox(body, height=6, activestyle="none", borderwidth=1, relief="solid")
        self.log.pack(fill="both", expand=True)

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 0))
        self.install_button = ttk.Button(actions, text="Install", command=self.install)
        self.install_button.pack(side="right")
        self.close_button = ttk.Button(actions, text="Close", command=self.close)
        self.close_button.pack(side="right", padx=(0, 8))
        self.root.after(100, self.poll_events)

    def browse(self):
        initial = Path(self.install_path.get()).parent
        selected = filedialog.askdirectory(initialdir=initial if initial.exists() else LOCAL_APP_DATA)
        if selected:
            self.install_path.set(selected)

    def install(self):
        if self.installing:
            return
        source = bundle_root() / "app"
        if not source.is_dir():
            messagebox.showerror("Setup files missing", "The application files could not be found inside this installer.")
            return
        try:
            target = Path(self.install_path.get()).expanduser().resolve()
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Invalid folder", str(error))
            return
        if not str(self.install_path.get()).strip() or target == Path(target.anchor):
            messagebox.showerror("Invalid folder", "Choose a folder other than the drive root.")
            return
        if target.exists() and any(target.iterdir()):
            if not messagebox.askyesno("Use existing folder?", "Files in this folder may be replaced. Continue?"):
                return

        options = (self.create_desktop_shortcut.get(), self.launch_after_install.get())
        self.installing = True
        self.install_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.status.set("Preparing application files...")
        threading.Thread(target=self.copy_application, args=(source, target, options), daemon=True).start()

    def copy_application(self, source, target, options):
        warnings = []
        try:
            files = sorted(path for path in source.rglob("*") if path.is_file())
            total_bytes = max(1, sum(path.stat().st_size for path in files))
            copied_bytes = 0
            target.mkdir(parents=True, exist_ok=True)
            for index, source_file in enumerate(files, start=1):
                destination = target / source_file.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self.events.put(("progress", f"Installing {source_file.relative_to(source)}", copied_bytes * 100 / total_bytes))
                with source_file.open("rb") as input_file, destination.open("wb") as output_file:
                    while chunk := input_file.read(1024 * 1024):
                        output_file.write(chunk)
                        copied_bytes += len(chunk)
                        self.events.put(("progress", f"Copying file {index} of {len(files)}", copied_bytes * 100 / total_bytes))
                shutil.copystat(source_file, destination)

            executable = target / APP_EXECUTABLE
            write_uninstaller(target)
            start_menu = Path(os.environ.get("APPDATA", LOCAL_APP_DATA)) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Universal Converter"
            try:
                create_shortcut(start_menu / "Universal Converter.lnk", executable)
                if options[0]:
                    desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
                    create_shortcut(desktop / "Universal Converter.lnk", executable)
            except Exception as error:
                warnings.append(f"Shortcut creation was skipped: {error}")
            try:
                register_uninstaller(target, executable)
            except Exception as error:
                warnings.append(f"The Add/Remove Programs entry could not be created: {error}")
            self.events.put(("done", target, options[1], warnings))
        except Exception as error:
            self.events.put(("error", str(error)))

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, status, percent = event
                    self.status.set(status)
                    self.progress.configure(value=percent)
                    if not self.log.size() or self.log.get(tk.END).strip() != status:
                        self.log.insert(tk.END, status)
                        self.log.yview_moveto(1)
                        if self.log.size() > 80:
                            self.log.delete(0)
                elif event[0] == "done":
                    _, target, launch, warnings = event
                    self.installing = False
                    self.progress.configure(value=100)
                    self.status.set("Installation complete.")
                    self.log.insert(tk.END, "Installation complete.")
                    self.install_button.configure(text="Installed", state="disabled")
                    if warnings:
                        messagebox.showwarning("Installed with notices", "\n".join(warnings))
                    if launch:
                        try:
                            subprocess.Popen([str(target / APP_EXECUTABLE)], cwd=target)
                        except OSError as error:
                            messagebox.showerror("Launch failed", f"The app installed, but could not be started:\n{error}")
                elif event[0] == "error":
                    self.installing = False
                    self.install_button.configure(state="normal")
                    self.status.set("Installation failed.")
                    messagebox.showerror("Installation failed", event[1])
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def close(self):
        if not self.installing:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()