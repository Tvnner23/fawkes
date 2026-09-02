$ErrorActionPreference = 'Stop'
$stateRoot = Join-Path $env:LOCALAPPDATA 'Fawkes\Attention'
$statePath = Join-Path $stateRoot 'seen.json'
$receiptPath = Join-Path $stateRoot 'failure-receipts.jsonl'
$appId = 'ProjectFawkes.Attention'
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$seen = @()
$activeFailure = $null
if (Test-Path $statePath) {
  try { $seen = @((Get-Content -Raw $statePath | ConvertFrom-Json).seen) } catch { $seen = @() }
}

function Escape-Xml([string]$value) { return [Security.SecurityElement]::Escape($value) }
function Show-FawkesToast($title, $message, $activationUri, $tag) {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
  $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
  $iconUri = 'file:///' + ((Join-Path $env:LOCALAPPDATA 'Fawkes\FawkesAttention.png') -replace '\\','/')
  $xml.LoadXml("<toast activationType='protocol' launch='$(Escape-Xml $activationUri)'><visual><binding template='ToastGeneric'><image placement='appLogoOverride' hint-crop='circle' src='$(Escape-Xml $iconUri)'/><text>$(Escape-Xml $title)</text><text>$(Escape-Xml $message)</text><text placement='attribution'>Project Fawkes</text></binding></visual></toast>")
  $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
  $toast.Tag = ([string]$tag).Substring(0, [Math]::Min(16, ([string]$tag).Length))
  $toast.Group = 'FawkesAttention'
  $toast.ExpiresOnReboot = $false
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
}
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
    if ($activeFailure) { Write-AttentionReceipt 'recovery' $activeFailure 0 $true 'running'; $activeFailure = $null }
    if ($raw) {
      $events = @(($raw | ConvertFrom-Json).events)
      if ($events.Count -gt 0) {
        $foreground = @($events | Where-Object { $_.focus -eq $true })
        $primary = if ($foreground.Count -gt 0) { $foreground[0] } else { $events[0] }
        $title = if ($events.Count -gt 1) { "Fawkes needs Tanner ($($events.Count) updates)" } else { [string]$primary.title }
        $message = if ($events.Count -gt 1) { 'Open the Fawkes attention inbox for the exact decision and evidence.' } else { [string]$primary.safe_message }
        $activation = if ($primary.kind -eq 'needs_tanner') {
          'fawkes-attention://open?attention=' + [Uri]::EscapeDataString([string]$primary.source_id)
        } else { 'fawkes-attention://status' }
        Show-FawkesToast $title $message $activation ([string]$primary.event_id)
        $seen += @($events | ForEach-Object { $_.event_id })
        @{seen=@($seen | Select-Object -Unique); updated_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -Encoding UTF8 $statePath
      }
    }
    Start-Sleep -Seconds 15
  }
} catch {
  $failure = 'fawkes-windows-attention-' + [guid]::NewGuid().ToString('N')
  Write-AttentionReceipt 'failure' $failure 1 $false 'failed'
  throw
}
