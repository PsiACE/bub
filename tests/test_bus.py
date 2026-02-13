from __future__ import annotations

from pathlib import Path

import pytest

from bub.bus import MessageBus
from bub.framework import BubFramework


@pytest.mark.asyncio
async def test_handle_bus_once_publishes_outbound(tmp_path: Path) -> None:
    framework = BubFramework(tmp_path)
    framework.load_skills()
    bus = framework.create_bus()
    assert isinstance(bus, MessageBus)

    await bus.publish_inbound({"channel": "stdout", "chat_id": "bus", "sender_id": "u1", "content": "from bus"})

    result = await framework.handle_bus_once(bus, timeout_seconds=0.1)
    outbound = await bus.next_outbound(timeout_seconds=0.1)

    assert result is not None
    assert outbound is not None
    assert "from bus" in str(outbound["content"])
