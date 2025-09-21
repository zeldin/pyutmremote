# pyutmremote

pyutmremote is a python reimplementation of the remote protocol
used by [UTM](https://github.com/utmapp/UTM) allowing virtual machines
to be remote controlled from non-Apple platforms.


## GUI

To use the GUI, run

```
python -m utmremote.gui
```


## CLI

To use the CLI, run

```
python -m utmremote.cli -c cert.pem -s remote_host
```

where `cert.pem` is your client certificate (see below) and `remote_host`
is the remote host to connect to.


## Client certficiate

The UTM remote protocol requires the client to provide a client
certificate.  This certificate can be self signed, but the combined
fingerprint of the server and client certificates is used to mark a
connection as "trusted".  To create a certificate, either use openssl:

```
openssl req -x509 -newkey rsa:4096 -out cert.pem -keyout cert.pem -sha256 -days 3650 -passout pass:password -subj "/O=UTM/CN=UTM Remote Client"
```

or use the `-g` flag the first time connecting to have the CLI generate
one for you.  Check that the same fingerprint is displayed both in the
client and on the server before trusting the connection.

The GUI automatically creates a client certificate the first time it
is started.
