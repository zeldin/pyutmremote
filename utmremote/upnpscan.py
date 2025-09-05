try:
    import avahi
    import dbus
    from dbus.mainloop import glib
    from gi.repository import GObject
except ModuleNotFoundError:
    def _init_dbus():
        return None

    class _ServiceBrowser:
        def __init__(self, bus, service):
            pass
else:
    def _init_dbus():
        glib.threads_init()
        loop = glib.DBusGMainLoop()
        return dbus.SystemBus(mainloop=loop)

    class _ServiceBrowser:

        def __init__(self, bus, service):
            self.bus = bus
            self.server = dbus.Interface(bus.get_object(avahi.DBUS_NAME, '/'),
                                         'org.freedesktop.Avahi.Server')
            self.browser = dbus.Interface(bus.get_object(
                avahi.DBUS_NAME, self.server.ServiceBrowserNew(
                    avahi.IF_UNSPEC, avahi.PROTO_UNSPEC, service,
                    'local', dbus.UInt32(0))),
                                          avahi.DBUS_INTERFACE_SERVICE_BROWSER)
            self.browser.connect_to_signal("ItemNew", self._itemnew_handler)

        def _itemnew_handler(self, interface, protocol, name,
                             service, domain, flags):
            if flags & avahi.LOOKUP_RESULT_LOCAL:
                pass
            else:
                self.server.ResolveService(
                    interface, protocol, name, service, domain,
                    avahi.PROTO_UNSPEC, dbus.UInt32(0),
                    reply_handler=self._service_resolved,
                    error_handler=self._resolve_error)

        def _service_resolved(self, interface, protocol, name, service, domain,
                              host, aprotocol, address, port, txt, flags):
            pass

        def _resolve_error(self, error):
            pass


class ServiceBrowser(GObject.GObject, _ServiceBrowser):

    __gsignals__ = {
        'new_service': (GObject.SIGNAL_RUN_FIRST, None, (str, str, int))
    }

    def __init__(self, bus, service):
        GObject.GObject.__init__(self)
        self.services = set()
        _ServiceBrowser.__init__(self, bus, service)

    def _service_resolved(self, interface, protocol, name, service, domain,
                          host, aprotocol, address, port, txt, flags):
        s = (str(name), str(address), int(port))
        if s not in self.services:
            self.services.add(s)
            self.emit('new_service', *s)

    def get_services(self):
        return sorted(list(self.services))

    def do_new_service(self, name, address, port):
        pass


def get_dbus():
    return _init_dbus()
