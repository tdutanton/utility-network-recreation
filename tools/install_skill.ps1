# Устанавливает скилл utility-network-drawing в профиль DSH.
#
#   powershell -ExecutionPolicy Bypass -File tools\install_skill.ps1
#   powershell -File tools\install_skill.ps1 -Link     # junction вместо копии
#
# Скилл нужен не приложению, а человеку/агенту, который дорабатывает проект
# или разбирает эскизы вручную. Приложение работает без него.

param(
    [switch]$Link,
    [string]$SkillsDir = (Join-Path $env:USERPROFILE ".dsh\skills")
)

$ErrorActionPreference = "Stop"

$src = (Resolve-Path (Join-Path $PSScriptRoot "..\skills\utility-network-drawing")).Path
$dst = Join-Path $SkillsDir "utility-network-drawing"

if (-not (Test-Path (Join-Path $src "SKILL.md"))) {
    Write-Error "не найден SKILL.md в $src"
    exit 1
}

if (-not (Test-Path $SkillsDir)) {
    New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
}

if (Test-Path $dst) {
    $item = Get-Item $dst -Force
    if ($item.LinkType) {
        Write-Host "убираю прежнюю ссылку: $dst"
        $item.Delete()
    } else {
        Write-Host "заменяю прежнюю копию: $dst"
        Remove-Item -Recurse -Force $dst
    }
}

if ($Link) {
    New-Item -ItemType Junction -Path $dst -Target $src | Out-Null
    Write-Host "скилл связан с репозиторием: $dst -> $src"
} else {
    Copy-Item -Path $src -Destination $dst -Recurse -Force
    Write-Host "скилл скопирован: $dst"
}

$files = Get-ChildItem $dst -Recurse -File
Write-Host "файлов: $($files.Count)"
Write-Host "готово. Скилл появится в новых сессиях DSH."
