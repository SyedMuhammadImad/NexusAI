"""Operator diagnostics use mocked Windows metadata, never private state or MT5."""
import json
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/p3_operator_status.ps1'


def audit_fixture(*, elevated=True, repair=False, change=''):
    source = SCRIPT.read_text(encoding='utf-8')
    principal = "$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())"
    assert source.count(principal) == 1
    source = source.replace(principal, "$principal=[pscustomobject]@{};$principal | Add-Member ScriptMethod IsInRole {" +
                            ('$true' if elevated else '$false') + "}")
    # -Command has no script filename; the hash provider below is synthetic.
    source = source.replace('Get-FileHash -LiteralPath $PSCommandPath', 'Get-FileHash -LiteralPath "fixture-audit.ps1"')
    mocks = r'''
function Get-FileHash { param($LiteralPath,$Algorithm) [pscustomobject]@{Hash=('a'*64)} }
function Get-Content {
 param($LiteralPath,[switch]$Raw)
 if($LiteralPath.EndsWith('profile.json')) { return '{"service_sid":"fixture-sid","mt5_root":"C:/fixture","terminal_exe":"C:/fixture/terminal64.exe"}' }
 if($LiteralPath.EndsWith('host-probe.json')) { return '{"dedicated_identity":true,"non_admin":true,"session_zero":true,"broker_connected":false,"broker_actions":0}' }
 throw 'FIXTURE_REFUSES_UNEXPECTED_READ'
}
function Get-LocalUser { param($Name) [pscustomobject]@{Enabled=$true;SID=[pscustomobject]@{Value='fixture-sid'}} }
function Get-ScheduledTask {
 param($TaskName)
 $name=if($TaskName -eq 'NexusAI-P3-IsolationAttestor'){'service.ps1'}else{'probe.ps1'}
 $root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'NexusAI/Attestor'
 [pscustomobject]@{TaskName=$TaskName;State=$(if($name -eq 'service.ps1'){'Running'}else{'Ready'});
  Principal=[pscustomobject]@{UserId='SYSTEM';RunLevel='Limited';LogonType='ServiceAccount'};
  Actions=@([pscustomobject]@{Execute=(Join-Path $env:SYSTEMROOT 'System32/WindowsPowerShell/v1.0/powershell.exe');
   Arguments=($(if($script:updated -contains $TaskName){'-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "'}else{'-NoProfile -NonInteractive -File "'})+(Join-Path $root $name)+'"')})}
}
function Get-ScheduledTaskInfo { param($InputObject) [pscustomobject]@{LastTaskResult=0} }
function Get-WinEvent { param($LogName,$MaxEvents,$FilterXPath,$ErrorAction) throw 'FIXTURE_NO_EVENTS' }
function Get-Acl {
 param($LiteralPath)
 $value=[pscustomobject]@{Access=@()}
 $value | Add-Member ScriptMethod GetOwner { [Security.Principal.SecurityIdentifier]::new('S-1-5-18') }
 return $value
}
function New-ScheduledTaskAction { param($Execute,$Argument) [pscustomobject]@{Execute=$Execute;Arguments=$Argument} }
function Set-ScheduledTask { param($TaskName,$Action) $script:updated+=@($TaskName) }
function Start-ScheduledTask { param($TaskName) }
function Start-Sleep { param($Seconds) }
function Get-Item { param($LiteralPath) [pscustomobject]@{LastWriteTimeUtc=[DateTime]::UtcNow} }
'''
    source = source.replace("$ErrorActionPreference='Stop'", "$ErrorActionPreference='Stop'\n" + mocks + change, 1)
    # Scrubbed fixture processes do not have ProgramData environment variables.
    source = source.replace("[Environment]::GetFolderPath('CommonApplicationData')", "'C:/fixture-program-data'")
    # The native action-only updater is never invoked by fixture tests.
    source = source.replace('Update-P3PasswordTaskAction $task.TaskName $powershell $new',
                            'Set-ScheduledTask -TaskName $task.TaskName -Action $action')
    # A real COM launch must never run in credential-free fixture tests.
    source = source.replace("if($taskKind -eq 'HOST_PROBE'){Start-P3ProbeTask}",
                            "if($taskKind -eq 'HOST_PROBE'){Start-ScheduledTask -TaskName $task.TaskName}")
    # Invoke only mocked metadata functions; no real tasks, ACLs, profiles or hashes.
    command = '& { ' + source + " } -ExpectedScriptHash ('a'*64)" + (' -RepairTaskLaunch' if repair else '')
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                          capture_output=True, text=True, timeout=20)


def test_non_admin_is_explicit_failure_not_success():
    result = audit_fixture(elevated=False)
    assert result.returncode == 70
    assert json.loads(result.stdout)['reason'] == 'ELEVATION_REQUIRED'
    assert result.stderr == ''


