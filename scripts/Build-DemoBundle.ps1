param(
  [string]$BundleRoot = (Join-Path $PSScriptRoot '..\demo\bundle'),
  [string]$LynxRoot = (Join-Path $PSScriptRoot '..\third_party\lynx')
)

$ErrorActionPreference = 'Stop'

function Resolve-ExistingPath([string]$Path, [string]$Name) {
  $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
  if (-not $resolved) {
    throw "$Name not found: $Path"
  }
  return $resolved.Path
}

function Remove-LinkOrDirectory([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }
  $item = Get-Item -LiteralPath $Path -Force
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    [IO.Directory]::Delete($item.FullName)
    return
  }
  Remove-Item -LiteralPath $Path -Recurse -Force
}

function New-DependencyJunction(
  [string]$NodeModules,
  [string]$OfficialNodeModules,
  [string]$PackageName
) {
  $link = Join-Path $NodeModules $PackageName
  $target = Join-Path $OfficialNodeModules $PackageName
  if (-not (Test-Path -LiteralPath $target)) {
    throw "Official node package not found: $target. Run cmake --build --preset deps first."
  }
  $scope = Split-Path -Parent $link
  New-Item -ItemType Directory -Force -Path $scope | Out-Null
  Remove-LinkOrDirectory $link
  New-Item -ItemType Junction -Path $link -Target $target | Out-Null
}

$bundle = Resolve-ExistingPath $BundleRoot 'demo bundle root'
$lynx = Resolve-ExistingPath $LynxRoot 'Lynx source root'
$officialNodeModules = Join-Path $lynx 'node_modules'
$node = Join-Path $lynx 'buildtools\node\node.exe'
$rspeedy = Join-Path $officialNodeModules '@lynx-js\rspeedy\bin\rspeedy.js'

if (-not (Test-Path -LiteralPath $node)) {
  throw "Official Node.js not found: $node. Run cmake --build --preset deps first."
}
if (-not (Test-Path -LiteralPath $rspeedy)) {
  throw "Official rspeedy not found: $rspeedy. Run cmake --build --preset deps first."
}

$nodeModules = Join-Path $bundle 'node_modules'
New-Item -ItemType Directory -Force -Path $nodeModules | Out-Null
New-DependencyJunction $nodeModules $officialNodeModules '@lynx-js\react'
New-DependencyJunction $nodeModules $officialNodeModules '@lynx-js\react-rsbuild-plugin'
New-DependencyJunction $nodeModules $officialNodeModules '@lynx-js\rspeedy'
New-DependencyJunction $nodeModules $officialNodeModules '@rsbuild\plugin-sass'
New-DependencyJunction $nodeModules $officialNodeModules 'typescript'

Push-Location -LiteralPath $bundle
try {
  & $node $rspeedy build
  if ($LASTEXITCODE -ne 0) {
    throw "rspeedy build failed with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}
