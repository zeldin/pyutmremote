import enum

from .cod import Codable
from .data import UUID


class QEMUDriveImageType(enum.StrEnum):
    none = "None"
    disk = "Disk"
    cd = "CD"
    bios = "BIOS"
    linuxKernel = "LinuxKernel"
    linuxInitrd = "LinuxInitrd"
    linuxDtb = "LinuxDTB"


class QEMUDriveInterface(enum.StrEnum):
    none = "None"
    ide = "IDE"
    scsi = "SCSI"
    sd = "SD"
    mtd = "MTD"
    floppy = "Floppy"
    pflash = "PFlash"
    virtio = "VirtIO"
    nvme = "NVMe"
    usb = "USB"


class QEMUFileShareMode(enum.StrEnum):
    none = "None"
    webdav = "WebDAV"
    virtfs = "VirtFS"


class QEMUNetworkMode(enum.StrEnum):
    emulated = "Emulated"
    shared = "Shared"
    host = "Host"
    bridged = "Bridged"


class QEMUNetworkProtocol(enum.StrEnum):
    tcp = "TCP"
    udp = "UDP"


class QEMUScaler(enum.StrEnum):
    linear = "Linear"
    nearest = "Nearest"


class QEMUSerialMode(enum.StrEnum):
    builtin = "Terminal"
    tcpClient = "TcpClient"
    tcpServer = "TcpServer"
    ptty = "Ptty"


class QEMUSerialTarget(enum.StrEnum):
    autoDevice = "Auto"
    manualDevice = "Manual"
    gdb = "GDB"
    monitor = "Monitor"


class QEMUUSBBus(enum.StrEnum):
    disabled = "Disabled"
    usb2_0 = "2.0"
    usb3_0 = "3.0"


class UTMBackend(enum.StrEnum):
    unknown = "Unknown"
    apple = "Apple"
    qemu = "QEMU"


class UTMConfigurationInfo(Codable):
    Name: str
    Icon: str
    IconCustom: bool
    Notes: str
    UUID: UUID


class UTMConfigurationTerminal(Codable):
    Theme: str
    ForegroundColor: str
    BackgroundColor: str
    Font: str
    FontSize: int
    ResizeCommand: str
    CursorBlink: bool


class UTMQemuConfigurationDisplay(Codable):
    Hardware: str
    VgaRamMib: int
    DynamicResolution: bool
    UpscalingFilter: QEMUScaler
    DownscalingFilter: QEMUScaler
    NativeResolution: bool


class UTMQemuConfigurationDrive(Codable):
    ImageName: str
    ImageType: QEMUDriveImageType
    Interface: QEMUDriveInterface
    InterfaceVersion: int
    Identifier: str
    ReadOnly: bool


class UTMQemuConfigurationInput(Codable):
    UsbBusSupport: QEMUUSBBus
    UsbSharing: bool
    MaximumUsbShare: int


class UTMQemuConfigurationPortForward(Codable):
    Protocol: QEMUNetworkProtocol
    HostAddress: str
    HostPort: int
    GuestAddress: str
    GuestPort: int


class UTMQemuConfigurationNetwork(Codable):
    Mode: QEMUNetworkMode
    Hardware: str
    MacAddress: str
    IsolateFromHost: bool
    PortForward: list[UTMQemuConfigurationPortForward]
    BridgeInterface: str
    VlanGuestAddress: str
    VlanGuestAddressIPv6: str
    VlanHostAddress: str
    VlanHostAddressIPv6: str
    VlanDhcpStartAddress: str
    VlanDhcpEndAddress: str
    VlanDhcpDomain: str
    VlanDnsServerAddress: str
    VlanDnsServerAddressIPv6: str
    VlanDnsSearchDomain: str
    HostNetUuid: str


class UTMQemuConfigurationQEMU(Codable):
    DebugLog: bool
    UEFIBoot: bool
    RNGDevice: bool
    BalloonDevice: bool
    TPMDevice: bool
    Hypervisor: bool
    TSO: bool
    RTCLocalTime: bool
    PS2Controller: bool
    MachinePropertyOverride: str
    AdditionalArguments: list[str]


class UTMQemuConfigurationSerial(Codable):
    Mode: QEMUSerialMode
    Target: QEMUSerialTarget
    Terminal: UTMConfigurationTerminal
    Hardware: str
    TcpHostAddress: str
    TcpPort: int
    WaitForConnection: bool
    RemoteConnectionAllowed: bool


class UTMQemuConfigurationSharing(Codable):
    DirectoryShareMode: QEMUFileShareMode
    DirectoryShareReadOnly: bool
    ClipboardSharing: bool


class UTMQemuConfigurationSound(Codable):
    Hardware: str


class UTMQemuConfigurationSystem(Codable):
    Architecture: str
    Target: str
    CPU: str
    CPUFlagsAdd: list[str]
    CPUFlagsRemove: list[str]
    CPUCount: int
    ForceMulticore: bool
    MemorySize: int
    JITCacheSize: int


class UTMQemuConfiguration(Codable):
    Information: UTMConfigurationInfo
    System: UTMQemuConfigurationSystem
    QEMU: UTMQemuConfigurationQEMU
    Input: UTMQemuConfigurationInput
    Sharing: UTMQemuConfigurationSharing
    Display: list[UTMQemuConfigurationDisplay]
    Drive: list[UTMQemuConfigurationDrive]
    Network: list[UTMQemuConfigurationNetwork]
    Serial: list[UTMQemuConfigurationSerial]
    Sound: list[UTMQemuConfigurationSound]
    Backend: UTMBackend
    ConfigurationVersion: int
