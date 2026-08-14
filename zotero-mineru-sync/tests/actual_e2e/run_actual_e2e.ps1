$ErrorActionPreference = "Stop"

$project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $project ".testdata\zotero-e2e-actual-$stamp"
$profile = Join-Path $runRoot "profile"
$dataDir = Join-Path $runRoot "data"
$outputRoot = Join-Path $runRoot "sync-data"
$fixture = Join-Path $runRoot "paper.pdf"
$marker = Join-Path $runRoot "seed-marker.json"
$extensions = Join-Path $profile "extensions"
$pluginXpi = Join-Path $runRoot "zotero-mineru-sync.xpi"
$launcher = Join-Path $runRoot "launch-sync.cmd"
$mineruPython = Join-Path $project "..\MinerU-GUI\.venv\Scripts\python.exe"
$zotero = "C:\Program Files\Zotero\zotero.exe"

foreach ($path in @($runRoot, $profile, $dataDir, $outputRoot, $extensions)) {
  New-Item -ItemType Directory -Force -Path $path | Out-Null
}

# Produce a valid, project-local PDF without using an external fixture.
@"
from pathlib import Path
from pypdf import PdfWriter
writer = PdfWriter()
writer.add_blank_page(width=612, height=792)
with Path(r'''$fixture''').open('wb') as handle:
    writer.write(handle)
"@ | & python -

& python (Join-Path $project "build_plugin.py") --output $pluginXpi
Copy-Item -LiteralPath $pluginXpi -Destination (Join-Path $extensions "zotero-mineru-sync@local.xpi")
if (-not (Test-Path -LiteralPath $mineruPython)) { throw "MinerU-GUI venv Python not found: $mineruPython" }
@"
@echo off
setlocal
cd /d "%~dp0..\.."
"$mineruPython" -m zotero_mineru_sync %*
exit /b %ERRORLEVEL%
"@ | Set-Content -LiteralPath $launcher -Encoding ASCII

function JsonLiteral([object] $value) {
  return ($value | ConvertTo-Json -Compress)
}

$userPrefs = @(
  'user_pref("extensions.zotero.httpServer.enabled", true);',
  'user_pref("extensions.zotero.httpServer.localAPI.enabled", true);',
  'user_pref("extensions.zotero.sync.autoSync", false);',
  'user_pref("extensions.zotero.firstRun2", false);',
  'user_pref("extensions.zotero.firstRunGuidance", false);',
  'user_pref("extensions.zotero.firstRunGuidanceShown.readAloud", true);',
  'user_pref("extensions.autoDisableScopes", 0);',
  'user_pref("extensions.enabledScopes", 15);',
  'user_pref("xpinstall.signatures.required", false);',
  ('user_pref("extensions.zotero-mineru-sync.enabled", ' + (JsonLiteral $true) + ');'),
  ('user_pref("extensions.zotero-mineru-sync.command", ' + (JsonLiteral ($launcher -replace '\\', '/')) + ');'),
  ('user_pref("extensions.zotero-mineru-sync.dataRoot", ' + (JsonLiteral ($outputRoot -replace '\\', '/')) + ');'),
  'user_pref("extensions.zotero-mineru-sync.cpu", true);',
  'user_pref("extensions.zotero-mineru-sync.cpuThreads", 1);'
)
$userPrefs | Set-Content -LiteralPath (Join-Path $profile "user.js") -Encoding UTF8

$env:ZOTERO_GUI_PATH = (Resolve-Path (Join-Path $project "..\MinerU-GUI")).Path
$env:MOZ_CRASHREPORTER_DISABLE = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:ZOTERO_MINERU_DATA_ROOT = ($outputRoot -replace '\\', '/')
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $zotero
$startInfo.WorkingDirectory = $project
$startInfo.UseShellExecute = $false
# ProcessStartInfo avoids Start-Process's lossy argument joining on Windows.
$startInfo.Arguments = '--headless --new-instance --profile "' + $profile + '" -datadir "' + $dataDir + '"'
if ($startInfo.Arguments -notmatch [regex]::Escape($dataDir)) { throw "Zotero data directory was not included in launch arguments" }
$process = [System.Diagnostics.Process]::Start($startInfo)

try {
  $initDeadline = (Get-Date).AddMinutes(2)
  while ((Get-Date) -lt $initDeadline -and -not (Test-Path -LiteralPath (Join-Path $dataDir "zotero.sqlite"))) {
    Start-Sleep -Seconds 2
  }
  if (-not (Test-Path -LiteralPath (Join-Path $dataDir "zotero.sqlite"))) {
    throw "Zotero did not initialize the project-local database"
  }
}
finally {
  if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2
  $projectProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'zotero.exe'" |
    Where-Object { $_.CommandLine -like "*$runRoot*" })
  foreach ($item in $projectProcesses) { Stop-Process -Id $item.ProcessId -Force -ErrorAction SilentlyContinue }
}

$seed = & python (Join-Path $PSScriptRoot "seed_zotero_db.py") --db (Join-Path $dataDir "zotero.sqlite") --fixture $fixture --marker $marker | ConvertFrom-Json
if ($seed.status -ne "seeded") { throw "database seeding failed" }

$process = [System.Diagnostics.Process]::Start($startInfo)

try {
  $resultDeadline = (Get-Date).AddMinutes(10)
  $result = $null
  while ((Get-Date) -lt $resultDeadline) {
    $files = Get-ChildItem -LiteralPath (Join-Path $outputRoot "results") -Filter *.json -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
      $candidate = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
      if ($candidate.entries.Count -gt 0) {
        $result = $candidate
        break
      }
    }
    if ($result) { break }
    Start-Sleep -Seconds 3
  }
  if (-not $result) { throw "sync result did not arrive within 10 minutes" }
  $result | ConvertTo-Json -Depth 10
  if ($result.counts.SUCCESS -lt 1) { throw "actual E2E did not produce a SUCCESS result" }
  $artifact = Join-Path $outputRoot ("archive\{0}\{1}\{2}" -f $result.library_id, $seed.parent_item_key, $seed.attachment_key)
  if (-not (Test-Path -LiteralPath (Join-Path $artifact "manifest.json"))) { throw "manifest.json is missing: $artifact" }
  if (-not (Get-ChildItem -LiteralPath $artifact -Filter *.md -File -ErrorAction SilentlyContinue)) { throw "Markdown artifact is missing: $artifact" }
  Write-Output "actual Zotero E2E passed"
}
finally {
  if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  Get-CimInstance Win32_Process -Filter "Name = 'zotero.exe'" |
    Where-Object { $_.CommandLine -like "*$runRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
