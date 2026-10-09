# Privileged READ-ONLY metadata service. Fixed private profile; never broker/secret IO.
$ErrorActionPreference='Stop'
# Provisioning places this file at backend/private/mt5/host/service.ps1.
try {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    if($identity.User.Value -cne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NexusToken {
 [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
 [DllImport("advapi32.dll", SetLastError=true)] public static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
}
'@
    $profile=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'profile.json') -Raw | ConvertFrom-Json
    $boundary=$profile.mt5_root
    $requests=Join-Path $PSScriptRoot 'requests'
    $responses=Join-Path $PSScriptRoot 'responses'
    $seen=[Collections.Generic.HashSet[string]]::new()
    $allowed=@($profile.service_sid,'S-1-5-18','S-1-5-32-544')
    while($true) {
        foreach($file in (Get-ChildItem -LiteralPath $requests -File -Filter '*.json')) {
            if($file.Name -notmatch '^[a-f0-9]{32}\.json$' -or -not $seen.Add($file.Name)){continue}
            try {
                if($file.Length -gt 2048 -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'INVALID_REQUEST'}
                $acl=Get-Acl -LiteralPath $file.FullName
                if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $profile.service_sid){throw 'WRONG_REQUEST_OWNER'}
                $request=Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
                $keys=@($request.PSObject.Properties.Name | Sort-Object)
                $phase='EXECUTION'
                if(($keys -join ',') -ceq 'account_key,nonce,phase,python_pid,run_id') {
                    if($request.phase -notin @('BOOTSTRAP_PREPARE','BOOTSTRAP_READ')){throw 'INVALID_BOOTSTRAP_PHASE'}
                    $phase=$request.phase
                }
                if(($keys -join ',') -notin @('account_key,nonce,python_pid,run_id','account_key,nonce,phase,python_pid,run_id') -or
                    $request.nonce -cne $file.BaseName -or $request.account_key -cne $profile.account_key -or
                    $request.run_id -notmatch '^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$' -or
                    $request.python_pid -isnot [long] -and $request.python_pid -isnot [int] -or $request.python_pid -le 0){throw 'INVALID_REQUEST'}
                $started=[DateTimeOffset]::UtcNow
                $hostEvidence=[ordered]@{dedicated_identity=$false;session_zero=$false;non_admin=$false;exclusive_processes=$false;protected_acl=$false;terminal_pid=0}
                $processes=@(Get-CimInstance Win32_Process)
                $python=@($processes | Where-Object ProcessId -EQ $request.python_pid)
                if($python.Count -ne 1){throw 'PROCESS_MISSING'}
                $owner=Invoke-CimMethod -InputObject $python[0] -MethodName GetOwnerSid
                $hostEvidence.dedicated_identity=($owner.ReturnValue -eq 0 -and $owner.Sid -ceq $profile.service_sid -and $python[0].ExecutablePath -ieq $profile.python_exe)
                $hostEvidence.session_zero=($python[0].SessionId -eq 0)
                # Inspect the actual process token, not merely direct group membership.
                $processHandle=[NexusToken]::OpenProcess(0x1000,$false,$request.python_pid)
                $token=[IntPtr]::Zero
                if($processHandle -eq [IntPtr]::Zero){throw 'TOKEN_UNAVAILABLE'}
                try {
                    if(-not [NexusToken]::OpenProcessToken($processHandle,8,[ref]$token)){throw 'TOKEN_UNAVAILABLE'}
                    $workerIdentity=[Security.Principal.WindowsIdentity]::new($token)
                    try {
                        $workerPrincipal=[Security.Principal.WindowsPrincipal]::new($workerIdentity)
                        $hostEvidence.non_admin=(-not $workerPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
                        if($workerIdentity.User.Value -cne $profile.service_sid){throw 'TOKEN_IDENTITY_MISMATCH'}
                    } finally {$workerIdentity.Dispose()}
                } finally {if($token -ne [IntPtr]::Zero){[void][NexusToken]::CloseHandle($token)};[void][NexusToken]::CloseHandle($processHandle)}
                $exclusive=$true;$terminalPids=@()
                $clientScript=Join-Path $profile.repository_root 'scripts/p3_attestor_client.ps1'
                $clientSuffix='-File "'+$clientScript+'"'
                $powershell=Join-Path $env:SYSTEMROOT 'System32/WindowsPowerShell/v1.0/powershell.exe'
                foreach($p in $processes) {
                    if($p.ProcessId -eq 0){continue}
                    $o=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid
                    if($o.ReturnValue -ne 0){$exclusive=$false;continue}
                    if($o.Sid -cne $profile.service_sid){continue}
                    if($p.SessionId -ne 0){$exclusive=$false}
                    if($p.ExecutablePath -ieq $profile.terminal_exe){$terminalPids += [int]$p.ProcessId}
                    elseif($p.ProcessId -eq $request.python_pid){continue}
                    elseif($p.ParentProcessId -eq $request.python_pid -and $p.ExecutablePath -ieq $powershell -and
                        $p.CommandLine.EndsWith($clientSuffix,[StringComparison]::OrdinalIgnoreCase)){continue}
                    else {$exclusive=$false}
                }
                $expectedTerminals=if($phase -eq 'BOOTSTRAP_PREPARE'){0}else{1}
                $hostEvidence.exclusive_processes=($exclusive -and $terminalPids.Count -eq $expectedTerminals)
                if($terminalPids.Count -eq 1){$hostEvidence.terminal_pid=$terminalPids[0]}
                $protected=$true
                $paths=@($boundary,(Join-Path $boundary 'p3-operator.json'),(Join-Path $boundary 'p3-risk-basis.json'),
                    (Join-Path $boundary 'p3-costs.json'),(Split-Path -Parent $profile.terminal_exe),
                    (Join-Path $profile.verification_root $request.run_id))
                foreach($path in $paths) {
                    if($phase -ne 'EXECUTION' -and $path -in @((Join-Path $boundary 'p3-risk-basis.json'),(Join-Path $boundary 'p3-costs.json')) -and
                        -not (Test-Path -LiteralPath $path)){$path=$boundary}
                    $item=Get-Item -LiteralPath $path
                    if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){$protected=$false}
                    $a=Get-Acl -LiteralPath $path
                    if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $allowed){$protected=$false}
                    foreach($rule in $a.Access) {
                        $sid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
                        if($rule.AccessControlType -eq 'Allow' -and $sid -notin $allowed){$protected=$false}
                    }
                }
                $hostEvidence.protected_acl=$protected
                $completed=[DateTimeOffset]::UtcNow
                $receipt=[ordered]@{version='p3-system-attestor-v1';nonce=$request.nonce;account_key=$request.account_key;
                    run_id=$request.run_id;python_pid=$request.python_pid;started_at=$started.ToString('o');completed_at=$completed.ToString('o');host=$hostEvidence}
                if($phase -ne 'EXECUTION'){$receipt.version='p3-bootstrap-attestor-v1';$receipt.phase=$phase}
                $destination=Join-Path $responses $file.Name
                # Exclusive create: old receipts never overwrite; worker has read-only response ACL.
                $stream=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                try {$bytes=[Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json -Compress -Depth 8));$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
            } catch { [Console]::Error.WriteLine('ATTESTOR_REQUEST_REJECTED') }
        }
        Start-Sleep -Milliseconds 100
    }
} catch { [Console]::Error.WriteLine('ATTESTOR_BLOCKED');exit 2 }
