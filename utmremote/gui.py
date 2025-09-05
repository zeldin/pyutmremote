import asyncio
import json
import os
from pathlib import Path
from .asyncglib import AsyncLoop
from .gencert import generate_certificate_async
from .upnpscan import get_dbus, ServiceBrowser
from .utmremoteclient import UTMRemoteClient
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk  # noqa: E402


def _get_user_path(environ, fallback, *sub):
    path = os.environ.get(environ, "")
    if not path.strip():
        path = os.path.expanduser(fallback)
    path = Path(path, "pyutmremote")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path.joinpath(*sub)


def get_user_config_path(*sub):
    return _get_user_path("XDG_CONFIG_HOME", "~/.config", *sub)


def get_user_runtime_path(*sub):
    return _get_user_path("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}", *sub)


class FingerprintDialog(Gtk.Dialog):
    def __init__(self, info, fp, **kw):
        super().__init__(title="Check fingerprint", flags=0, **kw)
        self.add_buttons(
            "Close", Gtk.ResponseType.CLOSE,
            "Trust", Gtk.ResponseType.ACCEPT)
        self.set_default_size(150, 100)
        box = self.get_content_area()
        box.set_spacing(5)
        box.add(Gtk.Label(
            label="This host is not yet trusted.  You should verify that "
            "the fingerprints match what is displayed on the host and then "
            "select Trust to continue." if 'fingerprint' not in info else
            "The fingerprint of this host has changed!  You should verify "
            "that the fingerprints match what is displayed on the host and "
            "then select Trust to continue.", wrap=True, xalign=0.0))
        box.add(Gtk.Separator())
        box.add(Gtk.Label(label="<b>Name</b>", use_markup=True, xalign=0.0))
        box.add(Gtk.Label(label=info['name'], xalign=0.0))
        box.add(Gtk.Label(label="<b>Host</b>", use_markup=True, xalign=0.0))
        box.add(Gtk.Label(label=info['address'], xalign=0.0))
        box.add(Gtk.Label(
            label="<b>Fingerprint</b>", use_markup=True, xalign=0.0))
        box.add(Gtk.Label(label=fp))


