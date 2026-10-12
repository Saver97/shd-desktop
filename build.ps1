$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = if ($env:SHD_BUILD_PYTHON) { $env:SHD_BUILD_PYTHON } else {
    Join-Path $PSScriptRoot '.venv-release\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '请先创建 .venv-release 并安装 requirements-build.txt'
}
$version = '1.0.4'
$buildRoot = Join-Path $PSScriptRoot "build-single\$version"
$innerDir = Join-Path $buildRoot 'inner'
$innerExe = Join-Path $innerDir 'SHDDesktop.exe'
$generated = Join-Path $buildRoot 'SHDLauncher.generated.cs'
$outputDir = Join-Path $PSScriptRoot "release-candidate\$version"
$outputExe = Join-Path $outputDir 'SHDDesktop.exe'
New-Item -ItemType Directory -Force -Path $buildRoot, $innerDir, $outputDir | Out-Null
& $python -m PyInstaller --noconfirm --clean --distpath $innerDir --workpath (Join-Path $buildRoot 'work') (Join-Path $PSScriptRoot 'packaging\SHDDesktop.spec')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '缺少 .NET Framework C# 编译器，无法生成单文件启动器' }
$payloadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $innerExe).Hash.ToLowerInvariant()
$template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'packaging\SHDLauncher.cs') -Raw -Encoding UTF8
if (-not $template.Contains('__PAYLOAD_SHA256__')) { throw '启动器缺少资源哈希占位符' }
$template.Replace('__PAYLOAD_SHA256__', $payloadHash) | Set-Content -LiteralPath $generated -Encoding UTF8
& $compiler /nologo /target:winexe /optimize+ "/out:$outputExe" '/win32icon:assets\app.ico' "/resource:$innerExe,SHD.Payload" $generated
if ($LASTEXITCODE -ne 0) { throw "SHDLauncher build failed: $LASTEXITCODE" }
Get-FileHash -Algorithm SHA256 -LiteralPath $outputExe
