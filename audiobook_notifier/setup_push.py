import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_keys() -> tuple[str, str]:
    """A VAPID key pair as (public, private), both base64url.

    The public key is the uncompressed P-256 point browsers expect as
    applicationServerKey, the private key the raw 32-byte scalar.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(public), _b64url(private)


def run() -> None:
    public, private = generate_keys()
    print("Add these lines to your .env (or /etc/audiobook-notifier.conf):\n")
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:you@example.org")
    print("\nSet VAPID_SUBJECT to a contact address push services can reach you at.")
    print("Keep the key pair stable: changing it invalidates every subscribed device.")
