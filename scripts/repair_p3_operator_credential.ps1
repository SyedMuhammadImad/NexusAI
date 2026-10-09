param([switch]$Repair,[string]$ExpectedScriptHash='')
# Explicit owner-approved Windows credential repair; no broker or MT5 config read.
$ErrorActionPreference='Stop'
$stage='AUTHORIZATION'
try {
    if(-not $Repair) {
        [ordered]@{status='PLAN_ONLY';account='DEDICATED_WINDOWS_OPERATOR_ONLY';
            broker_connected=$false;broker_actions=0;credentials_changed=$false} | ConvertTo-Json -Compress
        exit 0
    }
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_HASH_REQUIRED'}
    $stage='PROTECTED_METADATA'
    $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
    $profilePath=Join-Path $root 'profile.json'
    foreach($path in @($root,$profilePath,(Join-Path $root 'probe.ps1'))) {
        for($p=$path;$p;$p=Split-Path -Parent $p) {
            $item=Get-Item -LiteralPath $p -Force
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_METADATA'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
        $acl=Get-Acl -LiteralPath $path
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'UNPROTECTED_METADATA'}
        foreach($ace in $acl.Access) {
            if($ace.AccessControlType -ne 'Allow'){continue}
            $sid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            if($sid -notin @('S-1-5-18','S-1-5-32-544') -and ($ace.FileSystemRights -band
                ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                 [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){throw 'WRITABLE_METADATA'}
        }
    }
    $profile=Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    $stage='DEDICATED_IDENTITY'
    $user=Get-LocalUser -Name NexusAIDemoOp
    if(-not $user.Enabled -or $user.SID.Value -cne $profile.service_sid){throw 'IDENTITY_MISMATCH'}
    if(@(Get-LocalGroupMember -SID 'S-1-5-32-544' | Where-Object {$_.SID.Value -ceq $user.SID.Value}).Count){throw 'ADMIN_WORKER_FORBIDDEN'}
    $task=Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    $taskSid=[Security.Principal.NTAccount]::new($task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
    if($taskSid -cne $user.SID.Value -or $task.Principal.RunLevel -ne 'Limited' -or
        $task.Principal.LogonType -ne 'Password' -or @($task.Actions).Count -ne 1 -or $task.State -eq 'Running') {throw 'UNEXPECTED_TASK_IDENTITY_OR_STATE'}
    $exe=Join-Path $env:SYSTEMROOT 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $script=Join-Path $root 'probe.ps1'
    $old='-NoProfile -NonInteractive -File "'+$script+'"'
    $new='-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'+$script+'"'
    if($task.Actions[0].Execute -ine $exe -or $task.Actions[0].Arguments -notin @($old,$new)){throw 'UNEXPECTED_TASK_ACTION'}
    $stage='ROTATE_WINDOWS_PASSWORD'
    $bytes=New-Object byte[] 48
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($bytes)} finally {$rng.Dispose()}
    $password='Nxa!'+[Convert]::ToBase64String($bytes)
    $secure=ConvertTo-SecureString $password -AsPlainText -Force
    try {
        Set-LocalUser -SID $user.SID -Password $secure
        $stage='UPDATE_SAME_LIMITED_TASK'
        $task.Actions=@(New-ScheduledTaskAction -Execute $exe -Argument $new)
        [void](Set-ScheduledTask -InputObject $task -User $task.Principal.UserId -Password $password)
    } finally {$password=$null;$secure.Dispose();[Array]::Clear($bytes,0,$bytes.Length)}
    $stage='VERIFY_TASK'
    $updated=Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    if($updated.Principal.UserId -cne $task.Principal.UserId -or $updated.Principal.RunLevel -ne 'Limited' -or
        $updated.Principal.LogonType -ne 'Password' -or @($updated.Actions).Count -ne 1 -or
        $updated.Actions[0].Execute -ine $exe -or $updated.Actions[0].Arguments -cne $new){throw 'POST_UPDATE_MISMATCH'}
    $stage='START_METADATA_PROBE'
    Start-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    [ordered]@{status='WINDOWS_CREDENTIAL_REPAIRED_NOT_QUALIFIED';broker_connected=$false;broker_actions=0;
        trading_authorized=$false} | ConvertTo-Json -Compress
    exit 0
} catch {
    [ordered]@{status='REPAIR_BLOCKED_OR_PARTIAL';stage=$stage;broker_connected=$false;broker_actions=0;
        trading_authorized=$false} | ConvertTo-Json -Compress
    exit 2
}
