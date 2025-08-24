import datetime
import os


def generate_certificate():
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import (hashes, asymmetric,
                                                serialization)

    one_day = datetime.timedelta(1, 0, 0)
    private_key = asymmetric.rsa.generate_private_key(
            public_exponent=65537, key_size=4096, backend=default_backend())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()
    subject = x509.Name([
        x509.NameAttribute(x509.oid.NameOID.ORGANIZATION_NAME, "UTM"),
        x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "UTM Remote Client")])
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(subject)
    builder = builder.not_valid_before(
        datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(
        datetime.datetime.today() + (one_day*3650))
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True)
    builder = builder.add_extension(
        x509.KeyUsage(digital_signature=True, content_commitment=False,
                      key_encipherment=True, data_encipherment=False,
                      key_agreement=False, key_cert_sign=True, crl_sign=True,
                      encipher_only=False, decipher_only=False), critical=True)
    builder = builder.add_extension(
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
        critical=False)
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=default_backend())

    return (certificate.public_bytes(serialization.Encoding.PEM),
            private_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(b"password")))


def _opener_private(path, flags):
    return os.open(path, flags, 0o600)


def generate_certificate_file(filename):
    with open(filename, "xb", opener=_opener_private) as f:
        cert, key = generate_certificate()
        f.write(key+cert)


if __name__ == "__main__":
    print("Go")
    generate_certificate_file("cert2.pem")
    print("Done")
