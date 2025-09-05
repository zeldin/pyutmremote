import asyncio
import enum
import struct

from .data import Data


class PeerError(Exception):
    pass


def messageId(id):
    def decorator(cls):
        cls.id = id
        return cls
    return decorator


class Message:
    @classmethod
    async def send(cls, parameters, to_peer):
        return cls.Reply(await to_peer.sendWithReply(
            cls.id, parameters.encode()))


class LocalInterface:

    async def handle(message, data):
        raise Exception("Unhandled message")

    async def handle_error(error):
        raise error


class PeerFlag(int, enum.Flag):
    none = 0
    response = 1 << 0
    error = 1 << 1


class Peer:
    def __init__(self, local, debug=False):
        self.debug = debug
        self.local = local
        self.protocol = None
        self.token = 1
        self.futures = {}

    def enqueue(self):
        token, future = self.token, asyncio.get_running_loop().create_future()
        self.futures[token] = future
        self.token += 1
        return token, future

    def failAll(self, error):
        futures = self.futures
        self.futures = {}
        for token, future in futures.items():
            future.set_exception(error)

    def complete(self, data, token):
        future = self.futures.pop(token, None)
        if future is not None:
            future.set_result(data)

    def fail(self, error, token):
        future = self.futures.pop(token, None)
        if future is not None:
            future.set_exception(error)

    async def serviceReply(self, msg):
        if self.debug:
            print(f"Message received: {msg}")
        data = Data(msg)
        id = data.popFirst()
        flags = PeerFlag(data.popFirst())
        token = data.popUleb128()
        if self.debug:
            print(f"id = {id}, flags = {flags!r}, token = {token}")
        if PeerFlag.response in flags:
            if PeerFlag.error in flags:
                if self.debug:
                    print("error")
                self.fail(PeerError(bytes(data).decode('utf-8')), token)
            else:
                if self.debug:
                    print("response")
                self.complete(data, token)
        else:
            if self.debug:
                print("request")
            try:
                response = await self.local.handle(id, data)
            except Exception as error:
                if self.debug:
                    print(f"exception: {error}")
                await self.sendError(id, error, token)
            else:
                if self.debug:
                    print(f"result: {bytes(response)}")
                await self.send(id, response, token, PeerFlag.response)

    async def send(self, id, data, token, flags=PeerFlag.none):
        if self.debug:
            print(f"send: {bytes(data)}")
        tk = Data()
        tk.pushUleb128(token)
        await self.protocol.send_data(struct.pack('BB', id, flags), tk, data)

    async def sendError(self, id, error, token):
        await self.send(id, str(error).encode('utf-8'), token,
                        PeerFlag.response | PeerFlag.error)

    async def sendWithReply(self, id, data):
        token, future = self.enqueue()
        try:
            await self.send(id, data, token)
        except Exception as error:
            self.fail(error, token)
        return await future

    async def trusted(self):
        await self.protocol.trusted()


class SwiftConnectProtocol(asyncio.Protocol):
    def __init__(self, peer):
        self.valve = asyncio.Event()
        self.transport = None
        self.peer = peer
        peer.protocol = self

    def connection_made(self, transport):
        self.transport = transport
        self.header = None
        self.data = None
        self.transport.pause_reading()
        self.valve.set()

    def data_received(self, data):
        while len(data) > 0:
            if self.header is None:
                self.header = data[:8]
                data = data[8:]
            elif len(self.header) == 8:
                msglen, = struct.unpack('>Q', self.header)
                if self.data is None:
                    self.data = data[:msglen]
                    data = data[msglen:]
                else:
                    self.data = self.data + data[:msglen-len(self.data)]
                    data = data[msglen-len(self.data):]
                if len(self.data) == msglen:
                    msg = self.data
                    self.data = None
                    self.header = None
                    asyncio.create_task(self.peer.serviceReply(msg))
            else:
                self.header = self.header + data[:8-len(self.header)]
                data = data[8-len(self.header):]

    def connection_lost(self, exc):
        self.peer.failAll(exc if exc is not None
                          else PeerError("Connection closed"))
        self.valve.set()

    def pause_writing(self):
        self.valve.clear()

    def resume_writing(self):
        self.valve.set()

    async def send_data(self, *msg):
        msglen = sum(0 if x is None else len(x) for x in msg)
        data = struct.pack('>Q', msglen)
        for x in msg:
            if x is not None:
                data += bytes(x)
        await self.valve.wait()
        self.transport.write(data)

    async def trusted(self):
        self.transport.resume_reading()
