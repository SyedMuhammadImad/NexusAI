param([switch]$Provision,[string]$ExpectedScriptHash='')
# One-time owner-approved infrastructure only. Never launch a terminal or trade.
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$mt5Root=Join-Path $repository 'backend/private/mt5'
$terminalSource='C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'
$pythonExe='C:/Users/LOCAL_USER\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$username='NexusAIDemoOp'
$stage=0

function Assert-Plain([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    for($p=$full;$p;$p=Split-Path -Parent $p) {
        if(Test-Path -LiteralPath $p) {
            $item=Get-Item -LiteralPath $p -Force
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_PROVISION_PATH'}
        }
        if((Split-Path -Parent $p) -eq $p){break}
    }
}

function Set-RestrictedAcl([string]$Path,[string]$Sid,[string]$Rights) {
    Assert-Plain $Path
    $item=Get-Item -LiteralPath $Path -Force
    $acl=if($item.PSIsContainer){[Security.AccessControl.DirectorySecurity]::new()}else{[Security.AccessControl.FileSecurity]::new()}
    $acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-18'))
    foreach($entry in @(@('S-1-5-18','FullControl'),@('S-1-5-32-544','FullControl'),@($Sid,$Rights))) {
        $principal=[Security.Principal.SecurityIdentifier]::new($entry[0])
        if($item.PSIsContainer) {
            $rule=[Security.AccessControl.FileSystemAccessRule]::new($principal,$entry[1],'ContainerInherit,ObjectInherit','None','Allow')
        } else {$rule=[Security.AccessControl.FileSystemAccessRule]::new($principal,$entry[1],'Allow')}
        [void]$acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

try {
    if(-not $Provision) {
        [ordered]@{mode='PLAN_ONLY';creates='dedicated non-admin identity and metadata-only scheduled tasks';
            terminal_launched=$false;broker_connected=$false;broker_actions=0;credentials_printed=$false} | ConvertTo-Json -Compress
        exit 0
    }
    throw 'DEDICATED_WINDOWS_ACCOUNT_PROVISIONING_WITHDRAWN_ADR_021'
    $programData=[Environment]::GetFolderPath('CommonApplicationData')
    if(-not $programData){throw 'PROGRAM_DATA_LOCATION_UNPROVEN'}
    $attestorRoot=Join-Path $programData 'NexusAI/Attestor'
    $attestorParent=Split-Path -Parent $attestorRoot
    $stage=1
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_SCRIPT_HASH_REQUIRED'}
    $stage=2
    # Required only to assign SYSTEM ownership during this one-time elevated setup.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NexusProvisionPrivilege {
 [StructLayout(LayoutKind.Sequential)] struct Luid {public uint Low;public int High;}
 [StructLayout(LayoutKind.Sequential)] struct Privilege {public uint Count;public Luid Id;public uint Attributes;}
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr t);
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LookupPrivilegeValue(string system,string name,out Luid id);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr token,bool disable,ref Privilege p,uint length,IntPtr previous,IntPtr returned);
 public static bool EnableRestore() {
  IntPtr token; if(!OpenProcessToken(GetCurrentProcess(),0x28,out token)) return false;
  try {Luid id;if(!LookupPrivilegeValue(null,"SeRestorePrivilege",out id))return false;
   var p=new Privilege{Count=1,Id=id,Attributes=2};
   return AdjustTokenPrivileges(token,false,ref p,0,IntPtr.Zero,IntPtr.Zero)&&Marshal.GetLastWin32Error()==0;
  }finally{CloseHandle(token);}
 }
}
'@
    if(-not [NexusProvisionPrivilege]::EnableRestore()){throw 'RESTORE_PRIVILEGE_UNAVAILABLE'}
    $stage=3
    foreach($p in @($repository,$mt5Root,$attestorRoot,$terminalSource,$pythonExe)){Assert-Plain $p}
    $stage=4
    if(Get-LocalUser -Name $username -ErrorAction SilentlyContinue){throw 'DEDICATED_IDENTITY_ALREADY_EXISTS_REVIEW_REQUIRED'}
    if(Test-Path -LiteralPath $attestorParent){throw 'ATTESTOR_PARENT_ALREADY_EXISTS_REVIEW_REQUIRED'}
    foreach($task in @('NexusAI-P3-IsolationAttestor','NexusAI-P3-HostProbe')) {
        if(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue){throw 'TASK_ALREADY_EXISTS_REVIEW_REQUIRED'}
    }
    $signature=Get-AuthenticodeSignature -LiteralPath $terminalSource
    $stage=5
    if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'MetaQuotes'){throw 'TERMINAL_SIGNATURE_UNPROVEN'}
    $configuration=Join-Path $mt5Root 'p3-operator.json'
    $stage=6
    Assert-Plain $configuration
    $file=Get-Item -LiteralPath $configuration
    if($file.Length -gt 65536){throw 'INVALID_CONFIGURATION'}
    # Sole authorized credential read. Never serialize it to public output.
    $config=Get-Content -LiteralPath $configuration -Raw | ConvertFrom-Json
    if($config.account.mode -cne 'DEMO' -or $config.account.evidence_source -cne 'MT5_DEMO' -or
        $config.policy_version -cne 'P2-DEMO-1.0'){throw 'DEMO_BINDING_REQUIRED'}
    $terminalDirectory=Join-Path $mt5Root 'terminal'
    if(Test-Path -LiteralPath $terminalDirectory){throw 'EXISTING_TERMINAL_REVIEW_REQUIRED'}
    $bytes=New-Object byte[] 48
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($bytes)} finally {$rng.Dispose()}
    $password='Nxa!'+[Convert]::ToBase64String($bytes)
    $secure=ConvertTo-SecureString $password -AsPlainText -Force
    $user=New-LocalUser -Name $username -Password $secure -AccountNeverExpires -Description 'NexusAI non-admin demo operator'
    $stage=7
    $sid=$user.SID.Value
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $username
    Set-RestrictedAcl $mt5Root $sid 'Modify'
    # Apply to existing named MT5 files only; do not enumerate unrelated secret stores.
    foreach($name in @('p3-operator.json','p3-risk-basis.json','p3-costs.json')) {
        $p=Join-Path $mt5Root $name
        if(Test-Path -LiteralPath $p){Set-RestrictedAcl $p $sid 'Modify'}
    }
    [void](New-Item -ItemType Directory -Path $terminalDirectory)
    $stage=8
    Copy-Item -LiteralPath $terminalSource -Destination (Join-Path $terminalDirectory 'terminal64.exe')
    Set-RestrictedAcl $terminalDirectory $sid 'Modify'
    $terminalExe=Join-Path $terminalDirectory 'terminal64.exe'
    Set-RestrictedAcl $terminalExe $sid 'ReadAndExecute'
    $terminalHash=(Get-FileHash -LiteralPath $terminalExe -Algorithm SHA256).Hash.ToLowerInvariant()
    if($terminalHash -cne (Get-FileHash -LiteralPath $terminalSource -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'BINARY_COPY_MISMATCH'}
    $verificationRoot=Join-Path $repository '.p3-verification'
    Assert-Plain $verificationRoot
    if(-not (Test-Path -LiteralPath $verificationRoot)){[void](New-Item -ItemType Directory -Path $verificationRoot)}
    Set-RestrictedAcl $verificationRoot $sid 'Modify' # No existing DB opened or recursively modified.
    [void](New-Item -ItemType Directory -Path $attestorParent)
    $stage=9
    Set-RestrictedAcl $attestorParent $sid 'ReadAndExecute'
    [void](New-Item -ItemType Directory -Path $attestorRoot)
    Set-RestrictedAcl $attestorRoot $sid 'ReadAndExecute'
    foreach($name in @('requests','responses')) {
        $p=Join-Path $attestorRoot $name
        [void](New-Item -ItemType Directory -Path $p)
        Set-RestrictedAcl $p $sid $(if($name -eq 'requests'){'Modify'}else{'ReadAndExecute'})
    }
    $account=[ordered]@{account_id=$config.account.account_id;currency=$config.account.currency;
        evidence_source=$config.account.evidence_source;mode=$config.account.mode;server=$config.account.server}
    $sha=[Security.Cryptography.SHA256]::Create()
    try {$digest=$sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($account | ConvertTo-Json -Compress)))} finally {$sha.Dispose()}
    $accountKey=([BitConverter]::ToString($digest)).Replace('-','').ToLowerInvariant()
    $profile=[ordered]@{service_sid=$sid;account_key=$accountKey;terminal_exe=$terminalExe;python_exe=$pythonExe;
        mt5_root=$mt5Root;repository_root=$repository;verification_root=$verificationRoot}
    $profile | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $attestorRoot 'profile.json') -Encoding UTF8
    Set-RestrictedAcl (Join-Path $attestorRoot 'profile.json') $sid 'ReadAndExecute'
    foreach($pair in @(@('p3_system_attestor.ps1','service.ps1'),@('p3_operator_host_probe.ps1','probe.ps1'))) {
        $source=Join-Path $PSScriptRoot $pair[0];$target=Join-Path $attestorRoot $pair[1]
        Assert-Plain $source
        Copy-Item -LiteralPath $source -Destination $target
        if((Get-FileHash -LiteralPath $source).Hash -cne (Get-FileHash -LiteralPath $target).Hash){throw 'SCRIPT_COPY_MISMATCH'}
        Set-RestrictedAcl $target $sid 'ReadAndExecute'
    }
    $config.terminal_exe=$terminalExe;$config.terminal_sha256=$terminalHash;$config.service_sid=$sid
    $config | Add-Member -NotePropertyName host_attestation -NotePropertyValue SYSTEM_FILES -Force
    [IO.File]::WriteAllText($configuration,($config | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Set-RestrictedAcl $configuration $sid 'Modify'
    $powershell=Join-Path $env:SYSTEMROOT 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $stage=10
    $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $action=New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'+(Join-Path $attestorRoot 'service.ps1')+'"')
    $system=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount
    [void](Register-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor' -Action $action -Principal $system -Settings $settings)
    $probe=New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'+(Join-Path $attestorRoot 'probe.ps1')+'"')
    $limited=New-ScheduledTaskPrincipal -UserId ($env:COMPUTERNAME+'\'+$username) -LogonType Password -RunLevel Limited
    $task=New-ScheduledTask -Action $probe -Principal $limited
    [void](Register-ScheduledTask -TaskName 'NexusAI-P3-HostProbe' -InputObject $task -User ($env:COMPUTERNAME+'\'+$username) -Password $password)
    $password=$null;$secure.Dispose();$config=$null
    Start-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor'
    $stage=11
    Start-ScheduledTask -TaskName 'NexusAI-P3-HostProbe'
    [ordered]@{status='PROVISIONED_NOT_QUALIFIED';broker_connected=$false;broker_actions=0;terminal_launched=$false} | ConvertTo-Json -Compress
} catch { [Console]::Error.WriteLine('PROVISIONING_BLOCKED_OR_PARTIAL_REVIEW_REQUIRED');exit (40+$stage) }
