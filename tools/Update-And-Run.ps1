[CmdletBinding()]
param(
    [string]$AppDirectory = "",
    [string]$ReleaseApiUrl = (
        "https://api.github.com/repos/DouYe/" +
        "wechat-pat-responder/releases/latest"
    ),
    [string]$ReleaseMetadataPath = "",
    [string]$PackagePath = "",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$assetName = "WeChatPatResponder-Windows-x64.zip"
$requiredFiles = @(
    "WeChatPatResponder.exe",
    "Run.cmd",
    "Update-and-Run.cmd",
    "CHANGELOG.md",
    "tools/Update-And-Run.ps1"
)
$maximumPackageBytes = 250MB

function Write-UpdateStep {
    param([string]$Message)
    Write-Host "[WeChat updater] $Message"
}

function Get-NormalizedPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Get-SafeChildPath {
    param(
        [string]$Parent,
        [string]$RelativePath
    )

    $parentPath = (Get-NormalizedPath $Parent).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $candidate = Get-NormalizedPath (Join-Path $parentPath $RelativePath)
    $prefix = $parentPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith(
        $prefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Release entry escapes the target directory: $RelativePath"
    }
    return $candidate
}

function Get-ReleaseMetadata {
    if ($ReleaseMetadataPath) {
        return Get-Content -LiteralPath $ReleaseMetadataPath -Raw |
            ConvertFrom-Json
    }

    $headers = @{
        Accept = "application/vnd.github+json"
        "User-Agent" = "WeChatPatResponder-Updater"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    return Invoke-RestMethod `
        -Uri $ReleaseApiUrl `
        -Headers $headers `
        -UseBasicParsing
}

function Get-InstalledTag {
    param([string]$Directory)
    $changeLogPath = Join-Path $Directory "CHANGELOG.md"
    if (-not (Test-Path -LiteralPath $changeLogPath -PathType Leaf)) {
        return ""
    }

    $match = Select-String `
        -LiteralPath $changeLogPath `
        -Pattern "^##\s+(\d+\.\d+\.\d+)\s*$" |
        Select-Object -First 1
    if (-not $match) {
        return ""
    }
    return "v" + $match.Matches[0].Groups[1].Value
}

function Stop-InstalledApp {
    param([string]$ExecutablePath)
    $targetPath = Get-NormalizedPath $ExecutablePath
    foreach ($process in Get-Process -Name "WeChatPatResponder" `
        -ErrorAction SilentlyContinue) {
        try {
            $processPath = Get-NormalizedPath $process.Path
        }
        catch {
            continue
        }
        if (-not $processPath.Equals(
            $targetPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            continue
        }

        Write-UpdateStep "Closing the installed app before replacement."
        [void]$process.CloseMainWindow()
        if (-not $process.WaitForExit(3000)) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit(3000) | Out-Null
        }
    }
}

if (-not $AppDirectory) {
    $AppDirectory = Split-Path -Parent $PSScriptRoot
}
$AppDirectory = Get-NormalizedPath $AppDirectory
if (-not (Test-Path -LiteralPath $AppDirectory -PathType Container)) {
    throw "Application directory does not exist: $AppDirectory"
}

$temporaryParent = Get-NormalizedPath ([System.IO.Path]::GetTempPath())
$temporaryRoot = Join-Path $temporaryParent (
    "WeChatPatResponderUpdate-" + [System.Guid]::NewGuid().ToString("N")
)
$downloadPath = Join-Path $temporaryRoot $assetName
$stagingPath = Join-Path $temporaryRoot "staging"
$backupPath = Join-Path $temporaryRoot "backup"
$newFiles = New-Object System.Collections.Generic.List[string]
$updateStarted = $false

try {
    $release = Get-ReleaseMetadata
    $releaseTag = [string]$release.tag_name
    if (-not $releaseTag) {
        throw "GitHub did not return a release tag."
    }
    $asset = $release.assets |
        Where-Object { $_.name -eq $assetName } |
        Select-Object -First 1
    if (-not $asset) {
        throw "Latest GitHub release does not contain $assetName."
    }

    $installedTag = Get-InstalledTag $AppDirectory
    if ($installedTag -eq $releaseTag -and -not $PackagePath) {
        Write-UpdateStep "Already current: $releaseTag"
        Stop-InstalledApp (Join-Path $AppDirectory "WeChatPatResponder.exe")
        if (-not $NoStart) {
            Start-Process `
                -FilePath (Join-Path $AppDirectory "Run.cmd") `
                -WorkingDirectory $AppDirectory
        }
        exit 0
    }

    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
    New-Item -ItemType Directory -Path $stagingPath | Out-Null
    New-Item -ItemType Directory -Path $backupPath | Out-Null

    Write-UpdateStep "Downloading $releaseTag..."
    if ($PackagePath) {
        Copy-Item -LiteralPath $PackagePath -Destination $downloadPath
    }
    else {
        Invoke-WebRequest `
            -Uri ([string]$asset.browser_download_url) `
            -OutFile $downloadPath `
            -UseBasicParsing `
            -Headers @{ "User-Agent" = "WeChatPatResponder-Updater" }
    }

    $package = Get-Item -LiteralPath $downloadPath
    $expectedSize = [long]$asset.size
    if (
        $package.Length -lt 1MB -or
        $package.Length -gt $maximumPackageBytes -or
        ($expectedSize -gt 0 -and $package.Length -ne $expectedSize)
    ) {
        throw "Downloaded ZIP size is invalid."
    }

    $expectedDigest = [string]$asset.digest
    if (-not $expectedDigest.StartsWith(
        "sha256:",
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "GitHub release does not provide a SHA-256 digest."
    }
    $actualDigest = (
        Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($actualDigest -ne $expectedDigest.Substring(7).ToLowerInvariant()) {
        throw "Downloaded ZIP failed SHA-256 verification."
    }
    Write-UpdateStep "SHA-256 verified."

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($downloadPath)
    try {
        $fileEntries = @(
            $archive.Entries |
                Where-Object { -not $_.FullName.EndsWith("/") }
        )
        $entryNames = @($fileEntries | ForEach-Object {
            $_.FullName.Replace("\", "/")
        })
        foreach ($requiredFile in $requiredFiles) {
            if ($entryNames -notcontains $requiredFile) {
                throw "Downloaded ZIP is missing: $requiredFile"
            }
        }
        foreach ($entry in $fileEntries) {
            [void](Get-SafeChildPath $stagingPath $entry.FullName)
            [void](Get-SafeChildPath $AppDirectory $entry.FullName)
        }
    }
    finally {
        $archive.Dispose()
    }

    [System.IO.Compression.ZipFile]::ExtractToDirectory(
        $downloadPath,
        $stagingPath
    )

    foreach ($relativePath in $entryNames) {
        $destination = Get-SafeChildPath $AppDirectory $relativePath
        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            $backupDestination = Get-SafeChildPath $backupPath $relativePath
            New-Item `
                -ItemType Directory `
                -Path (Split-Path -Parent $backupDestination) `
                -Force |
                Out-Null
            Copy-Item `
                -LiteralPath $destination `
                -Destination $backupDestination
        }
        else {
            $newFiles.Add($destination)
        }
    }

    Stop-InstalledApp (Join-Path $AppDirectory "WeChatPatResponder.exe")
    $updateStarted = $true
    foreach ($relativePath in $entryNames) {
        $source = Get-SafeChildPath $stagingPath $relativePath
        $destination = Get-SafeChildPath $AppDirectory $relativePath
        New-Item `
            -ItemType Directory `
            -Path (Split-Path -Parent $destination) `
            -Force |
            Out-Null
        Copy-Item `
            -LiteralPath $source `
            -Destination $destination `
            -Force
    }

    Write-UpdateStep "Updated successfully to $releaseTag."
    if (-not $NoStart) {
        Start-Process `
            -FilePath (Join-Path $AppDirectory "Run.cmd") `
            -WorkingDirectory $AppDirectory
    }
}
catch {
    if ($updateStarted) {
        Write-UpdateStep "Update failed; restoring the previous files."
        if (Test-Path -LiteralPath $backupPath -PathType Container) {
            Get-ChildItem -LiteralPath $backupPath -File -Recurse |
                ForEach-Object {
                    $relativePath = $_.FullName.Substring(
                        $backupPath.TrimEnd("\").Length + 1
                    )
                    $destination = Get-SafeChildPath `
                        $AppDirectory `
                        $relativePath
                    New-Item `
                        -ItemType Directory `
                        -Path (Split-Path -Parent $destination) `
                        -Force |
                        Out-Null
                    Copy-Item `
                        -LiteralPath $_.FullName `
                        -Destination $destination `
                        -Force
                }
        }
        foreach ($newFile in $newFiles) {
            if (Test-Path -LiteralPath $newFile -PathType Leaf) {
                Remove-Item -LiteralPath $newFile -Force
            }
        }
    }
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    $temporaryFullPath = Get-NormalizedPath $temporaryRoot
    $temporaryPrefix = $temporaryParent.TrimEnd("\") + "\"
    if (
        $temporaryFullPath.StartsWith(
            $temporaryPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        (Split-Path -Leaf $temporaryFullPath).StartsWith(
            "WeChatPatResponderUpdate-"
        ) -and
        (Test-Path -LiteralPath $temporaryFullPath)
    ) {
        Remove-Item -LiteralPath $temporaryFullPath -Recurse -Force
    }
}
