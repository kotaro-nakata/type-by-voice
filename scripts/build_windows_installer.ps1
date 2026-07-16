$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$VersionFile = Join-Path $Root "app_metadata.py"
$VersionMatch = Select-String -Path $VersionFile -Pattern '^APP_VERSION = "(.+)"$'
if (-not $VersionMatch) {
    throw "APP_VERSION was not found in app_metadata.py"
}
$Version = $VersionMatch.Matches[0].Groups[1].Value

$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $IsccPath = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $IsccPath) {
        throw "Inno Setup 6 was not found. Install it before building the installer."
    }
} else {
    $IsccPath = $Iscc.Source
}

$BundleExe = Join-Path $Root "dist\VoiceTerm\VoiceTerm.exe"
if (-not (Test-Path $BundleExe)) {
    throw "Windows bundle not found. Run: python scripts/build_bundle.py"
}

& $IsccPath "/DMyAppVersion=$Version" (Join-Path $Root "installer\windows\VoiceTerm.iss")
