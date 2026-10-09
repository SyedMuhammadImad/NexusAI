param([switch]$Provision,[string]$ExpectedScriptHash='')
# Fixed, read-only Python runtime outside the owner's home. No credential reads.
$ErrorActionPreference='Stop'
$stage='AUTHORIZATION'
try {
    if(-not $Provision){Write-Output 'PLAN_ONLY';exit 0}
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_HASH_REQUIRED'}
    $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
    $profilePath=Join-Path $root 'profile.json'
    foreach($path in @($root,$profilePath)) {
        $acl=Get-Acl -LiteralPath $path
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'UNPROTECTED_PROFILE'}
        foreach($ace in $acl.Access) {
            if($ace.AccessControlType -eq 'Allow' -and
                $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544') -and
                ($ace.FileSystemRights -band ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){throw 'WRITABLE_PROFILE'}
        }
    }
    $profile=Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    $user=Get-LocalUser -Name NexusAIDemoOp
    if($user.SID.Value -cne $profile.service_sid){throw 'IDENTITY_MISMATCH'}
    if(@(Get-LocalGroupMember -SID 'S-1-5-32-544' | Where-Object {$_.SID.Value -ceq $user.SID.Value}).Count){throw 'ADMIN_WORKER_FORBIDDEN'}
    if((Get-ScheduledTask -TaskName 'NexusAI-P3-HostProbe').State -eq 'Running'){throw 'WORKER_RUNNING'}
    $source='C:/Users/LOCAL_USER\AppData\Local\Python\pythoncore-3.14-64'
    if($profile.python_exe -ine (Join-Path $source 'python.exe')){throw 'UNEXPECTED_SOURCE_RUNTIME'}
    $destination=Join-Path (Split-Path -Parent $root) 'OperatorRuntime'
    if(Test-Path -LiteralPath $destination){throw 'RUNTIME_ALREADY_EXISTS_REVIEW_REQUIRED'}
    foreach($path in @($source,$profilePath,(Split-Path -Parent $destination))) {
        for($p=$path;$p;$p=Split-Path -Parent $p) {
            if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_RUNTIME_PATH'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
    }
    $stage='SOURCE_RUNTIME'
    $signature=Get-AuthenticodeSignature -LiteralPath (Join-Path $source 'python.exe')
    if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation'){throw 'RUNTIME_SIGNATURE_UNPROVEN'}
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NexusRuntimePrivilege {
 [StructLayout(LayoutKind.Sequential)] struct Luid {public uint Low;public int High;}
 [StructLayout(LayoutKind.Sequential)] struct Privilege {public uint Count;public Luid Id;public uint Attributes;}
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr t);
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LookupPrivilegeValue(string system,string name,out Luid id);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr token,bool disable,ref Privilege p,uint length,IntPtr previous,IntPtr returned);
 public static bool EnableRestore() {
  IntPtr token;if(!OpenProcessToken(GetCurrentProcess(),0x28,out token))return false;
  try {Luid id;if(!LookupPrivilegeValue(null,"SeRestorePrivilege",out id))return false;
   var p=new Privilege{Count=1,Id=id,Attributes=2};
   return AdjustTokenPrivileges(token,false,ref p,0,IntPtr.Zero,IntPtr.Zero)&&Marshal.GetLastWin32Error()==0;
  }finally{CloseHandle(token);}
 }
}
'@
    if(-not [NexusRuntimePrivilege]::EnableRestore()){throw 'RESTORE_PRIVILEGE_UNAVAILABLE'}
    [void](New-Item -ItemType Directory -Path $destination)
    $acl=[Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-18'))
    foreach($entry in @(@('S-1-5-18','FullControl'),@('S-1-5-32-544','FullControl'),@($user.SID.Value,'ReadAndExecute'))) {
        $rule=[Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($entry[0]),
            $entry[1],'ContainerInherit,ObjectInherit','None','Allow')
        [void]$acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $destination -AclObject $acl
    $stage='COPY_RUNTIME'
    # Fixed installed runtime only, not the user's profile or credential directories.
    $entries=@('python.exe','python3.dll','python314.dll','vcruntime140.dll','vcruntime140_1.dll','DLLs','Lib')
    foreach($name in $entries) {
        $path=Join-Path $source $name
        if((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_RUNTIME_ENTRY'}
        if((Get-Item -LiteralPath $path).PSIsContainer -and
            @(Get-ChildItem -LiteralPath $path -Recurse -Force | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'LINKED_RUNTIME_ENTRY'}
        Copy-Item -LiteralPath $path -Destination (Join-Path $destination $name) -Recurse
    }
    $exe=Join-Path $destination 'python.exe'
    if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne
        (Get-FileHash -LiteralPath (Join-Path $source 'python.exe') -Algorithm SHA256).Hash){throw 'RUNTIME_COPY_MISMATCH'}
    $stage='UPDATE_PROTECTED_METADATA'
    $before=(Get-Acl -LiteralPath $profilePath).Sddl
    $profile.python_exe=$exe
    [IO.File]::WriteAllText($profilePath,($profile | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
    if((Get-Acl -LiteralPath $profilePath).Sddl -cne $before){throw 'PROFILE_ACL_CHANGED'}
    Stop-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor'
    Start-ScheduledTask -TaskName 'NexusAI-P3-IsolationAttestor'
    Write-Output 'READONLY_RUNTIME_PROVISIONED_NOT_QUALIFIED'
    exit 0
} catch {
    [ordered]@{status='RUNTIME_PROVISIONING_BLOCKED_OR_PARTIAL';stage=$stage;broker_actions=0}|ConvertTo-Json -Compress
    exit 2
}
