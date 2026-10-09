param([switch]$Grant,[string]$ExpectedScriptHash='',[string]$AuditId='')
# Explicit owner-approved, single-account batch-logon grant. No credential access.
$ErrorActionPreference='Stop'
$stage='AUTHORIZATION'
$changed=$false
function Write-Result($value) {
    $json=$value | ConvertTo-Json -Compress
    Write-Output $json
    if($AuditId) {
        if($AuditId -notmatch '^[a-f0-9]{32}$'){throw 'INVALID_AUDIT_ID'}
        $directory=Join-Path (Split-Path -Parent $PSScriptRoot) 'tmp'
        for($p=$directory;$p;$p=Split-Path -Parent $p) {
            if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_AUDIT_PATH'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
        $stream=[IO.File]::Open((Join-Path $directory ('p3-batch-logon-'+$AuditId+'.json')),
            [IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$bytes=[Text.Encoding]::UTF8.GetBytes($json);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
        finally {$stream.Dispose()}
    }
}
try {
    if(-not $Grant){Write-Result @{status='PLAN_ONLY';rights_changed=$false;broker_actions=0};exit 0}
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'ELEVATION_REQUIRED'}
    if($ExpectedScriptHash -notmatch '^[a-f0-9]{64}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedScriptHash){throw 'REVIEWED_HASH_REQUIRED'}
    $stage='PROTECTED_IDENTITY'
    $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
    $path=Join-Path $root 'profile.json'
    foreach($target in @($root,$path)) {
        for($p=$target;$p;$p=Split-Path -Parent $p) {
            if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LINKED_PROFILE'}
            if((Split-Path -Parent $p) -eq $p){break}
        }
        $acl=Get-Acl -LiteralPath $target
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18'){throw 'UNPROTECTED_PROFILE'}
        foreach($ace in $acl.Access) {
            if($ace.AccessControlType -eq 'Allow' -and
                $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544') -and
                ($ace.FileSystemRights -band ([Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
                    [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))){throw 'WRITABLE_PROFILE'}
        }
    }
    $profile=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $user=Get-LocalUser -Name NexusAIDemoOp
    if(-not $user.Enabled -or $user.SID.Value -cne $profile.service_sid){throw 'IDENTITY_MISMATCH'}
    if((Get-CimInstance Win32_ComputerSystem).PartOfDomain -cne $false){throw 'DOMAIN_POLICY_REQUIRES_SEPARATE_QUALIFICATION'}
    $stage='READ_BATCH_POLICY'
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class NexusAIBatchRights {
    [StructLayout(LayoutKind.Sequential)] struct Obj {
        public uint Length; public IntPtr Root, Name; public uint Attributes;
        public IntPtr Descriptor, Quality;
    }
    [StructLayout(LayoutKind.Sequential)] struct Text {
        public ushort Length, MaximumLength; public IntPtr Buffer;
    }
    [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr system, ref Obj obj, uint access, out IntPtr handle);
    [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr handle);
    [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr buffer);
    [DllImport("advapi32.dll")] static extern uint LsaEnumerateAccountsWithUserRight(IntPtr handle, ref Text right, out IntPtr buffer, out uint count);
    [DllImport("advapi32.dll")] static extern uint LsaAddAccountRights(IntPtr handle, byte[] sid, Text[] rights, uint count);
    [DllImport("netapi32.dll", CharSet=CharSet.Unicode)] static extern uint NetUserGetLocalGroups(string server, string user, uint level, uint flags, out IntPtr buffer, uint size, out uint read, out uint total);
    [DllImport("netapi32.dll")] static extern uint NetApiBufferFree(IntPtr buffer);
    static void Check(uint result) { if(result != 0) throw new InvalidOperationException("NATIVE_POLICY_FAILURE"); }
    static Text Right(string value) {
        return new Text { Length=(ushort)(value.Length*2), MaximumLength=(ushort)((value.Length+1)*2), Buffer=Marshal.StringToHGlobalUni(value) };
    }
    public static string[] Members(string sid) {
        // This helper is intentionally limited to the fixed local operator on a workgroup host.
        var ids=new HashSet<string>(StringComparer.Ordinal) { sid, "S-1-1-0", "S-1-2-0", "S-1-5-3", "S-1-5-11", "S-1-5-113", "S-1-5-15", "S-1-5-64-10" };
        IntPtr buffer=IntPtr.Zero; uint read, total;
        try {
            Check(NetUserGetLocalGroups(null,"NexusAIDemoOp",0,1,out buffer,uint.MaxValue,out read,out total));
            if(read != total) throw new InvalidOperationException("INCOMPLETE_GROUP_EVIDENCE");
            for(int i=0;i<read;i++) {
                string name=Marshal.PtrToStringUni(Marshal.ReadIntPtr(buffer,i*IntPtr.Size));
                ids.Add(((SecurityIdentifier)new NTAccount(name).Translate(typeof(SecurityIdentifier))).Value);
            }
        } finally { if(buffer!=IntPtr.Zero) NetApiBufferFree(buffer); }
        var values=new string[ids.Count];ids.CopyTo(values);return values;
    }
    public static string[] Assigned(string rightName) {
        IntPtr handle=IntPtr.Zero, buffer=IntPtr.Zero; var obj=new Obj { Length=(uint)Marshal.SizeOf(typeof(Obj)) };
        var right=Right(rightName);uint count;
        try {
            Check(LsaOpenPolicy(IntPtr.Zero,ref obj,0x801,out handle));
            uint result=LsaEnumerateAccountsWithUserRight(handle,ref right,out buffer,out count);
            if(result==0x8000001a) return new string[0];
            Check(result);
            var ids=new string[count];
            for(int i=0;i<count;i++) ids[i]=new SecurityIdentifier(Marshal.ReadIntPtr(buffer,i*IntPtr.Size)).Value;
            return ids;
        } finally { if(buffer!=IntPtr.Zero) LsaFreeMemory(buffer);if(handle!=IntPtr.Zero)LsaClose(handle);Marshal.FreeHGlobal(right.Buffer); }
    }
    public static void GrantBatch(string sidValue) {
        IntPtr handle=IntPtr.Zero;var obj=new Obj { Length=(uint)Marshal.SizeOf(typeof(Obj)) };
        var sid=new SecurityIdentifier(sidValue);var bytes=new byte[sid.BinaryLength];sid.GetBinaryForm(bytes,0);
        var right=Right("SeBatchLogonRight");
        try {
            Check(LsaOpenPolicy(IntPtr.Zero,ref obj,0x810,out handle));
            Check(LsaAddAccountRights(handle,bytes,new Text[] {right},1));
        } finally { if(handle!=IntPtr.Zero)LsaClose(handle);Marshal.FreeHGlobal(right.Buffer); }
    }
}
'@
    $members=@([NexusAIBatchRights]::Members($user.SID.Value))
    if($members -contains 'S-1-5-32-544'){throw 'ADMIN_OPERATOR_FORBIDDEN'}
    $denied=@([NexusAIBatchRights]::Assigned('SeDenyBatchLogonRight'))
    if(@($denied | Where-Object {$_ -in $members}).Count){throw 'APPLICABLE_DENY_POLICY'}
    $before=@([NexusAIBatchRights]::Assigned('SeBatchLogonRight'))
    $stage='GRANT_ONLY_DEDICATED_BATCH_RIGHT'
    if($user.SID.Value -notin $before){[NexusAIBatchRights]::GrantBatch($user.SID.Value);$changed=$true}
    $stage='VERIFY_POLICY'
    $after=@([NexusAIBatchRights]::Assigned('SeBatchLogonRight'))
    $deniedAfter=@([NexusAIBatchRights]::Assigned('SeDenyBatchLogonRight'))
    if($user.SID.Value -notin $after -or @($before | Where-Object {$_ -notin $after}).Count -or
        @($after | Where-Object {$_ -notin $before -and $_ -cne $user.SID.Value}).Count -or
        @($deniedAfter | Where-Object {$_ -notin $denied}).Count -or
        @($denied | Where-Object {$_ -notin $deniedAfter}).Count -or
        @($deniedAfter | Where-Object {$_ -in $members}).Count){throw 'POST_POLICY_MISMATCH'}
    Write-Result @{status='BATCH_RIGHT_VERIFIED_NOT_QUALIFIED';rights_changed=$changed;other_accounts_changed=$false;
        deny_policy_changed=$false;worker_admin=$false;broker_connected=$false;broker_actions=0}
    exit 0
} catch {
    Write-Result @{status='BATCH_REPAIR_BLOCKED_OR_PARTIAL';stage=$stage;rights_changed=$changed;
        broker_connected=$false;broker_actions=0}
    exit 2
}
