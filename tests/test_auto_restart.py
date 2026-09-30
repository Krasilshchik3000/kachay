import asyncio
from unittest.mock import AsyncMock

from kachay.__main__ import auto_restart


class FakeService:
    def __init__(self) -> None:
        self.active_jobs = 0


def test_auto_restart_waits_for_idle_then_stops_polling():
    dp = AsyncMock()
    service = FakeService()
    service.active_jobs = 1

    async def scenario():
        task = asyncio.create_task(auto_restart(dp, service, after_seconds=0.01, poll=0.01))
        await asyncio.sleep(0.05)
        assert not dp.stop_polling.called, "не должен останавливаться, пока идёт загрузка"
        service.active_jobs = 0
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    dp.stop_polling.assert_awaited_once()
