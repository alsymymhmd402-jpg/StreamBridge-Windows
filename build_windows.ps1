param(
    [ValidateSet('onefile', 'onedir')]
    [string]$Mode = 'onefile'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a Python 3.11 virtual environment.' }
} else {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a Python virtual environment.' }
}
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) { throw 'Python 3.11 x64 was not found. Install it and retry.' }
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $VenvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $VenvPython -c "import tkinter; import streambridge.ui; print('Tkinter UI imports successfully.')"
if ($LASTEXITCODE -ne 0) { throw 'Tkinter/Tcl is missing from this Python installation.' }
& $VenvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; EXE was not built.' }

$PyInstallerArgs = @(
    'run_app.py',
    '--noconfirm',
    '--clean',
    '--windowed',
    '--name', 'StreamBridge',
    '--icon', 'src\streambridge\assets\streambridge.ico',
    '--manifest', 'streambridge.manifest',
    '--add-data', 'src\streambridge\assets;streambridge\assets',
    '--paths', 'src',
    '--collect-all', 'imageio_ffmpeg',
    '--collect-all', 'pyvirtualcam',
    '--collect-all', 'PIL',
    '--collect-all', 'cv2',
    '--collect-all', 'sounddevice',
    '--collect-all', '_sounddevice_data'
)
if ($Mode -eq 'onefile') {
    $PyInstallerArgs += '--onefile'
} else {
    $PyInstallerArgs += '--onedir'
}
& $VenvPython -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

Write-Host ''
if ($Mode -eq 'onefile') {
    Write-Host "Build complete: $PSScriptRoot\dist\StreamBridge.exe" -ForegroundColor Green
} else {
    Write-Host "Build complete: $PSScriptRoot\dist\StreamBridge\StreamBridge.exe" -ForegroundColor Green
}
Write-Host 'UnityCapture is a separate DirectShow driver and must be installed once on Windows.' -ForegroundColor Yellow
