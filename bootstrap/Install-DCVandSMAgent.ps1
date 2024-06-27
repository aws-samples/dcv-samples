<powershell>
<#
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#>
$SessMgrDNS = "SESSION-MGR-PRIVATE-DNS"
$BrokerAgentConnectionPort = "8445"
$token = Invoke-RestMethod -Headers @{'X-aws-ec2-metadata-token-ttl-seconds' = '21600'} -Method PUT -Uri http://169.254.169.254/latest/api/token
$instanceType = Invoke-RestMethod -Headers @{'X-aws-ec2-metadata-token' = $token} -Method GET -Uri http://169.254.169.254/latest/meta-data/instance-type
$OSVersion = ((Get-ItemProperty -Path "Microsoft.PowerShell.Core\Registry::\HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -Name ProductName).ProductName) -replace  "[^0-9]" , ''
if((($OSVersion -ne "2019") -and ($OSversion -ne "2022") -and ($OSversion -ne "10") -and ($OSversion -ne "11")) -and (($InstanceType[0] -ne 'g') -or ($InstanceType[0] -ne 'p'))){
    $VirtualDisplayDriverRequired = $true
}
$token = Invoke-RestMethod -Headers @{"X-aws-ec2-metadata-token-ttl-seconds" = "21600"} -Method PUT -Uri http://169.254.169.254/latest/api/token
$instanceType = Invoke-RestMethod -Headers @{"X-aws-ec2-metadata-token" = $token} -Method GET -Uri http://169.254.169.254/latest/meta-data/instance-type
if($VirtualDisplayDriverRequired){
    Start-Job -Name WebReq -ScriptBlock { Invoke-WebRequest -uri https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-virtual-display-x64-Release.msi -OutFile C:\Windows\Temp\DCVDisplayDriver.msi ; Invoke-WebRequest -uri https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-server-x64-Release.msi -OutFile C:\Windows\Temp\DCVServer.msi }  
}else{
    Start-Job -Name WebReq -ScriptBlock { Invoke-WebRequest -uri https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-server-x64-Release.msi -OutFile C:\Windows\Temp\DCVServer.msi }  
}
Wait-Job -Name WebReq
if($VirtualDisplayDriverRequired){
    Invoke-Command -ScriptBlock {Start-Process "msiexec.exe" -ArgumentList "/I C:\Windows\Temp\DCVDisplayDriver.msi /quiet /norestart" -Wait}
}
Invoke-Command -ScriptBlock {Start-Process "msiexec.exe" -ArgumentList "/I C:\Windows\Temp\DCVServer.msi ADDLOCAL=ALL /quiet /norestart /l*v dcv_install_msi.log " -Wait}
while (-not(Get-Service dcvserver -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 250 }
$dcvPath = "Microsoft.PowerShell.Core\Registry::\HKEY_USERS\S-1-5-18\Software\GSettings\com\nicesoftware\dcv"
Set-ItemProperty -Path "$dcvPath\session-management" -Name create-session -Value 0 -force
New-ItemProperty -Path "$dcvPath\connectivity" -Name enable-quic-frontend -PropertyType DWORD -Value 1 -force
New-ItemProperty -Path "$dcvPath\security" -Name "auth-token-verifier" -Value "https://$SessMgrDNS`:$BrokerAgentConnectionPort/agent/validate-authentication-token" -Force
New-ItemProperty -Path "$dcvPath\security" -Name no-tls-strict -PropertyType DWORD -Value 1 -force
Stop-Service dcvserver

Start-Job -Name SMWebReq -ScriptBlock { Invoke-WebRequest -uri https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-session-manager-agent-x64-Release.msi -OutFile C:\Windows\Temp\DCVSMAgent.msi }  
Wait-Job -Name SMWebReq
Invoke-Command -ScriptBlock {Start-Process "msiexec.exe" -ArgumentList "/I C:\Windows\Temp\DCVSMAgent.msi /quiet /norestart " -Wait}
while (-not(Get-Service DcvSessionManagerAgentService -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 250 }
Stop-Service DcvSessionManagerAgentService

# SET AGENT.CONF
$AgentConfContent = "version = '0.1'
[agent]
broker_host = '$SessMgrDNS'
broker_port = $BrokerAgentConnectionPort
tls_strict = false
broker_update_interval = 15
[log]
level = 'debug'
rotation = 'daily'
"
$AgentConfFolder = "C:\Program Files\NICE\DCVSessionManagerAgent\conf"
New-Item -Path $AgentConfFolder -Name "agent.conf" -ItemType File -Force -Value "$AgentConfContent"

Set-Service -Name DcvSessionManagerAgentService -StartupType Automatic
Start-Service dcvserver
Start-Service DcvSessionManagerAgentService
</powershell>