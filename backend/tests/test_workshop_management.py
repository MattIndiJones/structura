"""Campaign retirement/reset controls use temporary data only, no worker launch."""
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import agent_workshop
from backend.app.api.auth import get_current_user
from backend.app.services.agent_workshop import engine
from backend.app.services.agent_workshop.engine import Manager
from backend.app.services.agent_workshop.lease import CampaignLease
from backend.app.services.agent_workshop.store import CampaignConfig, Store


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    local = Store(tmp_path / 'campaigns')
    manager = Manager()
    monkeypatch.setattr(engine, 'store', local)
    monkeypatch.setattr(agent_workshop, 'store', local)
    monkeypatch.setattr(agent_workshop, 'manager', manager)
    monkeypatch.delenv('STRUCTURA_WORKSHOP_CHILD', raising=False)
    app = FastAPI()
    app.include_router(agent_workshop.router)
    app.include_router(agent_workshop.admin_router)
    identity = SimpleNamespace(id=3, role='user')
    app.dependency_overrides[get_current_user] = lambda: identity
    with TestClient(app) as client:
        yield local, manager, client, identity


def completed(local):
    state = local.create(CampaignConfig(months=1, seed=17, contract_scenario='random'), 3)
    state.update(status='COMPLETED', turns=58, month=1, actions=[{'actor': 'hector', 'status': 'FAILED'}])
    state['actors']['hector'].update(registered=True, deals=[{'id': 53}], relations={'bnp': {'id': 1}})
    local.save(state)
    private = local.path(state['id']) / 'instances' / 'hector'
    private.mkdir(parents=True)
    (private / 'structura.db').write_bytes(b'private test book')
    return state


def test_reset_creates_fresh_accounts_and_preserves_the_entire_previous_run(workshop):
    local, manager, client, _ = workshop
    previous = completed(local)
    manager.key = previous['id']
    manager.published = deepcopy(previous)
    response = client.post(f"/api/agent-workshop/{previous['id']}/reset")
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh['id'] != previous['id'] and fresh['config'] == previous['config']
    assert fresh['status'] == 'DRAFT' and fresh['turns'] == fresh['month'] == 0
    assert fresh['actions'] == fresh['incidents'] == fresh['messages'] == []
    assert fresh['commercial_volume'] == 0 and fresh['controller_active'] is False
    assert all(not a['registered'] and not a['deals'] and not a['relations'] for a in fresh['actors'].values())
    assert not (local.path(fresh['id']) / 'instances').exists()
    assert [s['id'] for s in local.list(3)] == [fresh['id']]
    assert client.get(f"/api/agent-workshop/{previous['id']}").status_code == 404
    backup = next((local.root / '_archive').iterdir())
    assert (backup / 'instances/hector/structura.db').read_bytes() == b'private test book'
    assert (backup / 'campaign.json').read_text(encoding='utf-8')
    assert manager.published is None


def test_delete_only_selected_campaign_and_keep_private_backup(workshop):
    local, manager, client, _ = workshop
    removed = completed(local)
    other = local.create(CampaignConfig(), 3)
    unrelated = local.root.parent / 'structura.db'
    unrelated.write_bytes(b'real data must not be touched')
    manager.key = removed['id']; manager.published = deepcopy(removed)
    response = client.delete(f"/api/agent-workshop/{removed['id']}")
    assert response.status_code == 200 and response.json()['deleted']
    assert [s['id'] for s in local.list(3)] == [other['id']]
    assert client.get(f"/api/agent-workshop/{removed['id']}").status_code == 404
    assert client.delete(f"/api/agent-workshop/{removed['id']}").status_code == 404
    assert unrelated.read_bytes() == b'real data must not be touched'
    assert next((local.root / '_archive').glob('*/instances/hector/structura.db')).read_bytes() == b'private test book'


