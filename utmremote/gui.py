import asyncio
import json
import os
import urllib.parse
from pathlib import Path
from .asyncglib import AsyncLoop
from .gencert import generate_certificate_async
from .zeroconf import get_dbus, ServiceBrowser
from .utmremoteclient import UTMRemoteClient
from .utmremotemessage import (UTMVirtualMachineState,
                               UTMVirtualMachineStopMethod)
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, GObject, Gtk, Gdk  # noqa: E402


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


class SignalingUTMRemoteClient(UTMRemoteClient, GObject.GObject):
    __gsignals__ = {
        'list_has_changed':
        (GObject.SIGNAL_RUN_FIRST, None, (object,)),
        'qemu_configuration_has_changed':
        (GObject.SIGNAL_RUN_FIRST, None, (str, object)),
        'mounted_drives_has_changed':
        (GObject.SIGNAL_RUN_FIRST, None, (str, object)),
        'virtual_machine_did_transition':
        (GObject.SIGNAL_RUN_FIRST, None, (str, object, bool)),
        'virtual_machine_did_error':
        (GObject.SIGNAL_RUN_FIRST, None, (str, str))
    }

    def __init__(self, *args, **kwargs):
        GObject.GObject.__init__(self)
        UTMRemoteClient.__init__(self, *args, **kwargs)

    signal_connect = GObject.GObject.connect

    async def remoteListHasChanged(self, ids):
        await AsyncLoop.wrap(self.emit, 'list_has_changed', ids)

    async def remoteQemuConfigurationHasChanged(self, id, configuration):
        await AsyncLoop.wrap(self.emit, 'qemu_configuration_has_changed',
                             id, configuration)

    async def remoteMountedDrivesHasChanged(self, id, mountedDrives):
        await AsyncLoop.wrap(self.emit, 'mounted_drives_has_changed',
                             id, mountedDrives)

    async def remoteVirtualMachineDidTransition(self, id, state,
                                                isTakeoverAllowed):
        await AsyncLoop.wrap(self.emit, 'virtual_machine_did_transition',
                             id, state, isTakeoverAllowed)

    async def remoteVirtualMachineDidError(self, id, errorMessage):
        await AsyncLoop.wrap(self.emit, 'virtual_machine_did_error',
                             id, errorMessage)


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
        box.add(Gtk.Label(label=info.get('name', ''), xalign=0.0))
        box.add(Gtk.Label(label="<b>Host</b>", use_markup=True, xalign=0.0))
        box.add(Gtk.Label(label=info.get('address'), xalign=0.0))
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
        self.vms = {}
        self.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    def get_selected(self):
        list_store, treeiter = self.get_selection().get_selected()
        if treeiter is None:
            return None, None, None
        else:
            id, name, state = list_store.get(treeiter, 0, 1, 3)
            return id, name, UTMVirtualMachineState[state]

    def update_list(self, vm_ids=None):
        self.bar.run_async_task(self.loop, self._list_vms(vm_ids),
                                f"Listing virtual machines")

    def vm_did_transition(self, id, state, isTakeoverAllowed):
        if id in self.vms:
            self.model.set_value(self.vms[id], 3, state.name)

    def _update_vminfos(self, vminfos):
        self.model.clear()
        self.vms = dict()
        for vminfo in vminfos:
            self.vms[vminfo.id] = self.model.append([
                vminfo.id, vminfo.name, vminfo.backend, vminfo.state.name])

    async def _list_vms(self, vm_ids=None):
        remote = self.client.remote
        if vm_ids is None:
            vm_ids = await remote.listVirtualMachines()
        await AsyncLoop.wrap(self._update_vminfos,
                             await remote.getVirtualMachineInformation(vm_ids))


