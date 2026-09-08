# One native terminal for the same retained Worker. No prompt, decision or key.
$ErrorActionPreference='Stop'
$mutex=New-Object Threading.Mutex($false,'Local\FawkesSameWorkerNativeTerminal')
$owned=$false
try{
 try{$owned=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
 if(-not $owned){exit 0}
 Write-Output 'Same Fawkes Worker; waiting for any existing standalone owner to finish. No owner will be stopped.'
 while($true){
  & wsl.exe -d Ubuntu --exec /home/tvnner/fawkes/.venv/bin/python -B /home/tvnner/.local/share/fawkes-worker-link/pi_worker_link.py attach
  $exit=$LASTEXITCODE
  if($exit -eq 0){break} # Explicit /quit remains a stop, not automatic new work.
  if($exit -eq 78){throw 'Accepted Worker startup binding needs reconciliation; no automatic bypass.'}
  if($exit -eq 75){Write-Output 'Existing same-thread owner preserved; waiting.'}
  else{Write-Output 'Worker connection interrupted; retrying the same connection without sending input.'}
  Start-Sleep -Seconds 10
 }
}finally{if($owned){$mutex.ReleaseMutex()};$mutex.Dispose()}
