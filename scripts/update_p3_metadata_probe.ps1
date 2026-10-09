param([switch]$Deploy,[string]$ExpectedScriptHash='',[string]$ExpectedProbeHash='')
# Deploy only the fixed metadata-only probe, preserving its protected ACL/principal.
$ErrorActionPreference='Stop'
try {
    if(-not $Deploy){Write-Output 'PLAN_ONLY';exit 0}
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or $ExpectedProbeHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_HASH_REQUIRED'}
    $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
    $target=Join-Path $root 'probe.ps1'
    $source=Join-Path $PSScriptRoot 'p3_operator_host_probe.ps1'
    foreach($path in @($source,$target,(Join-Path $root 'profile.json'))) {
        for($p=$path;$p;$p=Split-Path -Parent $p) {
            if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_DEPLOYMENT_PATH'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
    }
    foreach($path in @($root,$target,(Join-Path $root 'profile.json'))) {
        $acl=Get-Acl -LiteralPath $path
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'UNPROTECTED_METADATA'}
        foreach($ace in $acl.Access) {
            if($ace.AccessControlType -eq 'Allow' -and
                $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544') -and
                ($ace.FileSystemRights -band ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){throw 'WRITABLE_METADATA'}
        }
    }
    $profile=Get-Content -LiteralPath (Join-Path $root 'profile.json') -Raw | ConvertFrom-Json
    $user=Get-LocalUser -Name NexusAIDemoOp
    if($user.SID.Value -cne $profile.service_sid){throw 'IDENTITY_MISMATCH'}
    $task=Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    $taskSid=[Security.Principal.NTAccount]::new($task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
    if($task.State -eq 'Running' -or $taskSid -cne $user.SID.Value -or $task.Principal.RunLevel -ne 'Limited' -or
        @($task.Actions).Count -ne 1 -or $task.Actions[0].Arguments -cne ('-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'+$target+'"')){throw 'TASK_BINDING_MISMATCH'}
    $before=(Get-Acl -LiteralPath $target).Sddl
    $bytes=[IO.File]::ReadAllBytes($source)
    $sha=[Security.Cryptography.SHA256]::Create()
    try {$digest=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    if($digest -cne $ExpectedProbeHash){throw 'REVIEWED_PROBE_HASH_REQUIRED'}
    [IO.File]::WriteAllBytes($target,$bytes)
    if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $digest -or
        (Get-Acl -LiteralPath $target).Sddl -cne $before){throw 'POST_DEPLOYMENT_MISMATCH'}
    Write-Output 'METADATA_PROBE_DEPLOYED_NO_BROKER_ACTIONS'
    exit 0
} catch {[Console]::Error.WriteLine('METADATA_PROBE_DEPLOYMENT_BLOCKED');exit 2}
