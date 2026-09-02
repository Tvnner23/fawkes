$ErrorActionPreference = 'Stop'
$installRoot = Join-Path $env:LOCALAPPDATA 'Fawkes'
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
$source = Join-Path $PSScriptRoot 'FawkesAttention.ps1'
$installed = Join-Path $installRoot 'FawkesAttention.ps1'
Copy-Item -Force $source $installed
$iconPath = Join-Path $installRoot 'FawkesAttention.png'
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object Drawing.Bitmap 64,64
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([Drawing.Color]::FromArgb(23,27,34))
$font = New-Object Drawing.Font 'Segoe UI',36,([Drawing.FontStyle]::Bold)
$brush = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(238,132,65))
$graphics.DrawString('F',$font,$brush,13,5)
$bitmap.Save($iconPath,[Drawing.Imaging.ImageFormat]::Png)
$brush.Dispose(); $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
$launcherPath = Join-Path $installRoot 'FawkesAttentionLauncher.exe'
$launcherSource = @'
using System;
using System.Diagnostics;
using System.Text.RegularExpressions;
public static class FawkesAttentionLauncher {
 [STAThread] public static void Main(string[] args) {
  string target = "http://localhost:8787/?view=developer&section=attention";
  if (args.Length > 0 && args[0].StartsWith("fawkes-attention://open?", StringComparison.OrdinalIgnoreCase)) {
   Uri uri; if (!Uri.TryCreate(args[0], UriKind.Absolute, out uri)) return;
   string query = uri.Query.TrimStart('?');
   if (!query.StartsWith("attention=", StringComparison.Ordinal)) return;
   string id = Uri.UnescapeDataString(query.Substring(10));
   if (!Regex.IsMatch(id, "^attention-[a-f0-9]{64}$")) return;
   target += "&attention=" + Uri.EscapeDataString(id);
  } else if (args.Length > 0 && !args[0].Equals("fawkes-attention://status", StringComparison.OrdinalIgnoreCase)) return;
  Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
 }
}
'@
Add-Type -TypeDefinition $launcherSource -Language CSharp -OutputAssembly $launcherPath -OutputType WindowsApplication
$protocol = 'HKCU:\Software\Classes\fawkes-attention'
New-Item -Path $protocol -Force | Out-Null
Set-ItemProperty -Path $protocol -Name '(Default)' -Value 'URL:Fawkes Attention Protocol'
Set-ItemProperty -Path $protocol -Name 'URL Protocol' -Value ''
New-Item -Path "$protocol\DefaultIcon" -Force | Out-Null
Set-ItemProperty -Path "$protocol\DefaultIcon" -Name '(Default)' -Value "$launcherPath,0"
New-Item -Path "$protocol\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$protocol\shell\open\command" -Name '(Default)' -Value ('"' + $launcherPath + '" "%1"')
$shortcutPath = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Fawkes Attention.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.Arguments = ''
$shortcut.Description = 'Project Fawkes attention and Rider decisions'
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
$shortcut.Save()
$propertySetter = @'
using System;
using System.Runtime.InteropServices;
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
interface IPropertyStore { uint GetCount(); void GetAt(uint i, out PROPERTYKEY k); void GetValue(ref PROPERTYKEY k, out PROPVARIANT v); void SetValue(ref PROPERTYKEY k, ref PROPVARIANT v); void Commit(); }
[StructLayout(LayoutKind.Sequential, Pack=4)] struct PROPERTYKEY { public Guid fmtid; public uint pid; public PROPERTYKEY(Guid f,uint p){fmtid=f;pid=p;} }
[StructLayout(LayoutKind.Explicit)] struct PROPVARIANT { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr pwszVal; }
public static class FawkesShortcutIdentity {
 [DllImport("shell32.dll", CharSet=CharSet.Unicode)] static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr bind, uint flags, ref Guid iid, out IPropertyStore store);
 [DllImport("ole32.dll")] static extern int PropVariantClear(ref PROPVARIANT value);
 public static void Set(string path,string id) { Guid iid=new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"); IPropertyStore store; Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path,IntPtr.Zero,2,ref iid,out store)); var key=new PROPERTYKEY(new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),5); var value=new PROPVARIANT{vt=31,pwszVal=Marshal.StringToCoTaskMemUni(id)}; try{store.SetValue(ref key,ref value);store.Commit();}finally{PropVariantClear(ref value);Marshal.ReleaseComObject(store);} }
}
'@
Add-Type -TypeDefinition $propertySetter -Language CSharp
[FawkesShortcutIdentity]::Set($shortcutPath, 'ProjectFawkes.Attention')
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$installed`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'Project Fawkes Attention' -Action $action -Trigger $trigger -Settings $settings -Description 'Surface durable Project Fawkes Rider-attention events.' -Force | Out-Null
Write-Output 'Project Fawkes Attention task installed.'