class ServerWindow(Gtk.Window):
    def __init__(self, loop, client, info):
        super().__init__(title=info.get('name') or info.get('address'))
        self.server_address = info['address']
        self.connect('delete-event', lambda win, event: client.close())
        client.signal_connect('list_has_changed', self._list_has_changed)
        client.signal_connect('qemu_configuration_has_changed',
                              self._qemu_configuration_has_changed)
        client.signal_connect('mounted_drives_has_changed',
                              self._mounted_drives_has_changed)
        client.signal_connect('virtual_machine_did_transition',
                              self._virtual_machine_did_transition)
        client.signal_connect('virtual_machine_did_error',
                              self._virtual_machine_did_error)

        self.set_default_size(300, 100)
        self.bar = StatusBar()
        self.loop = loop
        self.client = client
        self.vmlist = VirtualMachineList(loop, client, self.bar)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._start_button = Gtk.Button(label="Start")
        self._stop_button = Gtk.Button(label="Stop")
        self._restart_button = Gtk.Button(label="Restart")
        self._pause_button = Gtk.Button(label="Pause")
        self._resume_button = Gtk.Button(label="Resume")
        hbox.pack_start(self._start_button, True, True, 0)
        hbox.pack_start(self._stop_button, True, True, 0)
        hbox.pack_start(self._restart_button, True, True, 0)
        hbox.pack_start(self._pause_button, True, True, 0)
        hbox.pack_start(self._resume_button, True, True, 0)
        self._start_button.connect('clicked', self._start_button_clicked)
        self._stop_button.connect('clicked', self._stop_button_clicked)
        self._restart_button.connect('clicked', self._restart_button_clicked)
        self._pause_button.connect('clicked', self._pause_button_clicked)
        self._resume_button.connect('clicked', self._resume_button_clicked)
        selection = self.vmlist.get_selection()
        selection.connect('changed', self._selection_changed)
        self._selection_changed(selection)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.add(self.vmlist)
        vbox.add(hbox)
        vbox.pack_end(self.bar, False, False, 0)
        self.add(vbox)
        self.vmlist.update_list()

    def _selection_changed(self, selection):
        vm, name, state = self.vmlist.get_selected()
        self._start_button.set_sensitive(state is not None)
        if state == UTMVirtualMachineState.stopped:
            state = None
        self._stop_button.set_sensitive(state is not None)
        self._restart_button.set_sensitive(state is not None)
        self._pause_button.set_sensitive(state is not None)
        self._resume_button.set_sensitive(state is not None)

    def _start_button_clicked(self, button):
        vm, name, _ = self.vmlist.get_selected()
        if vm is not None:
            self.bar.run_async_task(
                self.loop, self.client.remote.startVirtualMachine(vm),
                f"Starting {name}...",
                lambda info: self._start_complete(info, vm))

    def _start_complete(self, info, vm):
        host, port = info.spiceHostExternal, info.spicePortExternal
        if not port:
            host, port = self.server_address, info.spicePortInternal
        if host and port:
            ca_file = get_user_runtime_path(f"{vm}.crt")
            spice_url = urllib.parse.urlunparse((
                'spice', '['+host+']' if ':' in host else host,
                '', '', urllib.parse.urlencode(
                    [('tls-port', port),
                     ('password', info.spicePassword)]), ''))
            self.bar.run_async_task(
                self.loop, self._run_remote_viewer(
                    spice_url, ca_file, (host, port), info.spicePublicKey),
                f"Opening remote viewer...")

    async def _run_remote_viewer(self, spice_url, ca_file, server, pubkey):
        spice_cert = await self.client.get_spice_cert(server, pubkey)
        with open(ca_file, "w") as f:
            f.write(spice_cert)
        await asyncio.create_subprocess_exec(
            "remote-viewer",
            "--spice-host-subject=CN=UTM Remote SPICE Server, O=UTM",
            f"--spice-ca-file={ca_file}", spice_url)

    def _stop_button_clicked(self, button):
        vm, name, _ = self.vmlist.get_selected()
        if vm is not None:
            self.bar.run_async_task(
                self.loop, self.client.remote.stopVirtualMachine(
                    vm, UTMVirtualMachineStopMethod.request),
                f"Stopping {name}...")

    def _restart_button_clicked(self, button):
        vm, name, _ = self.vmlist.get_selected()
        if vm is not None:
            self.bar.run_async_task(
                self.loop, self.client.remote.restartVirtualMachine(vm),
                f"Restarting {name}...")

    def _pause_button_clicked(self, button):
        vm, name, _ = self.vmlist.get_selected()
        if vm is not None:
            self.bar.run_async_task(
                self.loop, self.client.remote.pauseVirtualMachine(vm),
                f"Pausing {name}...")

    def _resume_button_clicked(self, button):
        vm, name, _ = self.vmlist.get_selected()
        if vm is not None:
            self.bar.run_async_task(
                self.loop, self.client.remote.resumeVirtualMachine(vm),
                f"Resuming {name}...")

    def _list_has_changed(self, client, ids):
        self.vmlist.update_list(ids)
        self._selection_changed(self.vmlist.get_selection())

    def _qemu_configuration_has_changed(self, client, id, configuration):
        pass

    def _mounted_drives_has_changed(self, client, id, mountedDrives):
        pass

    def _virtual_machine_did_transition(
            self, client, id, state, isTakeoverAllowed):
        self.vmlist.vm_did_transition(id, state, isTakeoverAllowed)
        self._selection_changed(self.vmlist.get_selection())

    def _virtual_machine_did_error(self, client, id, errorMessage):
        self.bar.error(errorMessage)


