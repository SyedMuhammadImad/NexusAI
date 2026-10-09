"""Removal helper dry-run/static safety checks; no real Windows account operations."""
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_removal_default_is_plan_only():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                             str(ROOT / 'scripts/remove_nexusai_operator_profile.ps1')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report['status'] == 'PLAN_ONLY'
    assert report['account_removed'] is False and report['broker_actions'] == 0


def test_removal_is_bound_to_dedicated_identity_and_checked_absolute_paths():
    source = (ROOT / 'scripts/remove_nexusai_operator_profile.ps1').read_text(encoding='utf-8')
    assert "$name='NexusAIDemoOp'" in source
    assert 'CURRENT_USER_REMOVAL_FORBIDDEN' in source and 'UNEXPECTED_ACCOUNT_IDENTITY' in source
    assert 'UNEXPECTED_PROFILE_PATH' in source and 'PROFILE_STILL_LOADED' in source
    assert 'REMOVAL_OUTSIDE_DEDICATED_BOUNDARY' in source and 'LINKED_INFRASTRUCTURE' in source
    assert 'Remove-CimInstance -InputObject $profile' in source
    assert 'Remove-Item -LiteralPath $absolute -Recurse -Force' in source
    assert 'cmd /c' not in source and 'MetaTrader5' not in source
    assert "Get-Content -LiteralPath $profilePath" in source
    assert 'Get-Content -LiteralPath $mt5Root' not in source


def test_withdrawn_account_provisioning_cannot_run_machine_changes():
    source = (ROOT / 'scripts/provision_p3_operator.ps1').read_text(encoding='utf-8')
    guard = source.index("throw 'DEDICATED_WINDOWS_ACCOUNT_PROVISIONING_WITHDRAWN_ADR_021'")
    assert guard < source.index('New-LocalUser -Name')
    assert guard < source.index('Register-ScheduledTask -TaskName')
