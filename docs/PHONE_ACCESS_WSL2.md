# Private iPhone Access from WSL2

## Diagnosed path

The current host uses WSL2 NAT.

```text
iPhone on home Wi-Fi
  -> Windows Ethernet 2: 192.168.1.69:8787
  -> Windows TCP port proxy
  -> WSL2: 172.27.231.173:8787
  -> token-authenticated Fawkes app
```

The inspected pre-configuration state was:

- Windows `Ethernet 2`: `192.168.1.69`, classified `Public`;
- Windows port 8787: listening on `127.0.0.1` only;
- no port-proxy rule;
- no `Fawkes Chat 8787` firewall rule.

The phone cannot route directly to the WSL NAT address. Do not expose a router
port and do not disable either firewall.

## 1. Restart Fawkes inside WSL

Stop the old local-only process. Start the authenticated listener:

```bash
cd /home/tvnner/fawkes
export OPENAI_API_KEY='YOUR_PROVIDER_KEY'
export FAWKES_APP_TOKEN='A_LONG_RANDOM_SECRET'
.venv/bin/python src/fawkes.py app
```

With a token configured, Fawkes defaults to `0.0.0.0:8787`. Confirm in a second
WSL terminal:

```bash
ss -ltn | grep ':8787'
curl -i http://172.27.231.173:8787/
```

The listener should show `0.0.0.0:8787`, not `127.0.0.1:8787`.

## 2. Configure the Windows private-network bridge

Open **Windows PowerShell as Administrator**. These commands deliberately bind
only the current home-LAN address and allow only the local subnet on the
Private firewall profile:

```powershell
Set-NetConnectionProfile -InterfaceAlias 'Ethernet 2' -NetworkCategory Private

Set-Service iphlpsvc -StartupType Automatic
Start-Service iphlpsvc

netsh interface portproxy add v4tov4 `
  listenaddress=192.168.1.69 listenport=8787 `
  connectaddress=172.27.231.173 connectport=8787

New-NetFirewallRule `
  -DisplayName 'Fawkes Chat 8787' `
  -Direction Inbound -Action Allow -Protocol TCP `
  -LocalAddress 192.168.1.69 -LocalPort 8787 `
  -RemoteAddress LocalSubnet -Profile Private
```

Verify:

```powershell
Get-NetConnectionProfile -InterfaceAlias 'Ethernet 2'
netsh interface portproxy show v4tov4
Get-NetFirewallRule -DisplayName 'Fawkes Chat 8787' |
  Get-NetFirewallPortFilter
Test-NetConnection 192.168.1.69 -Port 8787
```

On the iPhone, while connected to the same home Wi-Fi, open:

```text
http://192.168.1.69:8787
```

Enter `FAWKES_APP_TOKEN` when prompted. The provider key stays on the computer.

## WSL address changes

WSL NAT addresses can change after `wsl --shutdown`, Windows restart, or network
reconfiguration. If `hostname -I` in WSL no longer reports `172.27.231.173`, run
the following in Administrator PowerShell using the new address:

```powershell
netsh interface portproxy delete v4tov4 `
  listenaddress=192.168.1.69 listenport=8787

netsh interface portproxy add v4tov4 `
  listenaddress=192.168.1.69 listenport=8787 `
  connectaddress=NEW_WSL_ADDRESS connectport=8787
```

If the Windows LAN address changes, recreate both the proxy and firewall rule
with the new Windows address. A DHCP reservation for `192.168.1.69` in the home
router makes the Windows side stable without exposing any public port.

## Removal

To remove only the Fawkes bridge later:

```powershell
netsh interface portproxy delete v4tov4 `
  listenaddress=192.168.1.69 listenport=8787
Remove-NetFirewallRule -DisplayName 'Fawkes Chat 8787'
```

No router port-forwarding, UPnP rule, public firewall profile, or unauthenticated
non-loopback listener is required.
