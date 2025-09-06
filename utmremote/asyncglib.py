import asyncio
import gi
import threading
from gi.repository import GLib


class AsyncLoop:

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def submit(self, coro, when_done=None, when_exception=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def call_when_done():
            try:
                res = fut.result()
            except Exception as exc:
                if when_exception is not None:
                    when_exception(exc)
                else:
                    raise
            else:
                if when_done is not None:
                    when_done(res)

        fut.add_done_callback(lambda _: GLib.idle_add(call_when_done))

    @staticmethod
    async def wrap(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        async def success(value):
            fut.set_result(value)

        async def fail(exc):
            fut.set_exception(exc)

        def call_wrapped():
            try:
                asyncio.run_coroutine_threadsafe(
                    success(func(*args, **kwargs)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    fail(exc), loop)

        GLib.idle_add(call_wrapped)
        return await fut
