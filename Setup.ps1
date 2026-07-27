[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir

if ($env:OS -ne "Windows_NT") {
    throw "This application requires Windows 10 or Windows 11."
}

$python = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonArgs = @("-3")
if (-not $python) {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    $pythonArgs = @()
}

if (-not $python) {
    Write-Host "Python 3 was not found." -ForegroundColor Yellow
    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python 3.12 with winget..."
        winget install --id Python.Python.3.12 --exact --accept-package-agreements --accept-source-agreements
        Write-Host "Python was installed. Close this window and run Setup.cmd again." -ForegroundColor Green
        exit 0
    }
    Write-Host "Install Python 3.10+ (64-bit) from https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Start-Process "https://www.python.org/downloads/windows/"
    exit 1
}

$venvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating a private Python environment..."
    & $python.Source @pythonArgs -m venv ".venv"
}

Write-Host "Installing dependencies..."
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --disable-pip-version-check -r "requirements.txt"

Write-Host "Checking Windows OCR..."
& $venvPython "tools\check_environment.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "OCR is missing. Run Install-OCR.cmd as administrator, then restart Windows." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
if ($Run) {
    Start-Process -FilePath (Join-Path $projectDir ".venv\Scripts\pythonw.exe") -ArgumentList "`"$projectDir\WeChatPatResponder.py`""
}
