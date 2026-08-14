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
$pluginSource = Join-Path $runRoot "plugin-source"
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
if (-not (Test-Path -LiteralPath $fixture -PathType Leaf)) { throw "failed to create project-local PDF fixture: $fixture" }

Copy-Item -LiteralPath (Join-Path $project "zotero-plugin") -Destination $pluginSource -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "helper\bootstrap.js") -Destination (Join-Path $pluginSource "e2e_helper.js")
& python (Join-Path $project "build_plugin.py") --source $pluginSource --output $pluginXpi
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
  'user_pref("extensions.zotero-mineru-sync.cpuThreads", 1);',
  ('user_pref("extensions.zotero-mineru-sync-e2e.fixture", ' + (JsonLiteral ($fixture -replace '\\', '/')) + ');'),
  ('user_pref("extensions.zotero-mineru-sync-e2e.marker", ' + (JsonLiteral ($marker -replace '\\', '/')) + ');'),
  ('user_pref("extensions.zotero-mineru-sync-e2e.dataRoot", ' + (JsonLiteral ($outputRoot -replace '\\', '/')) + ');'),
  ('user_pref("extensions.zotero-mineru-sync.e2eBootstrap", ' + (JsonLiteral $true) + ');')
)
$userPrefs | Set-Content -LiteralPath (Join-Path $profile "user.js") -Encoding UTF8

$env:ZOTERO_GUI_PATH = (Resolve-Path (Join-Path $project "..\MinerU-GUI")).Path
$env:ZOTERO_STORAGE_ROOT = Join-Path $dataDir "storage"
$env:MOZ_CRASHREPORTER_DISABLE = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:ZOTERO_MINERU_DATA_ROOT = ($outputRoot -replace '\\', '/')
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $zotero
$startInfo.WorkingDirectory = $project
$startInfo.UseShellExecute = $false
# ProcessStartInfo avoids Start-Process's lossy argument joining on Windows.
$startInfo.Arguments = '--headless --new-instance -purgecaches --profile "' + $profile + '" -datadir "' + $dataDir + '"'
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
    if (Test-Path -LiteralPath $marker) {
      $candidate = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($candidate.status -eq "completed") {
        $result = $candidate
        break
      }
      if ($candidate.status -eq "error") { throw "actual E2E helper failed: $($candidate.error)" }
    }
    Start-Sleep -Seconds 3
  }
  if (-not $result) { throw "duplicate/merge lifecycle did not complete within 10 minutes" }
  $result | ConvertTo-Json -Depth 10
  $blockedEntries = @($result.blocked_result.entries)
  if ($result.blocked_result.counts.BLOCKED_DUPLICATE -ne 2 -or $blockedEntries.Count -ne 2) {
    throw "actual E2E did not skip both duplicate attachments before merge"
  }
  if ($result.archive_count_before_merge -ne 0) {
    throw "an archive was produced before the Zotero merge"
  }
  if (-not $result.duplicate_parent_deleted) {
    throw "Zotero merge did not delete the duplicate parent item"
  }
  $finalEntries = @($result.final_result.entries)
  $finalSuccessEntries = @($finalEntries | Where-Object { $_.status -eq "SUCCESS" })
  if ($finalEntries.Count -ne 1 -or $result.final_result.counts.SUCCESS -ne 1 -or $finalSuccessEntries.Count -ne 1) {
    throw "post-merge result did not contain exactly one successful conversion"
  }
  if ($finalSuccessEntries[0].parent_item_key -ne $result.surviving_parent_item_key -or
      $finalSuccessEntries[0].attachment_key -ne $result.surviving_attachment_key) {
    throw "successful conversion did not target the surviving Zotero attachment"
  }
  $allResults = @(Get-ChildItem -LiteralPath (Join-Path $outputRoot "results") -Filter *.json -File -ErrorAction SilentlyContinue |
    ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json })
  $conversionEntries = @($allResults | ForEach-Object { @($_.entries) } |
    Where-Object { $_.status -eq "SUCCESS" -or $_.status -eq "FAILED" })
  if ($conversionEntries.Count -ne 1 -or $conversionEntries[0].status -ne "SUCCESS") {
    throw "expected exactly one successful conversion attempt, found $($conversionEntries.Count) terminal conversion entries"
  }
  if ($result.archive_count_after_merge -ne 1) { throw "expected exactly one archive manifest, found $($result.archive_count_after_merge)" }
  $artifact = Join-Path $outputRoot ("archive\{0}\{1}\{2}" -f $result.final_result.library_id, $result.surviving_parent_item_key, $result.surviving_attachment_key)
  if (-not (Test-Path -LiteralPath (Join-Path $artifact "manifest.json"))) { throw "manifest.json is missing: $artifact" }
  if (@(Get-ChildItem -LiteralPath $outputRoot -Filter manifest.json -Recurse -File -ErrorAction SilentlyContinue).Count -ne 1) {
    throw "expected exactly one archived manifest"
  }
  if (@(Get-ChildItem -LiteralPath $artifact -Filter *.md -File -ErrorAction SilentlyContinue).Count -ne 1) {
    throw "Markdown artifact count is not one: $artifact"
  }
  Write-Output "actual Zotero duplicate/merge E2E passed"
}
finally {
  if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  Get-CimInstance Win32_Process -Filter "Name = 'zotero.exe'" |
    Where-Object { $_.CommandLine -like "*$runRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
