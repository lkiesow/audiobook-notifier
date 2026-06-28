import getpass
import os
import sys
from urllib.parse import quote

import requests


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _die(msg: str) -> None:
    print(f"\nError: {msg}", file=sys.stderr)
    sys.exit(1)


def run_wizard() -> None:
    print("Matrix setup wizard")
    print("===================")
    print("This will create a Matrix room and print the environment variables")
    print("needed to enable notifications.\n")

    homeserver = input("Homeserver URL (e.g. https://matrix.example.org): ").strip().rstrip("/")
    if not homeserver:
        _die("Homeserver URL is required.")

    username = input("Bot username (localpart or full @user:server): ").strip()
    if not username:
        _die("Username is required.")

    password = getpass.getpass("Bot password: ")
    if not password:
        _die("Password is required.")

    room_name = input("Name for the new room: ").strip()
    if not room_name:
        _die("Room name is required.")

    invite_user = input("Matrix handle of user to invite (e.g. @you:server): ").strip()
    if not invite_user:
        _die("User handle is required.")

    # Step 1: Login
    print("\nLogging in…")
    try:
        r = requests.post(
            f"{homeserver}/_matrix/client/v3/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": username},
                "password": password,
                "initial_device_display_name": "Audiobook Notifier Setup",
            },
            timeout=10,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        _die(f"Login failed: {e.response.status_code} {e.response.text}")
    except requests.RequestException as e:
        _die(f"Login failed: {e}")

    data = r.json()
    access_token = data["access_token"]
    bot_user_id = data["user_id"]
    print(f"Logged in as {bot_user_id}")

    # Step 2: Create room and invite user
    print(f"\nCreating room '{room_name}' and inviting {invite_user}…")
    try:
        r = requests.post(
            f"{homeserver}/_matrix/client/v3/createRoom",
            json={
                "preset": "private_chat",
                "name": room_name,
                "visibility": "private",
                "is_direct": False,
                "invite": [invite_user],
            },
            headers=_headers(access_token),
            timeout=10,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        _die(f"Failed to create room: {e.response.status_code} {e.response.text}")
    except requests.RequestException as e:
        _die(f"Failed to create room: {e}")

    room_id = r.json()["room_id"]
    encoded_room = quote(room_id, safe="")
    print(f"Room created: {room_id}")

    # Set room avatar
    icon_path = os.path.join(os.path.dirname(__file__), "static", "icon.png")
    print("\nUploading room avatar…")
    try:
        with open(icon_path, "rb") as f:
            r = requests.post(
                f"{homeserver}/_matrix/media/v1/upload",
                headers={**_headers(access_token), "Content-Type": "image/png"},
                params={"filename": "icon.png"},
                data=f,
                timeout=30,
            )
        r.raise_for_status()
        mxc_uri = r.json()["content_uri"]
        r = requests.put(
            f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/state/m.room.avatar",
            json={"url": mxc_uri},
            headers=_headers(access_token),
            timeout=10,
        )
        r.raise_for_status()
        print("Room avatar set.")
    except Exception as e:
        print(f"Warning: could not set room avatar: {e}", file=sys.stderr)

    # Step 3: Get current power levels
    try:
        r = requests.get(
            f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/state/m.room.power_levels",
            headers=_headers(access_token),
            timeout=10,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        _die(f"Failed to fetch power levels: {e.response.status_code} {e.response.text}")
    except requests.RequestException as e:
        _die(f"Failed to fetch power levels: {e}")

    power_levels = r.json()

    # Step 4: Promote invited user to admin and demote bot — single PUT
    print(f"\nPromoting {invite_user} to admin and demoting bot to regular user…")
    users = power_levels.get("users", {})
    users[invite_user] = 100
    users[bot_user_id] = 0
    power_levels["users"] = users

    try:
        r = requests.put(
            f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/state/m.room.power_levels",
            json=power_levels,
            headers=_headers(access_token),
            timeout=10,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        _die(f"Failed to set power levels: {e.response.status_code} {e.response.text}")
    except requests.RequestException as e:
        _die(f"Failed to set power levels: {e}")

    print("\nDone! Add these to your .env file:\n")
    print(f"MATRIX_HOMESERVER={homeserver}")
    print(f"MATRIX_ACCESS_TOKEN={access_token}")
    print(f"MATRIX_ROOM_ID={room_id}")
