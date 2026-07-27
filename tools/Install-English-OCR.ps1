#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$capabilities = @(
    "Language.Basic~~~en-US~0.0.1.0",
    "Language.OCR~~~en-US~0.0.1.0"
)

foreach ($name in $capabilities) {
    $capability = Get-WindowsCapability -Online -Name $name
    if ($capability.State -eq "Installed") {
        Write-Host "$name is already installed." -ForegroundColor Green
        continue
    }
    Write-Host "Installing $name ..."
    Add-WindowsCapability -Online -Name $name | Out-Host
}

Write-Host ""
Write-Host "English OCR is installed. Restart Windows before running the responder." -ForegroundColor Green
Read-Host "Press Enter to close"
