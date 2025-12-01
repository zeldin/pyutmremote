import enum

from .cod import Codable
from .swiftconnect import Message, messageId
from .data import UUID
from .utmconfiguration import UTMBackend, UTMQemuConfiguration


class UTMCapabilities(enum.IntFlag):
    hasJitEntitlements = 1 << 0
    hasHypervisorSupport = 1 << 1
    isAarch64 = 1 << 2
    isX86_64 = 1 << 3


class UTMVirtualMachineStartOptions(enum.IntFlag):
    bootDisposibleMode = 1 << 0
    bootRecovery = 1 << 1
    remoteSession = 1 << 2


class UTMVirtualMachineState(enum.IntEnum):
    stopped = 0
    starting = enum.auto()
    started = enum.auto()
    pausing = enum.auto()
    paused = enum.auto()
    resuming = enum.auto()
    saving = enum.auto()
    restoring = enum.auto()
    stopping = enum.auto()


class UTMVirtualMachineStopMethod(enum.IntEnum):
    request = 0
    force = enum.auto()
    kill = enum.auto()


class ServerInformation(Codable):
    spicePortInternal: int
    spicePortExternal: int
    spiceHostExternal: str
    spicePublicKey: bytes
    spicePassword: str


class VirtualMachineInformation(Codable):
    id: UUID
    name: str
    path: str
    isShortcut: bool
    isSuspended: bool
    isTakeoverAllowed: bool
    backend: UTMBackend
    state: UTMVirtualMachineState
    mountedDrives: dict[str, str]


class Date(str):
    pass


class UTMRemoteMessageServer(enum.IntEnum):
    serverHandshake = 0
    listVirtualMachines = enum.auto()
    reorderVirtualMachines = enum.auto()
    getVirtualMachineInformation = enum.auto()
    getQEMUConfiguration = enum.auto()
    getPackageSize = enum.auto()
    getPackageFile = enum.auto()
    sendPackageFile = enum.auto()
    deletePackageFile = enum.auto()
    mountGuestToolsOnVirtualMachine = enum.auto()
    startVirtualMachine = enum.auto()
    stopVirtualMachine = enum.auto()
    restartVirtualMachine = enum.auto()
    pauseVirtualMachine = enum.auto()
    resumeVirtualMachine = enum.auto()
    saveSnapshotVirtualMachine = enum.auto()
    deleteSnapshotVirtualMachine = enum.auto()
    restoreSnapshotVirtualMachine = enum.auto()
    changePointerTypeVirtualMachine = enum.auto()

    @messageId(serverHandshake)
    class ServerHandshake(Message):
        class Request(Codable):
            version: int
            password: str

        class Reply(Codable):
            version: int
            isAuthenticated: bool
            capabilities: UTMCapabilities
            model: str

    @messageId(listVirtualMachines)
    class ListVirtualMachines(Message):
        class Request(Codable):
            pass

        class Reply(Codable):
            ids: list[UUID]

    @messageId(reorderVirtualMachines)
    class ReorderVirtualMachines(Message):
        class Request(Codable):
            ids: list[UUID]
            offset: int

        class Reply(Codable):
            pass

    @messageId(getVirtualMachineInformation)
    class GetVirtualMachineInformation(Message):
        class Request(Codable):
            ids: list[UUID]

        class Reply(Codable):
            informations: list[VirtualMachineInformation]

    @messageId(getQEMUConfiguration)
    class GetQEMUConfiguration(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            configuration: UTMQemuConfiguration

    @messageId(getPackageSize)
    class GetPackageSize(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            size: int

    @messageId(getPackageFile)
    class GetPackageFile(Message):
        class Request(Codable):
            id: UUID
            relativePathComponents: list[str]
            lastModified: Date

        class Reply(Codable):
            data: bytes
            lastModified: Date

    @messageId(sendPackageFile)
    class SendPackageFile(Message):
        class Request(Codable):
            id: UUID
            relativePathComponents: list[str]
            lastModified: Date
            data: bytes

        class Reply(Codable):
            pass

    @messageId(deletePackageFile)
    class DeletePackageFile(Message):
        class Request(Codable):
            id: UUID
            relativePathComponents: list[str]

        class Reply(Codable):
            pass

    @messageId(mountGuestToolsOnVirtualMachine)
    class MountGuestToolsOnVirtualMachine(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            pass

    @messageId(startVirtualMachine)
    class StartVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            options: UTMVirtualMachineStartOptions

        class Reply(Codable):
            serverInfo: ServerInformation

    @messageId(stopVirtualMachine)
    class StopVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            method: UTMVirtualMachineStopMethod

        class Reply(Codable):
            pass

    @messageId(restartVirtualMachine)
    class RestartVirtualMachine(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            pass

    @messageId(pauseVirtualMachine)
    class PauseVirtualMachine(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            pass

    @messageId(resumeVirtualMachine)
    class ResumeVirtualMachine(Message):
        class Request(Codable):
            id: UUID

        class Reply(Codable):
            pass

    @messageId(saveSnapshotVirtualMachine)
    class SaveSnapshotVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            name: str

        class Reply(Codable):
            pass

    @messageId(deleteSnapshotVirtualMachine)
    class DeleteSnapshotVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            name: str

        class Reply(Codable):
            pass

    @messageId(restoreSnapshotVirtualMachine)
    class RestoreSnapshotVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            name: str

        class Reply(Codable):
            pass

    @messageId(changePointerTypeVirtualMachine)
    class ChangePointerTypeVirtualMachine(Message):
        class Request(Codable):
            id: UUID
            isTabletMode: bool

        class Reply(Codable):
            pass


class UTMRemoteMessageClient(enum.IntEnum):
    clientHandshake = 0
    listHasChanged = enum.auto()
    qemuConfigurationHasChanged = enum.auto()
    mountedDrivesHasChanged = enum.auto()
    virtualMachineDidTransition = enum.auto()
    virtualMachineDidError = enum.auto()

    @messageId(clientHandshake)
    class ClientHandshake(Message):
        class Request(Codable):
            version: int

        class Reply(Codable):
            version: int
            capabilities: UTMCapabilities

    @messageId(listHasChanged)
    class ListHasChanged(Message):
        class Request(Codable):
            ids: list[UUID]

        class Reply(Codable):
            pass

    @messageId(qemuConfigurationHasChanged)
    class QEMUConfigurationHasChanged(Message):
        class Request(Codable):
            id: UUID
            configuration: UTMQemuConfiguration

        class Reply(Codable):
            pass

    @messageId(mountedDrivesHasChanged)
    class MountedDrivesHasChanged(Message):
        class Request(Codable):
            id: UUID
            mountedDrives: dict[str, str]

        class Reply(Codable):
            pass

    @messageId(virtualMachineDidTransition)
    class VirtualMachineDidTransition(Message):
        class Request(Codable):
            id: UUID
            state: UTMVirtualMachineState
            isTakeoverAllowed: bool

        class Reply(Codable):
            pass

    @messageId(virtualMachineDidError)
    class VirtualMachineDidError(Message):
        class Request(Codable):
            id: UUID
            errorMessage: str

        class Reply(Codable):
            pass
