# Operator-only read-only collector. Input contains paths/SID, never credentials.
$ErrorActionPreference = 'Stop'
try {
    $inputData = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $identity.User.Value
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
    $dedicated = $sid -ceq $inputData.service_sid
    $sessionZero = $current.SessionId -eq 0
    $nonAdmin = -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $exclusive = $true
    $terminalPids = @()
    foreach ($p in (Get-CimInstance Win32_Process)) {
        if ($p.ProcessId -eq 0) { continue }
        $owner = Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid
        if ($owner.ReturnValue -ne 0) { $exclusive = $false; continue }
        if ($owner.Sid -cne $sid) { continue }
        if ($p.SessionId -ne 0) { $exclusive = $false }
        if ($p.ExecutablePath -ieq $inputData.terminal_exe) {
            $terminalPids += [int]$p.ProcessId
        } elseif ($p.ProcessId -eq $inputData.python_pid -and $p.ExecutablePath -ieq $inputData.python_exe) {
            continue
        } elseif ($p.ProcessId -eq $PID) {
            continue
        } else { $exclusive = $false }
    }
    if ($terminalPids.Count -ne 1) { $exclusive = $false }
    $protected = $true
    $allowed = @($sid, 'S-1-5-18', 'S-1-5-32-544')
    foreach ($path in $inputData.protected_paths) {
        $acl = Get-Acl -LiteralPath $path
        $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($ownerSid -notin $allowed) { $protected = $false }
        foreach ($rule in $acl.Access) {
            $ruleSid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            if ($rule.AccessControlType -eq 'Allow' -and $ruleSid -notin $allowed) { $protected = $false }
        }
    }
    [ordered]@{
        dedicated_identity = [bool]$dedicated
        session_zero = [bool]$sessionZero
        non_admin = [bool]$nonAdmin
        exclusive_processes = [bool]$exclusive
        protected_acl = [bool]$protected
        terminal_pid = $(if ($terminalPids.Count -eq 1) { $terminalPids[0] } else { 0 })
    } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('HOST_METADATA_UNAVAILABLE')
    exit 2
}
