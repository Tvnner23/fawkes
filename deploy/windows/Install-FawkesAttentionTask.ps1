$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'Fawkes'
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
$source = Join-Path $PSScriptRoot 'FawkesAttention.ps1'
$installed = Join-Path $installRoot 'FawkesAttention.ps1'
Copy-Item -Force $source $installed
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$installed`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'Project Fawkes Attention' -Action $action -Trigger $trigger -Settings $settings -Description 'Surface durable Project Fawkes Rider-attention events.' -Force | Out-Null
Write-Output 'Project Fawkes Attention task installed.'
