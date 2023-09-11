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

.SYNOPSIS
    This script is intended to generate usage reports for WSP Amazon WorkSpaces.
.DESCRIPTION
    A secheduled task should be pushed via Group Policy that will invoke the local script every minute
    on a WSP WorkSpace. The script will create a CSV for each day and records hostname, sessions start time, 
    session end time, username, and total session duration. These reports can be further analized by ingesting 
    into a visualization logging mechanism. To deploy this task, it is recommended to use a Group Policy Object,
    as WorkSpaces require AD DS. Alternatively, the scheduled task can be created locally.
.EXAMPLE
    Scheduled task arguement to execute local script. Path can be modified to your script location.
        -noprofile -ExecutionPolicy Unrestricted -file "C:\Program Files\Amazon\Build-WSPUsageReports.ps1"
    Scheduled task arguement to execute local script with a provided path. The path must exist locally.
        -noprofile -ExecutionPolicy Unrestricted -file "C:\Program Files\Amazon\Build-WSPUsageReports.ps1" -usageReportsFolder "C:\path"
#>
[CmdletBinding()]
Param (
    [Parameter(Mandatory=$false)]
    [string]$usageReportsFolder
)

$today = Get-Date
$reportId = $today.Month.ToString() + "-" + $today.Day.ToString() + "-" + $today.Year.ToString()
if($usageReportsFolder -eq ''){
    $usageReportsFolder = "C:\Windows\Temp\WSPUsageReports"
}else{
    if(-not(Test-Path -Path $usageReportsFolder)){ 
        write-host "Provided path not found. Reverting to default path."
        $usageReportsFolder = "C:\Windows\Temp\WSPUsageReports"
    }
}
$outfile = "$usageReportsFolder\$reportId.csv"
if(-not(Test-Path -Path $usageReportsFolder)){ 
    New-Item $usageReportsFolder -ItemType Directory -ea 0
}
if(-not(Test-Path -Path $outfile)){
    {} | Select "Hostname","LogonTime","LogoffTime","User","SessionTime" | Export-Csv $outfile -NoTypeInformation 
}
$hostname = $env:computername
$user = (Get-ChildItem D:\Users\)[0].Name
$sessionInfo = .'C:\Program Files\NICE\DCV\Server\bin\dcv.exe' list-sessions console -j | ConvertFrom-Json
if ($sessionInfo.'num-of-connections' -ne 0){
    $connectionInfo = .'C:\Program Files\NICE\DCV\Server\bin\dcv.exe' list-connections console -j | ConvertFrom-Json
    $sessionStart = '{0:HH:mm:ss}' -f ([DateTime](($connectionInfo.'connection-time').Split('T')).Split('.')[1])
    $importReport = Import-CSV -Path $outfile
    if (-not($importReport.LogonTime.Contains($sessionStart))){
        $inputLogonTime = [PSCustomObject]@{
            Hostname = $hostname
            LogonTime = $sessionStart
            LogoffTime = ''
            User = $user
            SessionTime = '00:00:00'
        }
        $inputLogonTime | Export-Csv $outfile -Append
    }
}
if ($sessionInfo.'last-disconnection-time' -ne ''){
    if (([DateTime]($sessionInfo.'last-disconnection-time').Split('T')[0]).Day -eq $today.Day){
        $disconnectedTime = '{0:HH:mm:ss}' -f ([DateTime]((($sessionInfo.'last-disconnection-time')).Split('T')).Split('.')[1])
    }else{
        $disconnectedTime = ''
    }
}else{
    $disconnectedTime = ''
}
$importReport = Import-CSV -Path $outfile
$updateReport = foreach ($line in $importReport){
    if (($line.LogoffTime -eq '') -and ($line.LogonTime -ne '') -and ($disconnectedTime -ne '')){
        if ((New-TimeSpan -Start $disconnectedTime -End $today) -lt (New-TimeSpan -Start $line.LogonTime -End $today)){
            $line.LogoffTime = $disconnectedTime
            $sessionTime = New-TimeSpan -Start $line.LogonTime -End $line.LogoffTime
            $sessionTime = $sessionTime.Hours.ToString() + ':' + $sessionTime.Minutes.ToString() + ':' +$sessionTime.Seconds.ToString()
            $line.SessionTime = $sessionTime
        }
        $line
    } elseif ($line.LogonTime -ne ''){
        $line
    }
}   
$updateReport | Export-Csv $outfile -NoTypeInformation
$verifyFile = Get-Content $outfile
if ($null -eq $verifyFile){
    {} | Select "Hostname","LogonTime","LogoffTime","User","SessionTime" | Export-Csv $outfile -NoTypeInformation 
}