#!/usr/bin/env bash
set -euo pipefail
powershell_script='C:\\Users\\tjbha\\AppData\\Local\\Temp\\Install-FawkesAttentionTask.ps1'
attention_script='C:\\Users\\tjbha\\AppData\\Local\\Temp\\FawkesAttention.ps1'
cp deploy/windows/Install-FawkesAttentionTask.ps1 /mnt/c/Users/tjbha/AppData/Local/Temp/Install-FawkesAttentionTask.ps1
cp deploy/windows/FawkesAttention.ps1 /mnt/c/Users/tjbha/AppData/Local/Temp/FawkesAttention.ps1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "$powershell_script"