def test_all_mocked_host_gates_are_not_trading_authorization():
    result = audit_fixture(repair=True)
    assert result.returncode == 63
    report = json.loads(result.stdout)
    assert report['status'] == 'HOST_METADATA_PASS'
    assert report['passed_gate_mask'] == 63
    assert report['broker_connected'] is report['trading_authorized'] is False
    assert report['broker_actions'] == 0


@pytest.mark.parametrize('change,code,reason', [
    ("function Get-Content { throw 'fixture-password-must-not-leak' }", 72, 'PROFILE_UNAVAILABLE'),
    ("function Get-LocalUser { throw 'fixture-password-must-not-leak' }", 73, 'DEDICATED_IDENTITY_UNAVAILABLE'),
    ("function Get-ScheduledTask { throw 'fixture-password-must-not-leak' }", 74, 'ATTESTOR_TASK_UNAVAILABLE'),
    ("function Get-ScheduledTask { param($TaskName) if($TaskName -eq 'NexusAI-P3-HostProbe'){throw 'fixture-password-must-not-leak'};[pscustomobject]@{} }", 75, 'PROBE_TASK_UNAVAILABLE'),
    ("function Get-Acl { throw 'fixture-password-must-not-leak' }", 76, 'TASK_SCRIPT_ACL_UNAVAILABLE'),
    ("function Set-ScheduledTask { throw 'fixture-password-must-not-leak' }", 83, 'TASK_UPDATE_FAILED'),
    ("function Start-ScheduledTask { throw 'fixture-password-must-not-leak' }", 84, 'TASK_START_FAILED'),
])
def test_failure_stage_is_exact_and_exception_content_is_never_exposed(change, code, reason):
    result = audit_fixture(repair=True, change=change)
    assert result.returncode == code
    report = json.loads(result.stdout)
    assert report['status'] == 'FAILED' and report['reason'] == reason
    assert report['broker_connected'] is False and report['broker_actions'] == 0
    assert isinstance(report['hresult'], int) and isinstance(report['native_error_code'], int)
    assert 'fixture-password-must-not-leak' not in result.stdout + result.stderr


def test_invalid_task_argument_is_not_silently_replaced():
    source = SCRIPT.read_text(encoding='utf-8')
    assert "Stop-P3Audit 'UNEXPECTED_TASK_ARGUMENTS'" in source
    assert "Stop-P3Audit 'REVIEWED_SCRIPT_HASH_REQUIRED'" in source
    assert 'Set-ExecutionPolicy' not in source
    assert 'p3-operator.json' not in source and 'MetaTrader5' not in source


def test_stale_host_receipt_cannot_make_a_new_probe_pass():
    result = audit_fixture(repair=True, change="function Get-Item { [pscustomobject]@{LastWriteTimeUtc=[DateTime]::UtcNow.AddHours(-1)} }")
    assert result.returncode == 90
    assert json.loads(result.stdout)['reason'] == 'STALE_PROBE_RECEIPT'


def test_failed_probe_cannot_reuse_previous_success_receipt():
    result = audit_fixture(repair=True, change="function Get-ScheduledTaskInfo { [pscustomobject]@{LastTaskResult=2} }")
    assert result.returncode == 89
    assert json.loads(result.stdout)['reason'] == 'PROBE_NOT_COMPLETED'


def test_credential_repair_default_is_plan_only_without_private_or_broker_reads():
    repair = SCRIPT.with_name('repair_p3_operator_credential.ps1')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(repair)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report['status'] == 'PLAN_ONLY'
    assert report['credentials_changed'] is report['broker_connected'] is False
    assert report['broker_actions'] == 0
    source = repair.read_text(encoding='utf-8')
    assert 'p3-operator.json' not in source and 'MetaTrader5' not in source
    assert "-TaskName 'NexusAI-P3-HostProbe'" in source
    assert "RunLevel -ne 'Limited'" in source


