param([switch]$RepairTaskLaunch,[string]$ExpectedScriptHash='', [string]$AuditId='')
# Elevated provisioning audit. Optional bounded task-policy repair; no broker calls.
$ErrorActionPreference='Stop'
$stage=0
$failure='ELEVATION_REQUIRED'
$taskResults=[ordered]@{attestor=$null;probe=$null}
$taskConditions=[ordered]@{}
$probeLaunch=[ordered]@{requested=$false;instance_returned=$false;state=$null}
$probeEvents=@()
$eventLogStatus='NOT_READ'
$logonFailures=@()
$taskKind='NONE'
$operation='READ'
$probeStarted=$null
$codes=@{
    ELEVATION_REQUIRED=70; REVIEWED_SCRIPT_HASH_REQUIRED=71; PROFILE_UNAVAILABLE=72;
    DEDICATED_IDENTITY_UNAVAILABLE=73; ATTESTOR_TASK_UNAVAILABLE=74; PROBE_TASK_UNAVAILABLE=75;
    TASK_SCRIPT_ACL_UNAVAILABLE=76; UNPROTECTED_TASK_SCRIPT=77; WRITABLE_TASK_SCRIPT=78;
    UNEXPECTED_TASK_ACTION=79; UNEXPECTED_TASK_ARGUMENTS=80;
    UNEXPECTED_PRIVILEGED_PRINCIPAL=81; ELEVATED_WORKER_FORBIDDEN=82;
    TASK_UPDATE_FAILED=83; TASK_START_FAILED=84; PROBE_RECEIPT_UNAVAILABLE=85;
    PROTECTED_ACL_UNAVAILABLE=86; TERMINAL_HASH_UNAVAILABLE=87; PROGRAM_DATA_UNAVAILABLE=88;
    PROBE_NOT_COMPLETED=89; STALE_PROBE_RECEIPT=90
}
function Write-P3Audit($Report) {
    $json=$Report | ConvertTo-Json -Compress -Depth 4
    Write-Output $json
    if($AuditId) {
        if($AuditId -notmatch '^[a-f0-9]{32}$'){throw 'INVALID_DIAGNOSTIC_ID'}
        $directory=Join-Path (Split-Path -Parent $PSScriptRoot) 'tmp'
        for($p=$directory;$p;$p=Split-Path -Parent $p) {
            $item=Get-Item -LiteralPath $p -Force
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_DIAGNOSTIC_PATH'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
        $path=Join-Path $directory ('p3-operator-audit-'+$AuditId+'.json')
        $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$bytes=[Text.Encoding]::UTF8.GetBytes($json);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
        finally {$stream.Dispose()}
    }
}
function Stop-P3Audit([string]$Reason,[int]$NativeCode=0,[int]$HResult=0,[string]$Category='NONE') {
    Write-P3Audit ([ordered]@{status='FAILED';reason=$Reason;native_error_code=$NativeCode;
        hresult=$HResult;error_category=$Category;task=$taskKind;operation=$operation;
        task_last_results=$taskResults;task_conditions=$taskConditions;task_event_log=$eventLogStatus;
        probe_launch=$probeLaunch;probe_events=$probeEvents;operator_logon_failures=$logonFailures;
        broker_connected=$false;broker_actions=0})
    exit $codes[$Reason]
}
function Start-P3ProbeTask {
    $scheduler=New-Object -ComObject 'Schedule.Service'
    $scheduler.Connect()
    $registered=$scheduler.GetFolder('\').GetTask('NexusAI-P3-HostProbe')
    $probeLaunch.requested=$true
    $instance=$registered.Run($null)
    $probeLaunch.instance_returned=($null -ne $instance)
    if($instance){$probeLaunch.state=[int]$instance.State}
}
function Update-P3PasswordTaskAction([string]$Name,[string]$Executable,[string]$Arguments) {
    # /TR changes the command only; no /RU, /RP, credential read or principal change.
    $run='"'+$Executable+'" '+$Arguments
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=Join-Path $env:SYSTEMROOT 'System32/schtasks.exe'
    $info.Arguments='/Change /TN "'+$Name+'" /TR "'+$run.Replace('"','\"')+'"'
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $child=[Diagnostics.Process]::new();$child.StartInfo=$info
    try {
        if(-not $child.Start()){throw 'TASK_ACTION_UPDATE_NOT_STARTED'}
        $child.StandardInput.Close()
        $out=$child.StandardOutput.ReadToEndAsync();$err=$child.StandardError.ReadToEndAsync()
        if(-not $child.WaitForExit(15000)){$child.Kill();$child.WaitForExit();throw 'TASK_ACTION_UPDATE_TIMED_OUT'}
        # Do not log provider output, which can contain deployment/account names.
        $text=$out.GetAwaiter().GetResult()+$err.GetAwaiter().GetResult()
        if($child.ExitCode -ne 0){
            $category='NATIVE_TASK_UPDATE_REJECTED'
            if($text -match 'Invalid argument|Invalid syntax|Invalid option'){$category='NATIVE_ARGUMENT_SYNTAX'}
            elseif($text -match 'password|logon|user name'){$category='CREDENTIAL_OR_LOGON_REQUIREMENT'}
            elseif($text -match 'Access is denied'){$category='ACCESS_DENIED'}
            elseif($text -match 'cannot find|does not exist'){$category='RESOURCE_NOT_FOUND'}
            $error=[InvalidOperationException]::new('TASK_ACTION_UPDATE_REJECTED')
            $error.Data['NativeTaskResult']=$child.ExitCode;$error.Data['SafeCategory']=$category
            $text=$null
            throw $error
        }
        $text=$null
    } finally {$child.Dispose()}
}
try {
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){Stop-P3Audit 'ELEVATION_REQUIRED'}
    $failure='REVIEWED_SCRIPT_HASH_REQUIRED'
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash) {
        Stop-P3Audit 'REVIEWED_SCRIPT_HASH_REQUIRED'
    }
    $failure='PROGRAM_DATA_UNAVAILABLE'
    $programData=[Environment]::GetFolderPath('CommonApplicationData')
    if(-not $programData){Stop-P3Audit 'PROGRAM_DATA_UNAVAILABLE'}
    $root=Join-Path $programData 'NexusAI/Attestor'
    $stage=1
    $failure='PROFILE_UNAVAILABLE'
    $profile=Get-Content -LiteralPath (Join-Path $root 'profile.json') -Raw | ConvertFrom-Json
    $mask=0
    $stage=2
    $failure='DEDICATED_IDENTITY_UNAVAILABLE'
    $user=Get-LocalUser -Name NexusAIDemoOp
    if($user.Enabled -and $user.SID.Value -ceq $profile.service_sid){$mask=$mask -bor 1}
    $failure='ATTESTOR_TASK_UNAVAILABLE'
    $attestor=Get-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor'
    $failure='PROBE_TASK_UNAVAILABLE'
    $probeTask=Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    $taskResults.attestor=(Get-ScheduledTaskInfo -InputObject $attestor).LastTaskResult
    $taskResults.probe=(Get-ScheduledTaskInfo -InputObject $probeTask).LastTaskResult
    foreach($task in @($attestor,$probeTask)) {
        $name=if($task.TaskName -eq 'NexusAI-P3-IsolationAttestor'){'attestor'}else{'probe'}
        $taskConditions[$name]=[ordered]@{state=[string]$task.State;
            enabled=[bool]$task.Settings.Enabled;disallow_battery=[bool]$task.Settings.DisallowStartIfOnBatteries;
            stop_on_battery=[bool]$task.Settings.StopIfGoingOnBatteries;
            run_only_idle=[bool]$task.Settings.RunOnlyIfIdle;network_required=[bool]$task.Settings.RunOnlyIfNetworkAvailable;
            allow_demand_start=[bool]$task.Settings.AllowDemandStart;
            action_remote_signed=(@($task.Actions).Count -eq 1 -and $task.Actions[0].Arguments -match ' -ExecutionPolicy RemoteSigned ')}
    }
    try {
        $xpath="*[EventData[Data[@Name='TaskName']='\NexusAI-P3-HostProbe']]"
        $events=Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' -MaxEvents 10 -FilterXPath $xpath -ErrorAction Stop
        foreach($event in $events) {
            [xml]$xml=$event.ToXml()
            $codesOnly=@()
            foreach($data in $xml.Event.EventData.Data) {
                if($data.Name -in @('ResultCode','ErrorCode')) {
                    $number=0L
                    if([long]::TryParse([string]$data.'#text',[ref]$number)){$codesOnly+=@($number)}
                }
            }
            $probeEvents+=@([ordered]@{event_id=[int]$event.Id;error_codes=$codesOnly})
        }
        $eventLogStatus='READ'
    } catch {$eventLogStatus='UNAVAILABLE_OR_NO_MATCHES'}
    $stage=3
    if($RepairTaskLaunch) {
        $probeStarted=[DateTime]::UtcNow
        $powershell=Join-Path $env:SYSTEMROOT 'System32/WindowsPowerShell/v1.0/powershell.exe'
        foreach($task in @($attestor,$probeTask)) {
            $taskKind=if($task.TaskName -eq 'NexusAI-P3-IsolationAttestor'){'ATTESTOR'}else{'HOST_PROBE'}
            $name=if($task.TaskName -eq 'NexusAI-P3-IsolationAttestor'){'service.ps1'}else{'probe.ps1'}
            $script=Join-Path $root $name
            $failure='TASK_SCRIPT_ACL_UNAVAILABLE'
            $acl=Get-Acl -LiteralPath $script
            if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){Stop-P3Audit 'UNPROTECTED_TASK_SCRIPT'}
            foreach($rule in $acl.Access) {
                if($rule.AccessControlType -eq 'Allow' -and
                    $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544') -and
                    ($rule.FileSystemRights -band ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete))){Stop-P3Audit 'WRITABLE_TASK_SCRIPT'}
            }
            if(@($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ine $powershell){Stop-P3Audit 'UNEXPECTED_TASK_ACTION'}
            $old='-NoProfile -NonInteractive -File "'+$script+'"'
            $new='-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'+$script+'"'
            if($task.Actions[0].Arguments -cne $old -and $task.Actions[0].Arguments -cne $new){Stop-P3Audit 'UNEXPECTED_TASK_ARGUMENTS'}
            if($task -eq $attestor -and $task.Principal.UserId -notin @('SYSTEM','S-1-5-18')){Stop-P3Audit 'UNEXPECTED_PRIVILEGED_PRINCIPAL'}
            if($task -eq $probeTask -and $task.Principal.RunLevel -ne 'Limited'){Stop-P3Audit 'ELEVATED_WORKER_FORBIDDEN'}
            if($task.Actions[0].Arguments -cne $new) {
                $action=New-ScheduledTaskAction -Execute $powershell -Argument $new
                $failure='TASK_UPDATE_FAILED'
                $operation='UPDATE_ACTION'
                if($task.Principal.LogonType -eq 'Password') {
                    Update-P3PasswordTaskAction $task.TaskName $powershell $new
                } else {[void](Set-ScheduledTask -TaskName $task.TaskName -Action $action)}
                $operation='READ_UPDATED_TASK'
                $updated=Get-ScheduledTask -TaskName $task.TaskName
                if($updated.Principal.UserId -cne $task.Principal.UserId -or
                    $updated.Principal.RunLevel -ne $task.Principal.RunLevel -or
                    $updated.Principal.LogonType -ne $task.Principal.LogonType -or
                    @($updated.Actions).Count -ne 1 -or $updated.Actions[0].Execute -ine $powershell -or
                    $updated.Actions[0].Arguments -cne $new){Stop-P3Audit 'UNEXPECTED_TASK_ACTION'}
            }
            $failure='TASK_START_FAILED'
            $operation='START_TASK'
            if($taskKind -eq 'HOST_PROBE'){Start-P3ProbeTask}
            elseif($task.State -ne 'Running'){Start-ScheduledTask -TaskName $task.TaskName}
        }
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        do {
            Start-Sleep -Seconds 1
            $probeTask=Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
            $taskResults.probe=(Get-ScheduledTaskInfo -InputObject $probeTask).LastTaskResult
        } while($probeTask.State -eq 'Running' -and [DateTime]::UtcNow -lt $deadline)
        $attestor=Get-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor'
        try {
            $xpath="*[System[EventID=4625 and TimeCreated[timediff(@SystemTime) <= 120000]] and EventData[Data[@Name='TargetUserName']='NexusAIDemoOp']]"
            foreach($event in @(Get-WinEvent -LogName Security -FilterXPath $xpath -MaxEvents 5 -ErrorAction Stop)) {
                [xml]$xml=$event.ToXml()
                $entry=[ordered]@{}
                foreach($data in $xml.Event.EventData.Data) {
                    if($data.Name -in @('Status','SubStatus','LogonType')) {
                        $value=[string]$data.'#text'
                        if($value -match '^(0x[0-9a-fA-F]+|[0-9]+)$'){$entry[$data.Name]=$value}
                    }
                }
                $logonFailures+=@($entry)
            }
        } catch { }
    }
    if($attestor.Principal.UserId -in @('SYSTEM','S-1-5-18') -and $probeTask.Principal.RunLevel -eq 'Limited'){$mask=$mask -bor 2}
    if($attestor.State -eq 'Running'){$mask=$mask -bor 4}
    $stage=4
    $operation='READ_HOST_RECEIPT'
    $failure='PROBE_RECEIPT_UNAVAILABLE'
    if($probeTask.State -eq 'Running' -or $taskResults.probe -ne 0){Stop-P3Audit 'PROBE_NOT_COMPLETED'}
    $receiptPath=Join-Path $profile.mt5_root 'host-probe.json'
    $written=(Get-Item -LiteralPath $receiptPath).LastWriteTimeUtc
    if($written -lt [DateTime]::UtcNow.AddMinutes(-5) -or ($probeStarted -and $written -lt $probeStarted)) {
        Stop-P3Audit 'STALE_PROBE_RECEIPT'
    }
    $probe=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if($probe.dedicated_identity -ceq $true -and $probe.non_admin -ceq $true -and $probe.session_zero -ceq $true -and
        $probe.broker_connected -ceq $false -and $probe.broker_actions -eq 0){$mask=$mask -bor 8}
    $stage=5
    $failure='PROTECTED_ACL_UNAVAILABLE'
    $protected=$true
    foreach($path in @((Split-Path -Parent $root),$root,(Join-Path $root 'responses'),(Join-Path $root 'profile.json'),(Join-Path $root 'service.ps1'))) {
        $acl=Get-Acl -LiteralPath $path
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){$protected=$false}
        foreach($rule in $acl.Access) {
            if($rule.AccessControlType -ne 'Allow'){continue}
            $sid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            if($sid -in @('S-1-5-18','S-1-5-32-544')){continue}
            if($sid -cne $profile.service_sid -or ($rule.FileSystemRights -band
                ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                 [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){$protected=$false}
        }
    }
    if($protected){$mask=$mask -bor 16}
    $failure='TERMINAL_HASH_UNAVAILABLE'
    if((Get-FileHash -LiteralPath $profile.terminal_exe).Hash -ceq
       (Get-FileHash -LiteralPath 'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe').Hash){$mask=$mask -bor 32}
    Write-P3Audit ([ordered]@{status=$(if($mask -eq 63){'HOST_METADATA_PASS'}else{'FAILED'});
        passed_gate_mask=$mask;expected_gate_mask=63;broker_connected=$false;broker_actions=0;
        trading_authorized=$false;task_last_results=$taskResults;task_conditions=$taskConditions;
        task_event_log=$eventLogStatus;probe_launch=$probeLaunch;probe_events=$probeEvents;
        operator_logon_failures=$logonFailures;operator_files_present=$probe.operator_files_present;
        file_schema_status=$probe.file_schema_status;validation_status=$probe.validation_status;
        validation_exit_code=$probe.validation_exit_code;python_path_accessible=$probe.python_path_accessible})
    if($mask -eq 0){exit 64}
    exit $mask
} catch {
    # Numeric OS diagnostics only. Never serialize error text, arguments or profile.
    $native=0
    if($_.Exception.PSObject.Properties['NativeErrorCode']){$native=[int]$_.Exception.NativeErrorCode}
    if($_.Exception.PSObject.Properties['ErrorData'] -and $_.Exception.ErrorData) {
        $value=$_.Exception.ErrorData.CimInstanceProperties['Error_Code']
        if($value -and $value.Value -is [ValueType]){$native=[int]$value.Value}
    }
    $category='OTHER'
    $message=$_.Exception.Message
    if($message -match 'empty string|cannot be null|is null'){$category='EMPTY_OR_NULL_ARGUMENT'}
    elseif($message -match 'password|logon|user name'){$category='CREDENTIAL_OR_LOGON_REQUIREMENT'}
    elseif($message -match 'Access is denied'){$category='ACCESS_DENIED'}
    elseif($message -match 'not recognized'){$category='COMMAND_UNAVAILABLE'}
    elseif($message -match 'running scripts is disabled|digitally signed'){$category='EXECUTION_POLICY'}
    elseif($message -match 'timed out'){$category='TIMEOUT'}
    elseif($message -match 'cannot find|not found'){$category='RESOURCE_NOT_FOUND'}
    elseif($message -match 'TASK_ACTION_UPDATE_REJECTED'){$category='NATIVE_TASK_UPDATE_REJECTED'}
    $message=$null
    if($_.Exception.Data.Contains('NativeTaskResult')){$native=[int]$_.Exception.Data['NativeTaskResult']}
    if($_.Exception.Data.Contains('SafeCategory')){$category=[string]$_.Exception.Data['SafeCategory']}
    Stop-P3Audit $failure $native $_.Exception.HResult $category
}
