<#
 One-step setup for Atlas Onboarding.
   setup.bat "C:\path\to\atlas_v2.0"            install or update
   setup.bat "C:\path\to\atlas_v2.0" -Remove    uninstall (learner progress is kept)
 Installs: ATLAS Tutor agent (VS Code Copilot), a Cursor rule + visual guide "Atlas Explorer".
 Everything is added as untracked, git-excluded files inside the Atlas checkout.
#>
param(
  [Parameter(Position = 0)][string]$Atlas,
  [switch]$Remove,
  [switch]$Shortcut
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot

function Step($n, $t) { Write-Host ("`n[{0}] {1}" -f $n, $t) -ForegroundColor Cyan }
function Fail($t) { Write-Host "ERROR: $t" -ForegroundColor Red; exit 1 }

$ruleRel = '.cursor/rules/atlas-onboarding.mdc'
$marker = 'atlas-onboarding-managed'
function Get-Exclude($atlas) { (& git -C $atlas rev-parse --path-format=absolute --git-path info/exclude).Trim() }
function Remove-CursorRule {
  $rule = Join-Path $Atlas $ruleRel
  $tracked = & git -C $Atlas ls-files -- $ruleRel
  if ($tracked) { Write-Host 'Tracked Cursor rule left in place.' -ForegroundColor Yellow }
  elseif ((Test-Path $rule) -and (Select-String -Path $rule -Pattern $marker -Quiet)) { Remove-Item $rule -Force }
  $ex = Get-Exclude $Atlas
  if (Test-Path $ex) {
    $t = [IO.File]::ReadAllText($ex)
    $t = [regex]::Replace($t, '(?s)\r?\n?# BEGIN atlas-onboarding cursor rule.*?# END atlas-onboarding cursor rule\r?\n?', '')
    [IO.File]::WriteAllText($ex, $t)
  }
}

Step 1 'Checking tools'
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { Fail 'Python 3.10+ not found. Install it from python.org and re-run.' }
$ver = & python -c "import sys;print('%d.%d'%sys.version_info[:2])"
if ([version]$ver -lt [version]'3.10') { Fail "Python $ver found, need 3.10 or newer." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'Git not found. Install Git for Windows and re-run.' }
Write-Host "Python $ver and Git OK"

Step 2 'Locating the Atlas checkout'
if (-not $Atlas) {
  $guess = @("$env:USERPROFILE\Documents\atlas_v2.0", "$env:USERPROFILE\source\repos\atlas_v2.0", "C:\atlas_v2.0") | Where-Object { Test-Path "$_\Atlas.sln" } | Select-Object -First 1
  if ($guess) { $Atlas = $guess; Write-Host "Found: $Atlas" }
  else { $Atlas = Read-Host 'Path to your Atlas checkout (folder that contains Atlas.sln)' }
}
$Atlas = $Atlas.Trim('"').TrimEnd('\')
if (-not (Test-Path "$Atlas\Atlas.sln")) { Fail "No Atlas.sln in '$Atlas'. Give the repository root." }
$dest = Join-Path $Atlas '.atlas-onboarding'
$explorerDest = Join-Path $dest 'explorer'
$manifest = Join-Path $dest 'manifest.json'
$markerFile = Join-Path $explorerDest '.atlas-explorer-managed'
function Test-ManagedExplorer {
  if ((Test-Path $markerFile) -and (Select-String -Path $markerFile -Pattern $marker -Quiet)) { return $true }
  # Copies installed before the marker still belong to this setup if they are our server.
  $server = Join-Path $explorerDest 'server.py'
  (Test-Path $server) -and (Select-String -Path $server -Pattern 'server_version = "AtlasExplorer"' -Quiet)
}

# Stop only the Explorer server started for this checkout. Compare full resolved paths, not substrings.
$atlasFull = (Resolve-Path -LiteralPath $Atlas).Path.TrimEnd('\')
$serverFull = Join-Path $explorerDest 'server.py'
function Test-ThisCheckout([string]$cmd) {
  if ($cmd -notmatch '(?i)(^|[\s"])([A-Za-z]:\\[^"\s]*server\.py|server\.py)(\s|"|$)') { return $false }
  $atlasArg = $null
  if ($cmd -match '(?i)--atlas(?:\s+|=)(?:"([^"]+)"|(\S+))') { $atlasArg = if ($Matches[1]) { $Matches[1] } else { $Matches[2] } }
  if ($atlasArg) {
    try { return (Resolve-Path -LiteralPath $atlasArg -ErrorAction Stop).Path.TrimEnd('\') -eq $atlasFull } catch { return $false }
  }
  if ($cmd -match '(?i)"([^"]*server\.py)"|([A-Za-z]:\\[^\s"]*server\.py)') {
    $script = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
    try { return (Resolve-Path -LiteralPath $script -ErrorAction Stop).Path -eq (Resolve-Path -LiteralPath $serverFull -ErrorAction Stop).Path } catch { return $false }
  }
  return $false
}
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { Test-ThisCheckout $_.CommandLine } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($Remove) {
  Step 3 'Removing the tutor'
  if (Test-Path $manifest) { & python "$here\scripts\install.py" remove --atlas $Atlas; if ($LASTEXITCODE) { Fail 'Installer refused removal (see message above).' } }
  elseif (Test-Path $dest) { Write-Host 'No installation manifest; tutor files were not removed.' -ForegroundColor Yellow }
  if (Test-ManagedExplorer) {
    Remove-Item $explorerDest -Recurse -Force
    $bat = Join-Path $dest 'Open Atlas Explorer.bat'
    if ((Test-Path $bat) -and (Select-String -Path $bat -Pattern 'Atlas Explorer' -Quiet)) { Remove-Item $bat -Force }
    Remove-Item (Join-Path $dest '.source-repo'), (Join-Path $dest 'update.log') -Force -ErrorAction SilentlyContinue
  } elseif (Test-Path $explorerDest) {
    Write-Host "Explorer folder is not managed by this installer; left in place: $explorerDest" -ForegroundColor Yellow
  }
  Remove-CursorRule
  Write-Host 'Removed. Your learner progress was not touched.' -ForegroundColor Green
  exit 0
}

Step 3 'Installing the ATLAS Tutor agent'
$action = if (Test-Path $manifest) { 'update' } else { 'install' }
& python "$here\scripts\install.py" $action --atlas $Atlas
if ($LASTEXITCODE) { Fail 'The installer stopped. Read the message above; nothing was left half-installed.' }

Step 4 'Installing the visual guide (Atlas Explorer)'
if ((Test-Path $explorerDest) -and -not (Test-ManagedExplorer)) {
  Fail "Atlas Explorer folder already exists and was not installed by this setup. Move '$explorerDest' aside and run setup again."
}
$baseline = Join-Path $here 'sync\baseline.json'
if (-not (Test-Path $baseline)) { Fail "Atlas docs baseline is missing: $baseline" }
$keep = Join-Path $env:TEMP ('atlas-shots-' + [guid]::NewGuid())
$shots = Join-Path $explorerDest 'assets\screens'
if (Test-Path $shots) { Copy-Item $shots $keep -Recurse -Force }   # keep screenshots added only on the Atlas side
if (Test-Path $explorerDest) { Remove-Item $explorerDest -Recurse -Force }
New-Item -ItemType Directory -Force $explorerDest | Out-Null
$src = Join-Path $here 'explorer'
Copy-Item "$src\*" $explorerDest -Recurse -Force
Copy-Item $baseline (Join-Path $explorerDest 'atlas-baseline.json') -Force
Set-Content -Encoding ASCII -Path $markerFile -Value $marker
if (Test-Path $keep) {   # put back only screenshots this package does not ship, so updated images always win
  Get-ChildItem $keep -File | Where-Object { -not (Test-Path (Join-Path $shots $_.Name)) } | Copy-Item -Destination $shots
  Remove-Item $keep -Recurse -Force
}
$bat = Join-Path $dest 'Open Atlas Explorer.bat'
Copy-Item (Join-Path $here 'scripts\open-explorer.bat') $bat -Force
# Remember where this copy of atlas-onboarding lives, so the launcher can pull new lessons before it starts.
# The file sits inside .atlas-onboarding/, which Git already excludes. ASCII only: batch files cannot read other characters.
$sourceFile = Join-Path $dest '.source-repo'
if ((Test-Path (Join-Path $here '.git')) -and ($here -cmatch '^[\x20-\x7E]+$')) { Set-Content -Encoding ASCII -Path $sourceFile -Value $here }
else { Remove-Item $sourceFile -Force -ErrorAction SilentlyContinue; Write-Host 'Automatic lesson updates are off (this copy is not a git clone, or its path has special characters).' -ForegroundColor Yellow }

if ($Shortcut) {
  $desk = [Environment]::GetFolderPath('Desktop')
  $uri = ([Uri](Join-Path $explorerDest 'index.html')).AbsoluteUri
  "[InternetShortcut]`r`nURL=$uri" | Set-Content -Encoding ASCII (Join-Path $desk 'Atlas Explorer.url')
  Write-Host 'Desktop shortcut created.'
}

Step 5 'Installing the Cursor rule'
$rule = Join-Path $Atlas $ruleRel
$tracked = & git -C $Atlas ls-files -- '.cursor/rules/atlas-onboarding.mdc'
if ($tracked) { Write-Host 'Cursor rule is tracked in git; left untouched.' -ForegroundColor Yellow }
elseif ((Test-Path $rule) -and -not (Select-String -Path $rule -Pattern $marker -Quiet)) { Write-Host 'A different .cursor rule with this name exists; left untouched.' -ForegroundColor Yellow }
else {
  New-Item -ItemType Directory -Force (Split-Path $rule) | Out-Null
  Copy-Item (Join-Path $here 'cursor\atlas-onboarding.mdc') $rule -Force
  $ex = Get-Exclude $Atlas
  $t = if (Test-Path $ex) { [IO.File]::ReadAllText($ex) } else { '' }
  if ($t -notmatch 'BEGIN atlas-onboarding cursor rule') {
    [IO.File]::AppendAllText($ex, "`n# BEGIN atlas-onboarding cursor rule`n/.cursor/rules/atlas-onboarding.mdc`n# END atlas-onboarding cursor rule`n")
  }
  Write-Host 'Cursor rule installed (git-excluded).'
}

Step 6 'Done'
Write-Host "Agent  : open '$Atlas' in VS Code, Copilot Chat -> pick 'ATLAS Tutor' -> say: Hi (or ask a question)" -ForegroundColor Green
Write-Host "Cursor : open the folder in Cursor, in chat type: @atlas-onboarding  Hi (or ask a question)" -ForegroundColor Green
Write-Host "Visual : double-click '$bat'" -ForegroundColor Green
if (-not $env:ATLAS_ONBOARDING_SILENT) { Start-Process $bat }
