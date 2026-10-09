param([switch]$Remove,[string]$ExpectedScriptHash='',[string]$AuditId='')
# Explicit owner-requested removal. Fixed account only; never reads broker credentials.
$ErrorActionPreference='Stop'
$stage='AUTHORIZATION'
$removed=$false
$profileRemoved=$false
function Report($value) {
    $json=$value | ConvertTo-Json -Compress
    Write-Output $json
    if($AuditId) {
        if($AuditId -notmatch '^[a-f0-9]{32}$'){throw 'INVALID_AUDIT_ID'}
        $directory=Join-Path (Split-Path -Parent $PSScriptRoot) 'tmp'
        Assert-Plain $directory
        $path=Join-Path $directory ('nexusai-profile-removal-'+$AuditId+'.json')
        $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$bytes=[Text.Encoding]::UTF8.GetBytes($json);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
        finally {$stream.Dispose()}
    }
}
function Assert-Plain([string]$Path) {
    for($p=[IO.Path]::GetFullPath($Path);$p;$p=Split-Path -Parent $p) {
        if(Test-Path -LiteralPath $p) {
            if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_REMOVAL_PATH'}
        }
        if((Split-Path -Parent $p) -eq $p){break}
    }
}
try {
    if(-not $Remove){Report @{status='PLAN_ONLY';account_removed=$false;broker_actions=0};exit 0}
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=[Security.Principal.WindowsPrincipal]::new($identity)
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_HASH_REQUIRED'}
    $stage='IDENTIFY_ACCOUNT'
    $name='NexusAIDemoOp'
    $user=Get-LocalUser -Name $name
    $sid=$user.SID.Value
    if($sid -ceq $identity.User.Value){throw 'CURRENT_USER_REMOVAL_FORBIDDEN'}
    $programData=[Environment]::GetFolderPath('CommonApplicationData')
    if(-not $programData){throw 'PROGRAM_DATA_UNAVAILABLE'}
    $root=Join-Path $programData 'NexusAI/Attestor'
    Assert-Plain $root
    $profilePath=Join-Path $root 'profile.json'
    Assert-Plain $profilePath
    if((Get-Acl -LiteralPath $profilePath).GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'UNPROTECTED_METADATA'}
    $metadata=Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    if($metadata.service_sid -cne $sid){throw 'UNEXPECTED_ACCOUNT_IDENTITY'}
    $repository=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    if([IO.Path]::GetFullPath($metadata.repository_root) -ine $repository){throw 'UNEXPECTED_PROJECT_BINDING'}
    $mt5Root=[IO.Path]::GetFullPath((Join-Path $repository 'backend/private/mt5'))
    if([IO.Path]::GetFullPath($metadata.mt5_root) -ine $mt5Root){throw 'UNEXPECTED_PRIVATE_BOUNDARY'}
    $profiles=@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$sid+"'"))
    if($profiles.Count -gt 1){throw 'AMBIGUOUS_WINDOWS_PROFILE'}
    if($profiles.Count -eq 1) {
        $profile=$profiles[0]
        if($profile.Special -ne $false){throw 'SPECIAL_PROFILE_REMOVAL_FORBIDDEN'}
        $absolute=[IO.Path]::GetFullPath($profile.LocalPath).TrimEnd('\')
        $users=[IO.Path]::GetFullPath((Join-Path $env:SystemDrive 'Users')).TrimEnd('\')
        $leaf=Split-Path -Leaf $absolute
        if((Split-Path -Parent $absolute) -ine $users -or
            ($leaf -ine $name -and -not $leaf.StartsWith($name+'.',[StringComparison]::OrdinalIgnoreCase))){throw 'UNEXPECTED_PROFILE_PATH'}
        Assert-Plain $absolute
    }
    $stage='STOP_DEDICATED_TASKS'
    foreach($taskName in @('NexusAI-P3-HostProbe','NexusAI-P3-IsolationAttestor')) {
        $task=Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue
        if(-not $task){continue}
        if($taskName -eq 'NexusAI-P3-HostProbe') {
            $taskSid=[Security.Principal.NTAccount]::new($task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
            if($taskSid -cne $sid){throw 'UNEXPECTED_TASK_IDENTITY'}
        } elseif($task.Principal.UserId -notin @('SYSTEM','S-1-5-18')){throw 'UNEXPECTED_ATTESTOR_IDENTITY'}
        $script=Join-Path $root $(if($taskName -eq 'NexusAI-P3-HostProbe'){'probe.ps1'}else{'service.ps1'})
        if(@($task.Actions).Count -ne 1 -or -not $task.Actions[0].Arguments.EndsWith('-File "'+$script+'"',[StringComparison]::OrdinalIgnoreCase)){throw 'UNEXPECTED_TASK_ACTION'}
        Stop-ScheduledTask -TaskPath '\' -TaskName $taskName
        Unregister-ScheduledTask -TaskPath '\' -TaskName $taskName -Confirm:$false
    }
    Disable-LocalUser -SID $user.SID
    $stage='STOP_DEDICATED_PROCESSES'
    foreach($process in @(Get-CimInstance Win32_Process)) {
        if($process.ProcessId -in @(0,4,$PID)){continue}
        try {$owner=Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid} catch {continue}
        if($owner.ReturnValue -eq 0 -and $owner.Sid -ceq $sid){Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue}
    }
    $stage='REMOVE_WINDOWS_PROFILE'
    $profiles=@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$sid+"'"))
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    while(@($profiles | Where-Object Loaded).Count -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 1
        $profiles=@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$sid+"'"))
    }
    foreach($profile in $profiles) {
        if($profile.Loaded){throw 'PROFILE_STILL_LOADED'}
        Remove-CimInstance -InputObject $profile
        $profileRemoved=$true
    }
    $stage='REMOVE_ACCOUNT'
    Remove-LocalUser -SID $user.SID
    $removed=$true
    $stage='PRESERVE_PROJECT_ACCESS'
    # Restore the owner's access only on exact project boundaries; no secret read.
    $paths=@($mt5Root,(Join-Path $repository '.p3-verification'))
    foreach($file in @('p3-operator.json','p3-risk-basis.json','p3-costs.json')){$paths+=Join-Path $mt5Root $file}
    foreach($path in $paths) {
        if(-not (Test-Path -LiteralPath $path)){continue}
        Assert-Plain $path
        $item=Get-Item -LiteralPath $path
        $acl=Get-Acl -LiteralPath $path
        foreach($ace in @($acl.Access)) {
            if($ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $sid){[void]$acl.RemoveAccessRuleSpecific($ace)}
        }
        $rule=if($item.PSIsContainer){[Security.AccessControl.FileSystemAccessRule]::new($identity.User,'Modify','ContainerInherit,ObjectInherit','None','Allow')}
            else{[Security.AccessControl.FileSystemAccessRule]::new($identity.User,'Modify','Allow')}
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $path -AclObject $acl
    }
    $stage='REMOVE_DEDICATED_INFRASTRUCTURE'
    foreach($target in @($root,(Join-Path (Split-Path -Parent $root) 'OperatorRuntime'))) {
        $absolute=[IO.Path]::GetFullPath($target)
        $allowed=@([IO.Path]::GetFullPath((Join-Path $programData 'NexusAI/Attestor')),
                   [IO.Path]::GetFullPath((Join-Path $programData 'NexusAI/OperatorRuntime')))
        if($absolute -notin $allowed){throw 'REMOVAL_OUTSIDE_DEDICATED_BOUNDARY'}
        if(-not (Test-Path -LiteralPath $absolute)){continue}
        Assert-Plain $absolute
        if(@(Get-ChildItem -LiteralPath $absolute -Recurse -Force | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'LINKED_INFRASTRUCTURE'}
        Remove-Item -LiteralPath $absolute -Recurse -Force
    }
    $stage='VERIFY_REMOVAL'
    if(Get-LocalUser -SID $user.SID -ErrorAction SilentlyContinue){throw 'ACCOUNT_STILL_EXISTS'}
    if(@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$sid+"'")).Count){throw 'PROFILE_STILL_EXISTS'}
    Report @{status='DEDICATED_ACCOUNT_AND_PROFILE_REMOVED';account_removed=$removed;
        windows_profile_removed=$profileRemoved;project_preserved=$true;credentials_read=$false;
        broker_actions=0;trading_enabled=$false}
    exit 0
} catch {
    Report @{status='REMOVAL_BLOCKED_OR_PARTIAL';stage=$stage;account_removed=$removed;
        windows_profile_removed=$profileRemoved;credentials_read=$false;broker_actions=0}
    exit 2
}
