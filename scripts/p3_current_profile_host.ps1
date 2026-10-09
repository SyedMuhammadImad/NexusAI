# ADR-022 cooperative current-user metadata only. No broker/credential reads.
$ErrorActionPreference='Stop'
$stage='IDENTITY'
try {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=[Security.Principal.WindowsPrincipal]::new($identity)
    $self=Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
    $request=[Console]::In.ReadToEnd()
    if(-not $request) {
        @{sid=$identity.User.Value;session_id=[int]$self.SessionId;
          non_admin=(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))} | ConvertTo-Json -Compress
        exit 0
    }
    $r=$request | ConvertFrom-Json
    if((@($r.PSObject.Properties.Name | Sort-Object) -join ',') -cne
        'actor_sid,phase,protected_paths,python_exe,python_pid,session_id,terminal_exe,terminal_pid'){throw 'INVALID_REQUEST'}
    if($r.phase -notin @('PREPARE','READ','EXECUTION')){throw 'INVALID_PHASE'}
    $stage='WORKER'
    $worker=Get-CimInstance Win32_Process -Filter "ProcessId=$($r.python_pid)"
    $owner=Invoke-CimMethod -InputObject $worker -MethodName GetOwnerSid
    $actor=($identity.User.Value -ceq $r.actor_sid -and $owner.ReturnValue -eq 0 -and
        $owner.Sid -ceq $r.actor_sid -and $worker.ExecutablePath -ieq $r.python_exe -and
        $self.ParentProcessId -eq $worker.ProcessId)
    $session=($worker.SessionId -eq $r.session_id -and $self.SessionId -eq $r.session_id)
    $stage='TERMINALS'
    $terminals=@(Get-CimInstance Win32_Process -Filter "Name='terminal64.exe' OR Name='terminal.exe'")
    $exclusive=($terminals.Count -eq $(if($r.phase -eq 'PREPARE'){0}else{1}))
    $terminalPid=0
    foreach($p in $terminals) {
        $o=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid
        if($o.ReturnValue -ne 0 -or $o.Sid -cne $r.actor_sid -or
            $p.SessionId -ne $r.session_id -or $p.ExecutablePath -ine $r.terminal_exe -or
            $p.ProcessId -ne $r.terminal_pid){$exclusive=$false}
        $terminalPid=[int]$p.ProcessId
    }
    $protected=$true
    foreach($path in $r.protected_paths) {
        $stage='PATH_ANCESTORS'
        for($p=[IO.Path]::GetFullPath($path);$p;$p=Split-Path -Parent $p) {
            if(Test-Path -LiteralPath $p) {
                if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){$protected=$false}
            }
            if((Split-Path -Parent $p) -eq $p){break}
        }
        $stage='ACL_READ'
        $acl=Get-Acl -LiteralPath $path
        $allowed=@($r.actor_sid,'S-1-5-18','S-1-5-32-544')
        $stage='ACL_OWNER'
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $allowed){$protected=$false}
        $stage='ACL_ENTRIES'
        foreach($ace in $acl.Access) {
            if($ace.AccessControlType -eq 'Allow' -and
                $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed){$protected=$false}
        }
    }
    @{version='p3-current-profile-host-v1';current_identity=[bool]$actor;
      session_match=[bool]$session;non_admin=(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator));
      exclusive_terminal=[bool]$exclusive;protected_acl=[bool]$protected;
      terminal_pid=$terminalPid} | ConvertTo-Json -Compress
} catch {[Console]::Error.WriteLine("CURRENT_PROFILE_HOST_${stage}_FAILED");exit 2}
