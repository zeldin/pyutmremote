import argparse
import asyncio
import sys
import urllib.parse

from . import (
    UTMRemoteClient, UTMVirtualMachineStopMethod,
    UTMVirtualMachineStartOptions)


async def async_main(argv):
    parser = argparse.ArgumentParser("python -m utmremote.cli",
                                     description="Connect to UTM using "
                                     "remote protocol")
    parser.add_argument('--cert', '-c', required=True,
                        help="client certificate to use (PEM format)")
    parser.add_argument('--server', '-s', required=True,
                        help="hostname of server to connect to")
    parser.add_argument('--port', '-p', default=21589,
                        help="port to connect to")
    parser.add_argument('--password', '-P',
                        help="password to authenticate with")
    parser.add_argument('--fingerprint', '-f',
                        help="expected connection fingerprint")
    parser.add_argument('--start', '-S', action='append',
                        help="start a virtual machine")
    parser.add_argument('--stop', '-T', action='append',
                        help="stop a virtual machine")
    parser.add_argument('--restart', action='append',
                        help="restart a virtual machine")
    parser.add_argument('--pause', action='append',
                        help="pause a virtual machine")
    parser.add_argument('--resume', action='append',
                        help="resume a virtual machine")
    parser.add_argument('--generate', '-g', help="generate a new cert",
                        action='store_true')
    parser.add_argument('--spice-cert', '-C',
                        help="save SPICE server certificate to "
                        "this file (PEM format)")
    parser.add_argument('--debug', '-d', help="enable debug",
                        action='store_true')

    args = parser.parse_args()
    if not args.debug:
        sys.tracebacklimit = 0

    if args.generate:
        from .gencert import generate_certificate_file
        generate_certificate_file(args.cert)

    with UTMRemoteClient(args.cert, debug=args.debug) as client:
        await client.connect((args.server, args.port),
                             args.password, args.fingerprint)
        if args.start is None and args.stop is None and args.restart is None \
           and args.pause is None and args.resume is None:
            for vminfo in await client.remote.getVirtualMachineInformation(
                    await client.remote.listVirtualMachines()):
                print(f"{vminfo.id} {vminfo.name:32} {vminfo.state.name}")
        else:
            if args.pause is not None:
                for vm in args.pause:
                    print(f"Pausing {vm}")
                    await client.remote.pauseVirtualMachine(vm)
            if args.stop is not None:
                for vm in args.stop:
                    print(f"Stopping {vm}")
                    await client.remote.stopVirtualMachine(
                        vm, UTMVirtualMachineStopMethod.request)
            if args.restart is not None:
                for vm in args.restart:
                    print(f"Restarting {vm}")
                    await client.remote.restartVirtualMachine(vm)
            if args.start is not None:
                for vm in args.start:
                    print(f"Starting {vm}")
                    info = await client.remote.startVirtualMachine(vm, 0)
                    if info.spicePortExternal:
                        host = info.spiceHostExternal
                        port = info.spicePortExternal
                    else:
                        host = args.server
                        port = info.spicePortInternal
                    if port:
                        if args.spice_cert:
                            spice_cert = await client.get_spice_cert(
                                (host, port), info.spicePublicKey)
                            with open(args.spice_cert, "w") as f:
                                f.write(spice_cert)
                                print("Wrote SPICE server certificate to "
                                      f"{args.spice_cert}")
                        url = urllib.parse.urlunparse((
                            'spice', '['+host+']' if ':' in host else host,
                            '', '', urllib.parse.urlencode(
                                [('tls-port', port),
                                 ('password', info.spicePassword)]), ''))
                        print(f"SPICE URL: {url}")
            if args.resume is not None:
                for vm in args.resume:
                    print(f"Resuming {vm}")
                    await client.remote.resumeVirtualMachine(vm)


def main(argv):
    asyncio.run(async_main(argv))


if __name__ == "__main__":
    import sys
    main(sys.argv)
