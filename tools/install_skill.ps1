# Устанавливает скиллы из skills/ в профиль DSH.
#
#   powershell -ExecutionPolicy Bypass -File tools\install_skill.ps1
#   powershell -File tools\install_skill.ps1 -Link            # junction вместо копии
#   powershell -File tools\install_skill.ps1 -Name gost-drafting
#
# Скиллы нужны не приложению, а человеку/агенту, который дорабатывает проект
# или разбирает эскизы вручную. Приложение работает без них.

param(
    [switch]$Link,
    [Alias("Name")]
    [string]$Skill = "",
    [string]$SkillsDir = (Join-Path $env:USERPROFILE ".dsh\skills")
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\skills")).Path
if (-not (Test-Path $SkillsDir)) {
    New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null
}

$sources = Get-ChildItem -Path $root -Directory | Where-Object {
    (-not $Skill) -or ($_.Name -eq $Skill)
}

if (-not $sources) {
    Write-Error "в $root нет скиллов (фильтр: '$Skill')"
    exit 1
}

$total = 0
foreach ($src in $sources) {
    if (-not (Test-Path (Join-Path $src.FullName "SKILL.md"))) {
        Write-Host "пропускаю $($src.Name): нет SKILL.md"
        continue
    }
    $dst = Join-Path $SkillsDir $src.Name

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
        New-Item -ItemType Junction -Path $dst -Target $src.FullName | Out-Null
        Write-Host "связан: $dst -> $($src.FullName)"
    } else {
        Copy-Item -Path $src.FullName -Destination $dst -Recurse -Force
        Write-Host "скопирован: $dst"
    }
    $total += (Get-ChildItem $dst -Recurse -File).Count
}

Write-Host "файлов всего: $total"
Write-Host "готово. Скиллы появятся в новых сессиях DSH."
