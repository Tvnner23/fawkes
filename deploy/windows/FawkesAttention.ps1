$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$stateRoot = Join-Path $env:LOCALAPPDATA 'Fawkes\Attention'
$statePath = Join-Path $stateRoot 'seen.json'
$receiptPath = Join-Path $stateRoot 'failure-receipts.jsonl'
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$seen = @()
if (Test-Path $statePath) {
  try { $seen = @((Get-Content -Raw $statePath | ConvertFrom-Json).seen) } catch { $seen = @() }
}
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.Text = 'Project Fawkes'
$activeFailure = $null
function Write-AttentionReceipt($type, $failureId, $exitCode, $recovered, $state) {
  $record = [ordered]@{schema_version=1; receipt_type=$type; failure_id=$failureId;
    timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); component='windows_attention_manager';
    lifecycle_stage='poll_wsl_attention'; failure_category='attention_delivery_failure';
    process_exit_code=$exitCode; provider_code=$null; exception_type='WslAttentionPollFailure';
    safe_message='The credential-free WSL attention poll failed.'; restart_attempt=1;
    recovered=$recovered; final_service_state=$state}
  ($record | ConvertTo-Json -Compress) | Add-Content -Encoding UTF8 $receiptPath
}
try {
  while ($true) {
    $arguments = @('-d','Ubuntu','--exec','/usr/bin/env','-C','/home/tvnner/.local/lib/fawkes-production/current','/home/tvnner/.local/lib/fawkes-production/venv/bin/python','-B','scripts/fawkes_attention_events.py')
    foreach ($item in $seen) { $arguments += @('--seen', [string]$item) }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $raw = & wsl.exe @arguments 2>$null
    $pollExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($pollExit -ne 0) {
      if (-not $activeFailure) {
        $activeFailure = 'fawkes-windows-attention-' + [guid]::NewGuid().ToString('N')
        Write-AttentionReceipt 'failure' $activeFailure $pollExit $false 'recovering'
      }
      Start-Sleep -Seconds 15
      continue
    }
    if ($activeFailure) {
      Write-AttentionReceipt 'recovery' $activeFailure 0 $true 'running'
      $activeFailure = $null
    }
    if ($LASTEXITCODE -eq 0 -and $raw) {
      $payload = $raw | ConvertFrom-Json
      $events = @($payload.events)
      if ($events.Count -gt 0) {
        $foreground = @($events | Where-Object { $_.focus -eq $true })
        $notify.BalloonTipTitle = if ($events.Count -gt 1) { "Fawkes has $($events.Count) updates" } else { [string]$events[0].title }
        $notify.BalloonTipText = if ($events.Count -gt 1) { 'Open the Fawkes attention inbox for details.' } else { [string]$events[0].safe_message }
        $notify.ShowBalloonTip(10000)
        if ($foreground.Count -gt 0) { Start-Process 'http://localhost:8787/?view=developer&section=attention' }
        $seen += @($events | ForEach-Object { $_.event_id })
        @{seen=@($seen | Select-Object -Unique); updated_at=(Get-Date).ToUniversalTime().ToString('o')} |
          ConvertTo-Json | Set-Content -Encoding UTF8 $statePath
      }
    }
    Start-Sleep -Seconds 15
  }
} finally {
  $notify.Visible = $false
  $notify.Dispose()
}
