import asyncio
import hashlib
import ssl

from .swiftconnect import SwiftConnectProtocol, LocalInterface, Peer
from .utmremotemessage import UTMRemoteMessageClient as CM
from .utmremotemessage import UTMRemoteMessageServer as SM


def _fingerprint_der(der):
    hash = hashlib.sha256()
    hash.update(der)
    return hash.digest()


def _fingerprint_pem(pem):
    header, footer = pem.find(ssl.PEM_HEADER), pem.find(ssl.PEM_FOOTER)
    pem = pem[(None if header < 0 else header):
              (None if footer < 0 else footer+len(ssl.PEM_FOOTER))]
    return _fingerprint_der(ssl.PEM_cert_to_DER_cert(pem))


class UTMRemoteClient:

    class Local(LocalInterface):

        def __init__(self, remoteClient):
            self.remoteClient = remoteClient

        async def handle(self, message, data):
            if message == CM.clientHandshake:
                return (await self._handshake(
                    CM.ClientHandshake.Request(data))).encode()
            elif message == CM.listHasChanged:
                return (await self._listHasChanged(
                    CM.ListHasChanged.Request(data))).encode()
            elif message == CM.qemuConfigurationHasChanged:
                return (await self._qemuConfigurationHasChanged(
                    CM.QEMUConfigurationHasChanged.Request(data))).encode()
            elif message == CM.mountedDrivesHasChanged:
                return (await self._mountedDrivesHasChanged(
                    CM.MountedDrivesHasChanged.Request(data))).encode()
            elif message == CM.virtualMachineDidTransition:
                return (await self._virtualMachineDidTransition(
                    CM.VirtualMachineDidTransition.Request(data))).encode()
            elif message == CM.virtualMachineDidError:
                return (await self._virtualMachineDidError(
                    CM.VirtualMachineDidError.Request(data))).encode()
            else:
                raise ValueError(f"Message ID '{message}' is unsupported.")

        async def _handshake(self, req):
            return CM.ClientHandshake.Reply(version=1, capabilities=0)

        async def _listHasChanged(self, req):
            await self.remoteClient.remoteListHasChanged(req.ids)
            return CM.ListHasChanged.Reply()

        async def _qemuConfigurationHasChanged(self, req):
            await self.remoteClient.remoteQemuConfigurationHasChanged(
                req.id, req.configuration)
            return CM.QEMUConfigurationHasChanged.Reply()

        async def _mountedDrivesHasChanged(self, req):
            await self.remoteClient.remoteMountedDrivesHasChanged(
                req.id, req.mountedDrives)
            return CM.MountedDrivesHasChanged.Reply()

        async def _virtualMachineDidTransition(self, req):
            await self.remoteClient.remoteVirtualMachineDidTransition(
                req.id, req.state, req.isTakeoverAllowed)
            return CM.VirtualMachineDidTransition.Reply()

        async def _virtualMachineDidError(self, req):
            await self.remoteClient.remoteVirtualMachineDidError(
                req.id, req.errorMessage)
            return CM.VirtualMachineDidError.Reply()

    class Remote:

        def __init__(self, peer):
            self.peer = peer
            self.capabilities = None

        async def handshake(self, password=None):
            reply = await self._handshake(SM.ServerHandshake.Request(
                version=1, password=password))
            if reply.version != 1:
                raise ValueError("The server interface version does "
                                 "not match the client.")
            self.capabilities = reply.capabilities
            return reply.isAuthenticated, reply.model

        async def listVirtualMachines(self):
            return (await self._listVirtualMachines(
                SM.ListVirtualMachines.Request())).ids

        async def reorderVirtualMachines(self, ids, toOffset):
            await self._reorderVirtualMachines(
                SM.ReorderVirtualMachines.Request(ids=ids, toOffset=toOffset))

        async def getVirtualMachineInformation(self, ids):
            return (await self._getVirtualMachineInformation(
                SM.GetVirtualMachineInformation.Request(ids=ids))).informations

        async def getQEMUConfiguration(self, id):
            return (await self._getQEMUConfiguration(
                SM.GetQEMUConfiguration.Request(id=id))).configuration

        async def getPackageSize(self, id):
            return (await self._getPackageSize(
                SM.GetPackageSize.Request(id=id))).size

        async def getPackageFile(self, id, relativePathComponents,
                                 lastModified=None):
            reply = await self._getPackageFile(
                SM.GetPackageFile.Request(
                    id=id, relativePathComponents=relativePathComponents,
                    lastModified=lastModified))
            return reply.data, reply.lastModified

        async def sendPackageFile(self, id, relativePathComponents,
                                  lastModified, data):
            await self._sendPackageFile(
                SM.SendPackageFile.Request(
                    id=id, relativePathComponents=relativePathComponents,
                    lastModified=lastModified, data=data))

        async def deletePackageFile(self, id, relativePathComponents):
            await self._deletePackageFile(
                SM.DeletePackageFile.Request(
                    id=id, relativePathComponents=relativePathComponents))

        async def mountGuestToolsOnVirtualMachine(self, id):
            await self._mountGuestToolsOnVirtualMachine(
                SM.MountGuestToolsOnVirtualMachine.Request(id=id))

        async def startVirtualMachine(self, id, options=0):
            return (await self._startVirtualMachine(
                SM.StartVirtualMachine.Request(id=id,
                                               options=options))).serverInfo

        async def stopVirtualMachine(self, id, method):
            await self._stopVirtualMachine(
                SM.StopVirtualMachine.Request(id=id, method=method))

        async def restartVirtualMachine(self, id):
            await self._restartVirtualMachine(
                SM.RestartVirtualMachine.Request(id=id))

        async def pauseVirtualMachine(self, id):
            await self._pauseVirtualMachine(
                SM.PauseVirtualMachine.Request(id=id))

        async def resumeVirtualMachine(self, id):
            await self._resumeVirtualMachine(
                SM.ResumeVirtualMachine.Request(id=id))

        async def saveSnapshotVirtualMachine(self, id, name=None):
            await self._saveSnapshotVirtualMachine(
                SM.SaveSnapshotVirtualMachine.Request(id=id, name=name))

        async def deleteSnapshotVirtualMachine(self, id, name=None):
            await self._deleteSnapshotVirtualMachine(
                SM.DeleteSnapshotVirtualMachine.Request(id=id, name=name))

        async def restoreSnapshotVirtualMachine(self, id, name=None):
            await self._restoreSnapshotVirtualMachine(
                SM.RestoreSnapshotVirtualMachine.Request(id=id, name=name))

        async def changePointerTypeVirtualMachine(self, id, tablet):
            await self._changePointerTypeVirtualMachine(
                SM.ChangePointerTypeVirtualMachine.Request(
                            id=id, isTabletMode=tablet))

        async def _handshake(self, parameters):
            return await SM.ServerHandshake.send(parameters, self.peer)

        async def _listVirtualMachines(self, parameters):
            return await SM.ListVirtualMachines.send(parameters, self.peer)

        async def _reorderVirtualMachines(self, parameters):
            return await SM.ReorderVirtualMachines.send(parameters, self.peer)

        async def _getVirtualMachineInformation(self, parameters):
            return await SM.GetVirtualMachineInformation.send(parameters,
                                                              self.peer)

        async def _getQEMUConfiguration(self, parameters):
            return await SM.GetQEMUConfiguration.send(parameters, self.peer)

        async def _getQEMUConfiguration(self, parameters):
            return await SM.GetQEMUConfiguration.send(parameters, self.peer)

        async def _getPackageSize(self, parameters):
            return await SM.GetPackageSize.send(parameters, self.peer)

        async def _getPackageFile(self, parameters):
            return await SM.GetPackageFile.send(parameters, self.peer)

        async def _sendPackageFile(self, parameters):
            return await SM.SendPackageFile.send(parameters, self.peer)

        async def _deletePackageFile(self, parameters):
            return await SM.DeletePackageFile.send(parameters, self.peer)

        async def _mountGuestToolsOnVirtualMachine(self, parameters):
            return await SM.MountGuestToolsOnVirtualMachine.send(
                parameters, self.peer)

        async def _startVirtualMachine(self, parameters):
            return await SM.StartVirtualMachine.send(parameters, self.peer)

        async def _stopVirtualMachine(self, parameters):
            return await SM.StopVirtualMachine.send(parameters, self.peer)

        async def _restartVirtualMachine(self, parameters):
            return await SM.RestartVirtualMachine.send(parameters, self.peer)

        async def _pauseVirtualMachine(self, parameters):
            return await SM.PauseVirtualMachine.send(parameters, self.peer)

        async def _resumeVirtualMachine(self, parameters):
            return await SM.ResumeVirtualMachine.send(parameters, self.peer)

        async def _saveSnapshotVirtualMachine(self, parameters):
            return await SM.SaveSnapshotVirtualMachine.send(
                parameters, self.peer)

        async def _deleteSnapshotVirtualMachine(self, parameters):
            return await SM.DeleteSnapshotVirtualMachine.send(
                parameters, self.peer)

        async def _restoreSnapshotVirtualMachine(self, parameters):
            return await SM.RestoreSnapshotVirtualMachine.send(
                parameters, self.peer)

        async def _changePointerTypeVirtualMachine(self, parameters):
            return await SM.ChangePointerTypeVirtualMachine.send(
                parameters, self.peer)

    @classmethod
    def check_cert_pubkey(cls, cert, expected_pubkey):
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        cert = x509.load_der_x509_certificate(cert)
        expected_pubkey = serialization.load_der_public_key(expected_pubkey)
        if cert.public_key() != expected_pubkey:
            raise ValueError("Certificate has wrong public key")

    @classmethod
    async def get_spice_cert(cls, server, expected_pubkey=None,
                             ssl_context=None):
        loop = asyncio.get_running_loop()
        if isinstance(server, tuple):
            connargs = dict(zip(["host", "port"], server))
        else:
            connargs = {"sock": server}
        if ssl_context is None:
            ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        reader, _ = await asyncio.open_connection(
            ssl=ssl_context, **connargs)
        sslobj = reader._transport.get_extra_info('ssl_object')
        peercert = sslobj.getpeercert(True)
        if expected_pubkey:
            cls.check_cert_pubkey(peercert, expected_pubkey)
        reader._transport.close()
        return ssl.DER_cert_to_PEM_cert(peercert)

    def __init__(self, certificate, ssl_context=None, debug=False):
        self.debug = debug
        self.transport = None
        if ssl_context is None:
            ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        if certificate is not None:
            ssl_context.load_cert_chain(certificate, password='password')
            with open(certificate, "r") as certfile:
                self.client_fingerprint = _fingerprint_pem(certfile.read())
        self.ssl_context = ssl_context

    async def connect(self, server, password=None, expected_fingerprint=None):
        loop = asyncio.get_running_loop()
        if isinstance(server, tuple):
            connargs = dict(zip(["host", "port"], server))
        else:
            connargs = {"sock": server}
        self.peer = Peer(self.Local(self))
        self.transport, protocol = await loop.create_connection(
            lambda: SwiftConnectProtocol(self.peer),
            ssl=self.ssl_context, **connargs)
        ssl = self.transport.get_extra_info('ssl_object')
        self.server_fingerprint = _fingerprint_der(ssl.getpeercert(True))
        if self.debug:
            fp = self.server_fingerprint.hex(':', 1).upper()
            print(f"server fingerprint: {fp}")
        if hasattr(self, 'client_fingerprint'):
            self.connection_fingerprint = bytes(
                s ^ c for s, c in zip(self.server_fingerprint,
                                      self.client_fingerprint))
            if self.debug:
                fp = self.client_fingerprint.hex(':', 1).upper()
                print(f"client fingerprint: {fp}")
            if self.debug or expected_fingerprint is None:
                fp = self.connection_fingerprint.hex(':', 1).upper()
                print(f"connection fingerprint: {fp}")
            if expected_fingerprint is not None:
                if isinstance(expected_fingerprint, str):
                    expected_fingerprint = bytes.fromhex(
                        expected_fingerprint.replace(':', ''))
                if expected_fingerprint != self.connection_fingerprint:
                    raise ConnectionError("Fingerprint mismatch")
        self.remote = self.Remote(self.peer)
        isAuthenticated, device = await self.remote.handshake(password)
        if not isAuthenticated:
            raise ValueError("Password invalid" if password else
                             "Password required")
        self.remote.model = str(device)

    def _cleanup(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._cleanup()

    def __del__(self):
        self._cleanup()

    async def remoteListHasChanged(self, ids):
        if self.debug:
            print(f"remoteListHasChanged(ids)")
        pass

    async def remoteQemuConfigurationHasChanged(self, id, configuration):
        if self.debug:
            print(f"remoteQemuConfigurationHasChanged({id}, "
                  f"{configuration!r})")
        pass

    async def remoteMountedDrivesHasChanged(self, id, mountedDrives):
        if self.debug:
            print(f"remoteMountedDrivesHasChanged({id}, {mountedDrives})")
        pass

    async def remoteVirtualMachineDidTransition(self, id, state,
                                                isTakeoverAllowed):
        if self.debug:
            print(f"remoteVirtualMachineDidTransition({id}, {state!r}, "
                  f"{isTakeoverAllowed})")
        pass

    async def remoteVirtualMachineDidError(self, id, errorMessage):
        if self.debug:
            print(f"remoteVirtualMachineDidError({id}, {errorMessage})")
        pass
