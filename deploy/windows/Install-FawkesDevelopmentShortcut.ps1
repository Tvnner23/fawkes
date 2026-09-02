$ErrorActionPreference = 'Stop'
$content = "[InternetShortcut]`r`nURL=http://localhost:8787/?view=developer`r`n"
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Fawkes Development.url'
$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Fawkes Development.url'
[IO.File]::WriteAllText($desktop, $content)
[IO.File]::WriteAllText($startMenu, $content)
Write-Output 'Installed Fawkes Development shortcuts.'
