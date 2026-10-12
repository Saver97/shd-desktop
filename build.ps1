$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv-release\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw '请先创建 .venv-release 并安装 requirements-build.txt'
}
& $python -m PyInstaller --noconfirm --clean --distpath release --workpath build-release SHDDesktop.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '缺少 .NET Framework C# 编译器，无法生成桌面右键快速入口' }
& $compiler /nologo /target:winexe /optimize+ /out:release\SHDQuick.exe /win32icon:assets\app.ico SHDQuick.cs
if ($LASTEXITCODE -ne 0) { throw "SHDQuick build failed: $LASTEXITCODE" }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot 'release\SHDDesktop.exe')
