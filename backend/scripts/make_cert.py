"""Create a self-signed HTTPS certificate for the LAN demo (phones need HTTPS for the microphone).

Writes backend/.cert/cert.pem and key.pem with SANs for localhost, 127.0.0.1 and this PC's LAN IP.
The phone will show a certificate warning once: tap Advanced -> Proceed.
Usage: uv run python scripts/make_cert.py [extra-ip-or-host ...]
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.signaling import lan_ip  # noqa: E402

out = Path(__file__).resolve().parent.parent / ".cert"
out.mkdir(exist_ok=True)
names = ["localhost", "127.0.0.1", lan_ip(), *sys.argv[1:]]
sans: list[x509.GeneralName] = []
for n in dict.fromkeys(names):
    try:
        sans.append(x509.IPAddress(ipaddress.ip_address(n)))
    except ValueError:
        sans.append(x509.DNSName(n))
key = ec.generate_private_key(ec.SECP256R1())
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RUKO local demo")])
now = dt.datetime.now(dt.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(subject).issuer_name(subject).public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=30))
    .add_extension(x509.SubjectAlternativeName(sans), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(key, hashes.SHA256())
)
(out / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
(out / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print(f"wrote {out / 'cert.pem'} for: {', '.join(dict.fromkeys(names))}")
