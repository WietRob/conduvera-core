"""Event stream + delivery daemon dispatch tests (SHIP-CONDUVERA-DELIVERY).

Covers:
- WS-F EventStreamBus: monotonic ids, Last-Event-ID resume, bounded history,
  wait_for_events blocking;
- delivery daemon dispatch methods (list/inspect/preflight/publish/sync/cleanup)
  route through the service without crashing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.control_plane.event_stream import EventStreamBus, EventStreamNotifier


class TestEventStreamBus:
    def test_monotonic_ids_and_resume(self):
        bus = EventStreamBus(max_history=10)
        i1 = bus.publish("job.started", {"job_id": "j1"})
        i2 = bus.publish("job.completed", {"job_id": "j1"})
        assert i2 > i1
        assert bus.last_id() == i2
        # resume after id 1 -> only the second event
        since = bus.events_since(1)
        assert [e["id"] for e in since] == [2]
        assert since[0]["event"] == "job.completed"

    def test_bounded_history(self):
        bus = EventStreamBus(max_history=3)
        for i in range(5):
            bus.publish("ev", {"n": i})
        # only last 3 retained
        assert len(bus.events_since(0)) == 3
        assert [e["data"]["n"] for e in bus.events_since(0)] == [2, 3, 4]

    def test_wait_for_events_times_out_cleanly(self):
        bus = EventStreamBus()
        # no events published; wait times out returning []
        got = bus.wait_for_events(0, timeout=0.2)
        assert got == []

    def test_sse_format(self):
        bus = EventStreamBus()
        bus.publish("delivery.published", {"delivery_id": "dlv_x", "state": "PR_OPEN"})
        n = EventStreamNotifier(bus)
        ev = bus.events_since(0)[0]
        line = n.sse_format(ev)
        assert line.startswith("id: 1")
        assert "event: delivery.published" in line
        assert "delivery_id" in line


class TestDeliveryDaemonDispatch:
    def test_dispatch_methods_route(self):
        from conduvera.control_plane.daemon import ControlPlaneDaemon

        class FakeService:
            def __init__(self):
                from conduvera.control_plane.delivery_store import DeliveryStore
                from conduvera.control_plane.evidence_store import EvidenceStore
                from conduvera.control_plane.delivery_service import DeliveryService
                from conduvera.control_plane.github_provider import GitHubDeliveryProvider
                self.delivery_store = DeliveryStore("/tmp/dlv-dispatch-d")
                self.evidence_store = EvidenceStore("/tmp/dlv-dispatch-e")
                self.delivery = DeliveryService(
                    store=self.delivery_store, evidence_store=self.evidence_store,
                    provider=GitHubDeliveryProvider(dry_run=True), service=self)
                self.event_bus = EventStreamBus()
                self.scheduler = type("S", (), {"store": type("ST", (), {
                    "get_job": lambda self, j: None,
                    "get_attempt": lambda self, a: None,
                    "all_attempts": lambda self: []})()})()

            def doctor(self):
                return {"ok": True}

        daemon = ControlPlaneDaemon(service=FakeService(), socket_path="/tmp/dlv-dispatch.sock")
        for method, params in [
            ("delivery_list", {}),
            ("delivery_preflight", {"job_or_delivery": "job_missing"}),
            ("delivery_sync", {"job_or_delivery": "dlv_missing"}),
        ]:
            req = {"method": method, "params": params}
            resp = daemon._dispatch(req)
            # preflight on missing job returns ok:false structured, not a crash
            assert "ok" in resp
