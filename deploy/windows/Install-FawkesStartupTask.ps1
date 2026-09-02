$ErrorActionPreference = 'Stop'
$taskName = 'Project Fawkes WSL Startup'
$wsl = Join-Path $env:WINDIR 'System32\wsl.exe'
$action = New-ScheduledTaskAction -Execute $wsl -Argument '-d Ubuntu --exec /bin/true'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts the Ubuntu WSL distro invisibly so enabled Fawkes systemd services start.' -Force
Write-Output "Registered: $taskName"
