$ErrorActionPreference = 'Stop'
$stateRoot = Join-Path $env:LOCALAPPDATA 'Fawkes\Attention'
$statePath = Join-Path $stateRoot 'seen.json'
$receiptPath = Join-Path $stateRoot 'failure-receipts.jsonl'
$appId = 'ProjectFawkes.Attention'
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$seen = @()
$activeAttention = @{}
$activeFailure = $null
if (Test-Path $statePath) {
  try {
    $retainedState = Get-Content -Raw $statePath | ConvertFrom-Json
    $seen = @($retainedState.seen)
    if ($retainedState.active_attention) {
      foreach ($entry in $retainedState.active_attention.PSObject.Properties) {
        $activeAttention[$entry.Name] = $entry.Value
      }
    }
  } catch { $seen = @(); $activeAttention = @{} }
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
function Save-AttentionState {
  @{seen=@($seen | Select-Object -Unique); active_attention=$activeAttention;
    updated_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $statePath
}
function Test-FawkesAttentionPending([string]$attentionId) {
  $arguments = @('-d','Ubuntu','--exec','/usr/bin/env','-C','/home/tvnner/.local/lib/fawkes-production/current','/home/tvnner/.local/lib/fawkes-production/venv/bin/python','-B','scripts/fawkes_attention_events.py','--pending-attention',$attentionId)
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = 'SilentlyContinue'
  $rawStatus = & wsl.exe @arguments 2>$null
  $statusExit = $LASTEXITCODE
  $ErrorActionPreference = $previousPreference
  if ($statusExit -ne 0 -or -not $rawStatus) { return $false }
  try { return [bool](($rawStatus | ConvertFrom-Json).pending) } catch { return $false }
}
function Remove-ResolvedFawkesToasts {
  foreach ($eventId in @($activeAttention.Keys)) {
    $entry = $activeAttention[$eventId]
    if (-not (Test-FawkesAttentionPending ([string]$entry.source_id))) {
      [Windows.UI.Notifications.ToastNotificationManager]::History.Remove(
        [string]$entry.tag, 'FawkesAttention', $appId)
      $activeAttention.Remove($eventId)
      Save-AttentionState
    }
  }
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
    Remove-ResolvedFawkesToasts
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
        $pendingDecisions = @($events | Where-Object { $_.kind -eq 'needs_tanner' } | Sort-Object created_at -Descending)
        $foreground = @($events | Where-Object { $_.focus -eq $true } | Sort-Object created_at -Descending)
        $primary = if ($pendingDecisions.Count -gt 0) { $pendingDecisions[0] } elseif ($foreground.Count -gt 0) { $foreground[0] } else { $events[-1] }
        $title = if ($events.Count -gt 1) { "Fawkes needs Tanner ($($events.Count) updates)" } else { [string]$primary.title }
        $message = if ($events.Count -gt 1) { 'Open the Fawkes attention inbox for the exact decision and evidence.' } else { [string]$primary.safe_message }
        $activation = if ($primary.kind -eq 'needs_tanner') {
          'fawkes-attention://open?attention=' + [Uri]::EscapeDataString([string]$primary.source_id)
        } else { 'fawkes-attention://status' }
        if ($primary.kind -eq 'needs_tanner' -and -not (Test-FawkesAttentionPending ([string]$primary.source_id))) {
          $seen += [string]$primary.event_id
          Save-AttentionState
          Start-Sleep -Seconds 3
          continue
        }
        $eventId = [string]$primary.event_id
        $tag = $eventId.Substring([Math]::Max(0, $eventId.Length - 16))
        Show-FawkesToast $title $message $activation $tag
        if ($primary.kind -eq 'needs_tanner') {
          $activeAttention[$eventId] = @{source_id=[string]$primary.source_id; tag=$tag;
            submitted_at=(Get-Date).ToUniversalTime().ToString('o'); detail_url=[string]$primary.detail_url}
        }
        $seen += @($events | ForEach-Object { $_.event_id })
        Save-AttentionState
      }
    }
    Start-Sleep -Seconds 3
  }
} catch {
  $failure = 'fawkes-windows-attention-' + [guid]::NewGuid().ToString('N')
  Write-AttentionReceipt 'failure' $failure 1 $false 'failed'
  throw
}
