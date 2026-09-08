# Fixed local Windows clipboard operation. Input is data on stdin, never code.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$mutex=$null;$held=$false;$reply=@{status='failed';code='invalid_request'}
try {
 $chars=New-Object char[] 140001
 $n=[Console]::In.ReadBlock($chars,0,$chars.Length)
 if($n -gt 140000 -or [Console]::In.Peek() -ne -1){throw 'input_bound'}
 $r=(New-Object string($chars,0,$n))|ConvertFrom-Json
 $names=@($r.PSObject.Properties.Name|Sort-Object)-join ','
 if($names -ne 'attempt_id,byte_length,content_b64,content_sha256,expires_epoch,latest_intent_path,snapshot_id,windows_session_id,windows_sid'){throw 'fields'}
 if($r.snapshot_id -isnot [string] -or $r.snapshot_id -notmatch '^console-update-[a-f0-9]{64}$' -or $r.attempt_id -isnot [string] -or $r.attempt_id -notmatch '^[a-f0-9]{32}$'){throw 'identity'}
 if($r.content_b64 -isnot [string] -or $r.content_sha256 -isnot [string] -or $r.content_sha256 -notmatch '^[a-f0-9]{64}$'){throw 'content_identity'}
 if($r.byte_length -isnot [int] -or $r.byte_length -lt 1 -or $r.byte_length -gt 96000){throw 'length'}
 if(($r.expires_epoch -isnot [long] -and $r.expires_epoch -isnot [int]) -or $r.windows_session_id -isnot [int] -or $r.windows_sid -isnot [string]){throw 'types'}
 if($r.latest_intent_path -isnot [string] -or $r.latest_intent_path.Length -gt 3200 -or $r.latest_intent_path -cnotmatch '^\\\\wsl[.]localhost\\[A-Za-z0-9._-]{1,64}\\[^\r\n\x00]+\\native-latest-intent[.]txt$' -or @($r.latest_intent_path.Split('\')|Where-Object {$_ -eq '..'}).Count){throw 'intent_path'}
 $utf8=New-Object Text.UTF8Encoding($false,$true)
 $bytes=[Convert]::FromBase64String($r.content_b64)
 $text=$utf8.GetString($bytes)
 $hash=[Security.Cryptography.SHA256]::Create()
 try{$digest=([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
 if($bytes.Length -ne $r.byte_length -or $digest -cne $r.content_sha256 -or $text.Contains([string][char]0)){throw 'content_mismatch'}
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
 $session=[Diagnostics.Process]::GetCurrentProcess().SessionId
 if($sid -cne $r.windows_sid -or $session -ne $r.windows_session_id -or $session -le 0){throw 'wrong_windows_session'}
 $reply=@{status='failed';code='windows_clipboard_unavailable';attempt_id=$r.attempt_id;snapshot_id=$r.snapshot_id;content_sha256=$digest;byte_length=$bytes.Length;windows_sid=$sid;windows_session_id=$session}
 Add-Type -AssemblyName System.Windows.Forms
 $mutex=New-Object Threading.Mutex($false,('Local\FawkesConsoleClipboard-'+$sid))
 try{$held=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$held=$true}
 if(-not $held){throw 'clipboard_delivery_busy'}
 $epoch=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
 if($r.expires_epoch -lt $epoch -or $r.expires_epoch -gt $epoch+20){throw 'expired'}
 # File opened/read ONLY while holding the same mutex as the clipboard write.
 # Atomic replacement by the service publishes new intent; missing, unreadable,
 # oversized or mismatched state is never permission to use an older request.
 $reply.code='latest_intent_unavailable'
 $fence=[IO.File]::Open($r.latest_intent_path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
 try {
  $fenceBytes=New-Object byte[] 257
  $fenceCount=0
  while($fenceCount -lt 257){$read=$fence.Read($fenceBytes,$fenceCount,257-$fenceCount);if($read -eq 0){break};$fenceCount+=$read}
  $expected=$r.attempt_id+"`n"+$r.snapshot_id+"`n"+$digest+"`n"
  if($fenceCount -gt 256 -or [Text.Encoding]::ASCII.GetString($fenceBytes,0,$fenceCount) -cne $expected){$reply.code='latest_intent_mismatch';throw 'superseded'}
 }finally{$fence.Dispose()}
 $data=New-Object Windows.Forms.DataObject
 $data.SetData([Windows.Forms.DataFormats]::UnicodeText,$false,$text)
 # Persist after helper exit; no retry loop. The latest-intent fence plus the
 # mutex prevents an older surviving helper overtaking a newer confirmation.
 $reply.status='unknown';$reply.code='windows_write_or_readback_uncertain'
 [Windows.Forms.Clipboard]::SetDataObject($data,$true,0,0)
 if([Windows.Forms.Clipboard]::GetText([Windows.Forms.TextDataFormat]::UnicodeText) -cne $text){throw 'readback_mismatch'}
 $reply.status='copied';$reply.code='verified_windows_readback'
 $reply.copied_at=[DateTime]::UtcNow.ToString('o')
}catch{
 # Fixed bounded diagnostics only; no raw snapshot, clipboard or exception text.
}finally{
 if($held){$mutex.ReleaseMutex()}
 if($null -ne $mutex){$mutex.Dispose()}
 $text=$null;$bytes=$null;$r=$null
}
$reply|ConvertTo-Json -Compress