def batch_fixture(*, deny=False, domain=False, admin=False):
    source = SCRIPT.with_name('repair_p3_batch_logon.ps1').read_text(encoding='utf-8')
    principal = "$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())"
    source = source.replace(principal, "$principal=[pscustomobject]@{};$principal | Add-Member ScriptMethod IsInRole {$true}")
    source = source.replace('Get-FileHash -LiteralPath $PSCommandPath', 'Get-FileHash -LiteralPath "fixture.ps1"')
    source = source.replace("[Environment]::GetFolderPath('CommonApplicationData')", "'C:/fixture'")
    source = source.replace('[NexusAIBatchRights]::Members($user.SID.Value)', 'Fixture-Members')
    source = source.replace("[NexusAIBatchRights]::Assigned('SeDenyBatchLogonRight')", 'Fixture-Deny')
    source = source.replace("[NexusAIBatchRights]::Assigned('SeBatchLogonRight')", 'Fixture-Allow')
    source = source.replace('[NexusAIBatchRights]::GrantBatch($user.SID.Value)', 'Fixture-Grant $user.SID.Value')
    mocks = r'''
function Add-Type { param($TypeDefinition) }
function Get-FileHash { param($LiteralPath,$Algorithm) [pscustomobject]@{Hash=('a'*64)} }
function Get-Content { param($LiteralPath,[switch]$Raw) '{"service_sid":"fixture-sid"}' }
function Get-LocalUser { param($Name) [pscustomobject]@{Enabled=$true;SID=[pscustomobject]@{Value='fixture-sid'}} }
function Get-Item { param($LiteralPath,[switch]$Force) [pscustomobject]@{Attributes=[IO.FileAttributes]::Normal} }
function Get-Acl {
 param($LiteralPath)
 $value=[pscustomobject]@{Access=@()}
 $value | Add-Member ScriptMethod GetOwner { [Security.Principal.SecurityIdentifier]::new('S-1-5-18') }
 return $value
}
function Fixture-Allow { 'other-fixture-sid';if($script:granted){'fixture-sid'} }
function Fixture-Grant { param($Sid) if($Sid -cne 'fixture-sid'){throw 'WRONG_ACCOUNT'};$script:granted=$true }
'''
    mocks += '\nfunction Get-CimInstance { [pscustomobject]@{PartOfDomain=' + ('$true' if domain else '$false') + '} }'
    mocks += "\nfunction Fixture-Members { 'fixture-sid'" + (";'S-1-5-32-544'" if admin else '') + ' }'
    mocks += '\nfunction Fixture-Deny { ' + ("'fixture-sid'" if deny else '') + ' }'
    source = source.replace("$ErrorActionPreference='Stop'", "$ErrorActionPreference='Stop'\n" + mocks, 1)
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                           '& { ' + source + " } -Grant -ExpectedScriptHash ('a'*64)"],
                          capture_output=True, text=True, timeout=20)


def test_batch_right_grant_is_single_account_and_not_qualification():
    result = batch_fixture()
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['rights_changed'] is True
    assert report['other_accounts_changed'] is report['deny_policy_changed'] is False
    assert report['broker_actions'] == 0 and report['worker_admin'] is False
    assert report['status'] == 'BATCH_RIGHT_VERIFIED_NOT_QUALIFIED'


@pytest.mark.parametrize('setting', ['deny', 'domain', 'admin'])
def test_batch_right_repair_rejects_unsafe_policy_before_change(setting):
    result = batch_fixture(**{setting: True})
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report['rights_changed'] is False and report['broker_actions'] == 0


def test_batch_default_does_not_access_policy_or_credentials():
    path = SCRIPT.with_name('repair_p3_batch_logon.ps1')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert json.loads(result.stdout)['status'] == 'PLAN_ONLY'
    source = path.read_text(encoding='utf-8')
    assert 'LsaRemoveAccountRights' not in source and 'Set-LocalUser' not in source
    assert 'p3-operator.json' not in source and 'MetaTrader5' not in source


def test_batch_native_interop_compiles_without_invoking_native_calls():
    source = SCRIPT.with_name('repair_p3_batch_logon.ps1').read_text(encoding='utf-8')
    native = source.split("Add-Type -TypeDefinition @'", 1)[1].split("'@", 1)[0]
    command = "Add-Type -TypeDefinition @'\n" + native + "'@\nWrite-Output 'COMPILED_ONLY'"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and result.stderr == ''
    assert result.stdout.strip() == 'COMPILED_ONLY'


@pytest.mark.parametrize('name', ['update_p3_metadata_probe.ps1', 'provision_p3_readonly_runtime.ps1'])
def test_operator_provisioning_helpers_are_plan_only_by_default(name):
    path = SCRIPT.with_name(name)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stdout.strip() == 'PLAN_ONLY'
    source = path.read_text(encoding='utf-8')
    assert 'p3-operator.json' not in source and 'MetaTrader5' not in source
    assert 'Set-LocalUser' not in source and 'ExpectedScriptHash' in source


def test_readonly_runtime_native_interop_compiles_without_enabling_privileges():
    source = SCRIPT.with_name('provision_p3_readonly_runtime.ps1').read_text(encoding='utf-8')
    native = source.split("Add-Type -TypeDefinition @'", 1)[1].split("'@", 1)[0]
    command = "Add-Type -TypeDefinition @'\n" + native + "'@\nWrite-Output 'COMPILED_ONLY'"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and result.stderr == ''
    assert result.stdout.strip() == 'COMPILED_ONLY'
