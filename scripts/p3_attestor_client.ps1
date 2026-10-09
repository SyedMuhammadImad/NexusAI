# Non-admin fixed file exchange. No credentials or broker calls; no arbitrary paths.
$ErrorActionPreference='Stop'
try {
    $request=[Console]::In.ReadToEnd() | ConvertFrom-Json
    $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    if($identity.User.Value -cne $request.service_sid -or $request.nonce -notmatch '^[a-f0-9]{32}$'){throw 'INVALID_CALLER'}
    $body=[ordered]@{nonce=$request.nonce;account_key=$request.account_key;python_pid=$request.python_pid;run_id=$request.run_id}
    if($request.PSObject.Properties['phase']) {
        if($request.phase -notin @('BOOTSTRAP_PREPARE','BOOTSTRAP_READ')){throw 'INVALID_PHASE'}
        $body.phase=$request.phase
    }
    $path=Join-Path $root ('requests/'+$request.nonce+'.json')
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {$bytes=[Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress));$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
    $response=Join-Path $root ('responses/'+$request.nonce+'.json')
    $started=[DateTimeOffset]::UtcNow
    while(-not (Test-Path -LiteralPath $response)) {
        if(([DateTimeOffset]::UtcNow-$started).TotalSeconds -gt 4){throw 'ATTESTOR_TIMEOUT'}
        Start-Sleep -Milliseconds 50
    }
    foreach($protected in @($root,(Join-Path $root 'responses'),$response,(Join-Path $root 'profile.json'),(Join-Path $root 'service.ps1'))) {
        $item=Get-Item -LiteralPath $protected
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_RECEIPT'}
        $acl=Get-Acl -LiteralPath $protected
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'INVALID_RECEIPT_OWNER'}
        foreach($rule in $acl.Access) {
            if($rule.AccessControlType -ne 'Allow'){continue}
            $sid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            if($sid -in @('S-1-5-18','S-1-5-32-544')){continue}
            if($sid -cne $request.service_sid -or ($rule.FileSystemRights -band
                ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                 [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){throw 'WRITABLE_RECEIPT'}
        }
    }
    if((Get-Item -LiteralPath $response).Length -gt 8192){throw 'OVERSIZED_RECEIPT'}
    $value=Get-Content -LiteralPath $response -Raw
    [Console]::Out.WriteLine($value)
} catch {[Console]::Error.WriteLine('ATTESTOR_RECEIPT_UNAVAILABLE');exit 2}
