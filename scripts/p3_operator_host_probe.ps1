# Runs ONLY as the new non-admin scheduled operator. No credential or broker reads.
$ErrorActionPreference='Stop'
try {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=[Security.Principal.WindowsPrincipal]::new($identity)
    $profile=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'profile.json') -Raw | ConvertFrom-Json
    $p=Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
    $result=[ordered]@{dedicated_identity=($identity.User.Value -ceq $profile.service_sid);
        non_admin=(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator));
        session_zero=($p.SessionId -eq 0);broker_connected=$false;broker_actions=0;qualification='NOT_PROVEN'}
    $files=[ordered]@{}
    foreach($entry in @(@('configuration','p3-operator.json'),@('risk_basis','p3-risk-basis.json'),@('cost_basis','p3-costs.json'))) {
        $files[$entry[0]]=[bool](Test-Path -LiteralPath (Join-Path $profile.mt5_root $entry[1]) -PathType Leaf)
    }
    $result.operator_files_present=$files
    # Explicit task-authorized offline validation. Only fixed enum results leave the worker.
    $result.validation_status='NOT_RUN'
    $result.validation_exit_code=$null
    $result.python_path_accessible=$false
    try {
        $validator=Join-Path $profile.repository_root 'scripts/validate_p3_operator_files.py'
        $result.python_path_accessible=[bool](Test-Path -LiteralPath $profile.python_exe -PathType Leaf)
        $result.validation_status='RUNTIME_START_FAILED'
        $env:PYTHONPATH=Join-Path $profile.repository_root 'backend/.venv/Lib/site-packages'
        # Do not expose native stderr, validation exceptions or credential field values.
        $output=& $profile.python_exe -S -s -B $validator --operator-files 2>$null
        $result.validation_exit_code=[int]$LASTEXITCODE
        $result.validation_status='REPORT_INVALID'
        $validation=$output | ConvertFrom-Json
        $safe=[ordered]@{}
        foreach($name in @('operator','risk-basis','costs')) {
            $value=[string]$validation.files.$name
            if($value -notin @('PASS','FAIL','MISSING','PLACEHOLDERS')){throw 'INVALID_VALIDATION_REPORT'}
            $safe[$name]=$value
        }
        $result.file_schema_status=$safe
        $result.validation_status='COMPLETED'
    } catch {
        if($result.validation_status -eq 'NOT_RUN'){$result.validation_status='RUNTIME_PATH_UNAVAILABLE'}
        $output=$null;$validation=$null
    }
    $path=Join-Path $profile.mt5_root 'host-probe.json'
    $result | ConvertTo-Json -Compress | Set-Content -LiteralPath $path -Encoding UTF8
} catch {[Console]::Error.WriteLine('OPERATOR_HOST_PROBE_FAILED');exit 2}