class ServerList(Gtk.ListBox):
    class ServerEntry(Gtk.ListBoxRow):
        def __init__(self, discovered, info):
            super().__init__()
            self.discovered = discovered
            self.sortpos = 2 if discovered else 0
            self.set_selectable(False)
            self.set_action_name('self.open')
            self.label = Gtk.Label(xalign=0.0)
            self.update(info)
            self.add(self.label)

        def update(self, info):
            self.name = info.get('name') or info.get('address')
            self.label.set_label(self.name)
            self.set_action_target_value(
                GLib.Variant.new_string(json.dumps(info)))

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
        self.discovered_servers = []
        self._discovered_servers_entries = []
        self._load_saved_servers()
        self.action_group = Gio.SimpleActionGroup()
        self.new_action = Gio.SimpleAction(name='new')
        self.open_action = Gio.SimpleAction(
            name='open', parameter_type=GLib.VariantType("s"))
        self.new_action.connect('activate', self._action_new)
        self.open_action.connect('activate', self._action_open)
        self.action_group.add_action(self.new_action)
        self.action_group.add_action(self.open_action)
        self.insert_action_group('self', self.action_group)
        self.connect('button-press-event', self._button_press)

        browser.connect('new_service', self._new_service)
        for serv in browser.get_services():
            self._new_service(browser, *serv)

    def _button_press(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            row = self.get_row_at_y(event.y)
            if row and row in self._saved_servers_entries:
                self._saved_server_menu(
                    event, self._saved_servers_entries.index(row))

    def _saved_server_menu(self, event, index):
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="Forget")
        item.connect("activate", lambda item: self._forget_saved_server(index))
        menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _forget_saved_server(self, index):
        self.remove(self._saved_servers_entries[index])
        del self.saved_servers[index]
        del self._saved_servers_entries[index]
        for serv in self.browser.get_services():
            self._new_service(self.browser, *serv)
        self._save_saved_servers()

    def _load_saved_servers(self):
        self.saved_servers = []
        self._saved_servers_entries = []
        path = get_user_config_path("servers.json")
        if path.exists():
            try:
                with path.open(encoding='utf-8') as f:
                    self.saved_servers = json.load(f)
            except Exception as exc:
                self.bar.error(str(exc))
        for ss in self.saved_servers:
            self._add_server(False, ss)

    def _save_saved_servers(self):
        path = get_user_config_path("servers.json")
        with path.open('w', encoding='utf-8') as f:
            json.dump(self.saved_servers, f)

    def _update_saved_server(self, info):
        for i, ss in enumerate(self.saved_servers):
            if ss == info:
                return
            elif (ss.get('name') == info.get('name') and
                  ss['address'] == info['address'] and
                  ss['port'] == info['port']):
                entry = self._saved_servers_entries[i]
                self.saved_servers[i] = info
                self._save_saved_servers()
                entry.update(info)
                return
        self.saved_servers.append(info)
        self._add_server(False, info)
        self._save_saved_servers()

    def _add_server(self, discovered, info):
        if discovered:
            for ss in self.saved_servers:
                if ss['address'] == info['address'] and (
                        ss['port'] == info['port']):
                    return
            self.discovered_servers.append(info)
        else:
            for i, ss in enumerate(self.discovered_servers):
                if ss['address'] == info['address'] and (
                        ss['port'] == info['port']):
                    self.remove(self._discovered_servers_entries[i])
                    del self.discovered_servers[i]
                    del self._discovered_servers_entries[i]
                    if len(self.discovered_servers) == 0 and (
                            self.separator is not None):
                        self.remove(self.separator)
                        self.separator = None
                    break
        entry = self.ServerEntry(discovered, info)
        if discovered:
            self._discovered_servers_entries.append(entry)
        else:
            self._saved_servers_entries.append(entry)
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
        label = info.get('name') or info.get('address')
        self.bar.run_async_task(self.loop, self._open_async(info),
                                f"Opening connection to {label}",
                                self._open_complete)

    def _open_complete(self, msg):
        client, info = msg
        self._update_saved_server(info)
        ServerWindow(self.loop, client, info).show_all()

    async def _open_async(self, info):
        client = SignalingUTMRemoteClient(self.cert_path)

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