class PasswordDialog(Gtk.Dialog):
    def __init__(self, **kw):
        super().__init__(title="Password required", flags=0, **kw)
        self.add_buttons(
            "Close", Gtk.ResponseType.CLOSE,
            "OK", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        box = self.get_content_area()
        self.entry = Gtk.Entry(visibility=False)
        box.add(self.entry)

    def get_password(self):
        return self.entry.get_text()


class StatusBar(Gtk.InfoBar):
    def __init__(self):
        super().__init__()
        self._counter = 0
        self.label = Gtk.Label()
        self.get_content_area().add(self.label)
        self.clear()

    def _set(self, msg, type):
        self.label.set_text(msg)
        self.set_message_type(type)
        self._counter += 1

    def clear(self):
        self._set("", Gtk.MessageType.OTHER)

    def info(self, msg):
        self._set(msg, Gtk.MessageType.OTHER)

    def warning(self, msg):
        self._set(msg, Gtk.MessageType.WARNING)

    def error(self, msg):
        self._set(msg, Gtk.MessageType.ERROR)

    def run_async_task(self, loop, task, message=None, done_cb=None):
        if message:
            self.info(message)
        counter = self._counter

        def when_done(retval):
            if message and counter == self._counter:
                self.clear()
            if done_cb is not None:
                done_cb(retval)

        def when_exception(excep):
            self.error(str(excep))

        loop.submit(task, when_done=when_done, when_exception=when_exception)


class VirtualMachineList(Gtk.TreeView):
    def __init__(self, loop, client, bar):
        super().__init__()
        self.loop = loop
        self.client = client
        self.bar = bar
        self.model = Gtk.ListStore(str, str, str, str)
        self.set_model(self.model)
        for i, title in enumerate(["Name", "Backend", "Status"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i+1)
            self.append_column(column)
        self.bar.run_async_task(self.loop, self._list_vms(),
                                f"Listing virtual machines")

    async def _list_vms(self):
        remote = self.client.remote
        vm_ids = await remote.listVirtualMachines()
        for vminfo in await remote.getVirtualMachineInformation(vm_ids):
            self.model.append([
                vminfo.id, vminfo.name, vminfo.backend, vminfo.state.name])


class ServerWindow(Gtk.Window):
    def __init__(self, loop, client, info):
        super().__init__(title=info['name'])
        self.connect('delete-event', lambda win, event: client.close())

        self.set_default_size(300, 100)
        bar = StatusBar()
        vms = VirtualMachineList(loop, client, bar)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.add(vms)
        vbox.pack_end(bar, False, False, 0)
        self.add(vbox)


class ServerList(Gtk.ListBox):
    class ServerEntry(Gtk.ListBoxRow):
        def __init__(self, discovered, info):
            super().__init__()
            self.discovered = discovered
            self.sortpos = 2 if discovered else 0
            self.name = info['name']
            self.set_selectable(False)
            self.set_action_name('self.open')
            self.set_action_target_value(
                GLib.Variant.new_string(json.dumps(info)))
            self.add(Gtk.Label(label=self.name, xalign=0.0))

    class UpnpSeparatorEntry(Gtk.ListBoxRow):
        sortpos = 1

        def __init__(self):
            super().__init__()
            self.set_selectable(False)
            self.set_activatable(False)
            label = Gtk.Label(xalign=0.0)
            label.set_markup("<b>Discovered</b>")
            self.add(label)

    def __init__(self, loop, browser, bar, cert_path):
        super().__init__()
        self.loop = loop
        self.browser = browser
        self.bar = bar
        self.cert_path = cert_path
        self.separator = None
        self.set_sort_func(self._sort_func)
        self.action_group = Gio.SimpleActionGroup()
        self.new_action = Gio.SimpleAction(name='new')
        self.open_action = Gio.SimpleAction(
            name='open', parameter_type=GLib.VariantType("s"))
        self.new_action.connect('activate', self._action_new)
        self.open_action.connect('activate', self._action_open)
        self.action_group.add_action(self.new_action)
        self.action_group.add_action(self.open_action)
        self.insert_action_group('self', self.action_group)

        browser.connect('new_service', self._new_service)
        for serv in browser.get_services():
            self._new_service(browser, *serv)

    def _add_server(self, discovered, info):
        entry = self.ServerEntry(discovered, info)
        entry.show_all()
        if discovered and self.separator is None:
            self.separator = self.UpnpSeparatorEntry()
            self.separator.show_all()
            self.add(self.separator)
        self.add(entry)

    def _new_service(self, browser, name, address, port):
        self._add_server(True, dict(
            name=name, address=address, port=port))

    def _sort_func(self, row1, row2):
        if row1.sortpos != row2.sortpos:
            return row1.sortpos - row2.sortpos
        return (row1.name > row2.name) - (row1.name < row2.name)

    def _action_new(self, action, _):
        print("Xnew")

    def _action_open(self, action, value):
        info = json.loads(value.get_string())
        self.bar.run_async_task(self.loop, self._open_async(info),
                                f"Opening connection to {info['name']}",
                                self._open_complete)

    def _open_complete(self, msg):
        client, info = msg
        ServerWindow(self.loop, client, info).show_all()

    async def _open_async(self, info):
        client = UTMRemoteClient(self.cert_path)

        async def fingerprint_check(fp):
            fp = fp.hex(':', 1).upper()
            if 'fingerprint' in info and info['fingerprint'] == fp:
                return
            await self.loop.wrap(self._fingerprint_dialog, info, fp)
            info['fingerprint'] = fp

        async def password_query():
            return await self.loop.wrap(self._password_dialog)

        await client.connect((info['address'], info['port']),
                             password=password_query,
                             expected_fingerprint=fingerprint_check)
        return client, info

    def _fingerprint_dialog(self, info, fp):
        dialog = FingerprintDialog(
            info, fp, transient_for=self.get_toplevel())
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            raise ConnectionError("Server not trusted")

    def _password_dialog(self):
        dialog = PasswordDialog(transient_for=self.get_toplevel())
        dialog.show_all()
        response = dialog.run()
        password = dialog.get_password()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            return password


class ServerListWindow(Gtk.Window):
    def __init__(self, loop, browser):
        super().__init__(title="Select a UTM server")
        self.set_default_size(300, 100)

        bar = StatusBar()
        add_icon = Gtk.Image.new_from_icon_name(
            'list-add', Gtk.IconSize.SMALL_TOOLBAR)
        add_button = Gtk.ToolButton(icon_widget=add_icon, label=None)
        add_button.set_action_name('servers.new')
        bar.get_action_area().add(add_button)

        path = get_user_config_path("client.crt")
        if not path.exists():
            bar.run_async_task(loop, generate_certificate_async(path),
                               "Generering client certificate...")

        servers = ServerList(loop, browser, bar, path)
        self.insert_action_group('servers', servers.action_group)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.add(servers)
        vbox.pack_end(bar, False, False, 0)
        self.add(vbox)


def main(argv):
    Gtk.init(argv)
    aioloop = AsyncLoop()
    dbus = get_dbus()
    browser = ServiceBrowser(dbus, "_utm_server._tcp")
    win = ServerListWindow(aioloop, browser)
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    import sys
    main(sys.argv)