@pytest.mark.parametrize('action', ['reset', 'delete'])
def test_external_lease_blocks_management_even_when_saved_state_says_completed(workshop, action):
    local, _, client, _ = workshop
    state = completed(local)
    lease = CampaignLease(local.path(state['id']))
    try:
        response = client.post(f"/api/agent-workshop/{state['id']}/reset") if action == 'reset' else client.delete(f"/api/agent-workshop/{state['id']}")
        assert response.status_code == 409
        assert local.load(state['id'])['turns'] == 58
        assert not (local.root / '_archive').exists()
    finally:
        lease.close()


def test_paused_local_controller_cannot_be_reset(workshop):
    local, manager, client, _ = workshop
    state = completed(local)
    manager.key = state['id']; manager.published = deepcopy(state)
    manager.thread = SimpleNamespace(is_alive=lambda: True)
    assert client.post(f"/api/agent-workshop/{state['id']}/reset").status_code == 409
    assert local.path(state['id']).exists()


def test_owner_and_child_boundaries_for_management(workshop, monkeypatch):
    local, _, client, identity = workshop
    state = completed(local)
    identity.id = 4
    assert client.delete(f"/api/agent-workshop/{state['id']}").status_code == 404
    assert client.post(f"/api/agent-workshop/{state['id']}/reset").status_code == 404
    identity.id = 3; identity.role = 'admin'
    monkeypatch.setenv('STRUCTURA_WORKSHOP_CHILD', '1')
    for prefix in ('/api/agent-workshop', '/api/admin/agent-workshop'):
        assert client.delete(f"{prefix}/{state['id']}").status_code == 403
        assert client.post(f"{prefix}/{state['id']}/reset").status_code == 403
    assert local.path(state['id']).exists()


@pytest.mark.parametrize('failure', [RuntimeError('Worker did not stop'), httpx.ConnectError('Control unavailable')])
def test_failed_worker_shutdown_retains_campaign(workshop, monkeypatch, failure):
    local, _, client, _ = workshop
    state = completed(local)
    def unavailable(*args):
        raise failure
    monkeypatch.setattr(engine.Instances, 'recover', unavailable)
    assert client.delete(f"/api/agent-workshop/{state['id']}").status_code == 409
    assert local.load(state['id'])['turns'] == 58
    assert not (local.root / '_archive').exists()


def test_failed_reset_write_restores_old_campaign(workshop, monkeypatch):
    local, _, client, _ = workshop
    state = completed(local)
    def unavailable(*args):
        raise OSError('Disk unavailable')
    monkeypatch.setattr(local, 'save', unavailable)
    assert client.post(f"/api/agent-workshop/{state['id']}/reset").status_code == 409
    assert [s['id'] for s in local.list(3)] == [state['id']]
    assert (local.path(state['id']) / 'instances/hector/structura.db').read_bytes() == b'private test book'


def test_start_and_management_share_a_cross_process_guard(workshop):
    local, manager, _, _ = workshop
    state = completed(local)
    with local.lifecycle_guard(state['id']):
        with pytest.raises(ValueError, match='autre processus'):
            manager.start(state['id'])
        with pytest.raises(ValueError, match='autre processus'):
            manager.manage(state['id'], 3, 'delete')
    assert local.path(state['id']).exists()


def test_retirement_cannot_return_cached_history_from_another_controller(workshop):
    local, manager, _, _ = workshop
    state = completed(local)
    reader = Manager(); reader.key = state['id']; reader.published = deepcopy(state)
    manager.manage(state['id'], 3, 'delete')
    with pytest.raises(FileNotFoundError):
        reader.snapshot(state['id'])


def test_deleting_an_old_run_does_not_interrupt_another_live_campaign(workshop):
    local, manager, _, _ = workshop
    old = completed(local)
    active = local.create(CampaignConfig(), 3)
    manager.key = active['id']; manager.published = deepcopy(active)
    manager.thread = SimpleNamespace(is_alive=lambda: True)
    manager.manage(old['id'], 3, 'delete')
    assert manager.key == active['id'] and manager.thread.is_alive()
    assert not manager.cancel.is_set() and local.path(active['id']).exists()
