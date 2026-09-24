import requests
import time
import html
import re
import random
from pathlib import Path

# ============================================================
# REMENIX LOGGER
# ============================================================

USERS_FILE = "users.txt"
OUTPUT_FILE = "results.txt"
HTML_OUTPUT_FILE = "results.html"
ITEMS_FILE = "items.txt"

# Normal pacing.
# The scanner automatically backs off if Roblox sends 429.
BASE_DELAY = 0.25
MIN_DELAY = 0.15
MAX_DELAY = 0.0

MAX_RETRIES = 5
TIMEOUT = 5

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "REMENIX-LOGGER/1.0"
})


# ============================================================
# TERMINAL COLORS
# ============================================================

RESET = "\033[0m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"


def enable_colors():
    """Enable ANSI colors on Windows terminals."""

    try:
        import os
        os.system("")
    except Exception:
        pass


# ============================================================
# BANNER
# ============================================================

def print_banner():

    print(YELLOW + r"""
██████╗ ███████╗███╗   ███╗███████╗███╗   ██╗██╗██╗  ██╗
██╔══██╗██╔════╝████╗ ████║██╔════╝████╗  ██║██║╚██╗██╔╝
██████╔╝█████╗  ██╔████╔██║█████╗  ██╔██╗ ██║██║ ╚███╔╝
██╔══██╗██╔══╝  ██║╚██╔╝██║██╔══╝  ██║╚██╗██║██║ ██╔██╗
██║  ██║███████╗██║ ╚═╝ ██║███████╗██║ ╚████║██║██╔╝ ██╗
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝
""" + RESET)

    print(YELLOW + "REMENIX LOGGER" + RESET)
    print(YELLOW + "Telegram: T.me/RemenixEdits2" + RESET)
    print(YELLOW + "Discord: militaryremenix" + RESET)
    print()


# ============================================================
# ADAPTIVE RATE LIMITER
# ============================================================

class RateLimiter:

    def __init__(self):
        self.delay = BASE_DELAY
        self.last_request = 0

    def wait(self):

        elapsed = time.monotonic() - self.last_request

        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        self.last_request = time.monotonic()

    def success(self):

        # Slowly become faster after successful requests.
        self.delay = max(
            MIN_DELAY,
            self.delay * 0.95
        )

    def limited(self, retry_after=None):

        if retry_after:

            try:
                retry_after = float(retry_after)
            except ValueError:
                retry_after = None

        if retry_after is None:
            retry_after = min(
                MAX_DELAY,
                max(
                    1.0,
                    self.delay * 2
                )
            )

        self.delay = min(
            MAX_DELAY,
            max(
                self.delay * 1.8,
                1.0
            )
        )

        # Small random variation prevents identical timing.
        sleep_time = min(
            MAX_DELAY,
            retry_after + random.uniform(0.1, 0.4)
        )

        print(
            RED +
            f"  Rate limited. Waiting {sleep_time:.1f}s..."
            +
            RESET
        )

        time.sleep(sleep_time)


LIMITER = RateLimiter()


# ============================================================
# REQUEST HELPER
# ============================================================

def request(url, params=None):

    for attempt in range(MAX_RETRIES):

        LIMITER.wait()

        try:

            response = SESSION.get(
                url,
                params=params,
                timeout=TIMEOUT
            )

        except requests.RequestException as error:

            if attempt == MAX_RETRIES - 1:
                print(
                    RED +
                    f"  Request failed: {error}" +
                    RESET
                )
                return None

            time.sleep(
                min(
                    MAX_DELAY,
                    1 + attempt
                )
            )

            continue

        if response.status_code == 429:

            retry_after = response.headers.get(
                "Retry-After"
            )

            LIMITER.limited(
                retry_after
            )

            continue

        if response.status_code >= 500:

            if attempt == MAX_RETRIES - 1:
                return response

            time.sleep(
                min(
                    MAX_DELAY,
                    1 + attempt
                )
            )

            continue

        LIMITER.success()

        return response

    return None


# ============================================================
# USER INFORMATION
# ============================================================

def get_username(user_id):

    url = (
        f"https://users.roblox.com/v1/users/{user_id}"
    )

    response = request(url)

    if response is None:
        return None

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        return None

    try:
        return response.json().get("name")
    except Exception:
        return None


def inventory_is_public(user_id):

    url = (
        f"https://inventory.roblox.com/v1/users/"
        f"{user_id}/can-view-inventory"
    )

    response = request(url)

    if response is None:
        return False

    if response.status_code != 200:
        return False

    try:
        return response.json().get(
            "canView",
            False
        )
    except Exception:
        return False


# ============================================================
# ASSET NAME
# ============================================================

def get_asset_name(asset_id):

    if not asset_id:
        return "Unknown Item"

    url = (
        f"https://economy.roblox.com/"
        f"v2/assets/{asset_id}/details"
    )

    response = request(url)

    if response is None:
        return "Unknown Item"

    if response.status_code != 200:
        return "Unknown Item"

    try:

        return response.json().get(
            "Name",
            "Unknown Item"
        )

    except Exception:

        return "Unknown Item"


# ============================================================
# CLEAN ITEM NAME
# ============================================================

def clean_item_name(name):

    if not name:
        return "Unknown Item"

    name = str(name).strip()

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    replacements = [
        "Limited Unique",
        "Limited U",
        "Limited"
    ]

    for replacement in replacements:

        if name.endswith(
            " " + replacement
        ):

            name = name[
                :-len(replacement)
            ].strip()

    if len(name) > 55:

        name = (
            name[:52].rstrip()
            + "..."
        )

    return name


# ============================================================
# COLLECTIBLES
# ============================================================

def get_collectibles(user_id):

    url = (
        f"https://inventory.roblox.com/v1/users/"
        f"{user_id}/assets/collectibles"
    )

    collectibles = []
    cursor = None

    while True:

        params = {
            "limit": 100
        }

        if cursor:
            params["cursor"] = cursor

        response = request(
            url,
            params
        )

        if response is None:
            break

        if response.status_code in (403, 404):
            break

        if response.status_code != 200:
            break

        try:
            data = response.json()
        except Exception:
            break

        items = data.get(
            "data",
            []
        )

        collectibles.extend(
            items
        )

        cursor = data.get(
            "nextPageCursor"
        )

        if not cursor:
            break

    return collectibles


# ============================================================
# ACCESSORIES
# ============================================================

def get_accessories(user_id):

    accessory_types = {

        8: "Hat",
        41: "Hair Accessory",
        42: "Face Accessory",
        43: "Neck Accessory",
        44: "Shoulder Accessory",
        45: "Front Accessory",
        46: "Back Accessory",
        47: "Waist Accessory"
    }

    accessories = []

    for asset_type_id, type_name in accessory_types.items():

        url = (
            f"https://inventory.roblox.com/v2/users/"
            f"{user_id}/inventory/{asset_type_id}"
        )

        cursor = None

        while True:

            params = {
                "limit": 100
            }

            if cursor:
                params["cursor"] = cursor

            response = request(
                url,
                params
            )

            if response is None:
                break

            if response.status_code in (403, 404):
                break

            if response.status_code != 200:
                break

            try:
                data = response.json()
            except Exception:
                break

            items = data.get(
                "data",
                []
            )

            for item in items:

                asset_id = (
                    item.get("assetId")
                    or item.get("id")
                )

                name = item.get(
                    "name"
                )

                # Only make the extra name request
                # when the inventory response did
                # not already provide a name.
                if not name and asset_id:

                    name = get_asset_name(
                        asset_id
                    )

                accessories.append({
                    "assetId": asset_id,
                    "name": name or "Unknown Item",
                    "type": type_name
                })

            cursor = data.get(
                "nextPageCursor"
            )

            if not cursor:
                break

    return accessories


# ============================================================
# LOAD USERS
# ============================================================

def load_user_ids():

    path = Path(
        USERS_FILE
    )

    if not path.exists():

        print(
            RED +
            f"{USERS_FILE} does not exist."
            +
            RESET
        )

        return []

    user_ids = []

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            try:

                user_ids.append(
                    int(line)
                )

            except ValueError:

                print(
                    f"Skipping invalid ID: {line}"
                )

    # Remove duplicates while preserving order.
    return list(
        dict.fromkeys(user_ids)
    )


# ============================================================
# LOAD ITEM FILTER
# ============================================================

def load_item_ids():

    path = Path(
        ITEMS_FILE
    )

    if not path.exists():
        return set()

    item_ids = set()

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            try:
                item_ids.add(
                    int(line)
                )
            except ValueError:
                pass

    return item_ids


# ============================================================
# ITEM URL
# ============================================================

def get_item_url(asset_id):

    if not asset_id:
        return None

    return (
        f"https://www.roblox.com/catalog/"
        f"{asset_id}"
    )


# ============================================================
# WRITE TXT RESULT
# ============================================================

def write_text_result(
    output,
    username,
    user_id,
    accessories,
    collectibles
):

    output.write(
        "=" * 70 + "\n"
    )

    output.write(
        f"USERNAME: {username}\n"
    )

    output.write(
        f"USER ID: {user_id}\n"
    )

    output.write(
        "=" * 70 + "\n\n"
    )

    output.write(
        "================ ACCESSORIES ================\n"
    )

    output.write(
        f"Accessories found: "
        f"{len(accessories)}\n\n"
    )

    for item in accessories:

        asset_id = item.get(
            "assetId",
            "Unknown"
        )

        name = clean_item_name(
            item.get(
                "name",
                "Unknown Item"
            )
        )

        item_type = item.get(
            "type",
            "Accessory"
        )

        url = get_item_url(
            asset_id
        )

        output.write(
            f"- {name} | "
            f"ID: {asset_id} | "
            f"Type: {item_type}"
        )

        if url:
            output.write(
                f" | {url}"
            )

        output.write("\n")

    output.write("\n")

    output.write(
        "================ COLLECTIBLES ================\n"
    )

    output.write(
        f"Collectibles found: "
        f"{len(collectibles)}\n\n"
    )

    for item in collectibles:

        asset_id = (
            item.get("assetId")
            or item.get("id")
            or "Unknown"
        )

        name = clean_item_name(
            item.get(
                "name",
                "Unknown Item"
            )
        )

        url = get_item_url(
            asset_id
        )

        output.write(
            f"- {name} | ID: {asset_id}"
        )

        if url:
            output.write(
                f" | {url}"
            )

        output.write("\n")

    output.write(
        "\n\n"
    )

    # Make sure the result is physically written
    # immediately instead of waiting until the scan ends.
    output.flush()


# ============================================================
# HTML
# ============================================================

def write_html_header(output):

    output.write("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>REMENIX LOGGER</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #111827;
    color: #e5e7eb;
    margin: 0;
    padding: 30px;
}

h1 {
    color: #facc15;
}

.brand {
    color: #facc15;
    font-weight: bold;
}

.user {
    background: #1f2937;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 25px;
}

.username {
    font-size: 22px;
    font-weight: bold;
    color: #60a5fa;
}

.user-id {
    color: #9ca3af;
    font-size: 14px;
}

.section {
    margin-top: 20px;
}

.section-title {
    font-size: 18px;
    font-weight: bold;
    color: white;
    margin-bottom: 8px;
}

.item {
    background: #111827;
    border-radius: 8px;
    padding: 10px;
    margin: 6px 0;
}

.item a {
    color: #60a5fa;
    text-decoration: none;
    font-weight: bold;
}

.item a:hover {
    text-decoration: underline;
}

.item-id,
.item-type {
    color: #9ca3af;
    font-size: 13px;
}

</style>
</head>

<body>

<h1>REMENIX LOGGER</h1>

<div class="brand">
Telegram: T.me/RemenixEdits2<br>
Discord: militaryremenix
</div>

<br>
""")


def write_html_user(
    output,
    username,
    user_id,
    accessories,
    collectibles
):

    output.write(
        '<div class="user">\n'
    )

    output.write(
        '<div class="username">'
        + html.escape(str(username))
        + '</div>\n'
    )

    output.write(
        '<div class="user-id">'
        f'User ID: {user_id}'
        '</div>\n'
    )

    # Accessories

    output.write(
        '<div class="section">'
    )

    output.write(
        '<div class="section-title">'
        f'Accessories ({len(accessories)})'
        '</div>'
    )

    for item in accessories:

        asset_id = item.get(
            "assetId"
        )

        name = clean_item_name(
            item.get(
                "name",
                "Unknown Item"
            )
        )

        item_type = html.escape(
            str(
                item.get(
                    "type",
                    "Accessory"
                )
            )
        )

        url = get_item_url(
            asset_id
        )

        if url:

            output.write(
                '<div class="item">'
                f'<a href="{html.escape(url)}" '
                f'target="_blank">'
                f'{html.escape(name)}'
                '</a> '
                f'<span class="item-id">'
                f'ID: {asset_id}</span> '
                f'<span class="item-type">'
                f'({item_type})</span>'
                '</div>'
            )

    output.write(
        '</div>'
    )

    # Collectibles

    output.write(
        '<div class="section">'
    )

    output.write(
        '<div class="section-title">'
        f'Collectibles ({len(collectibles)})'
        '</div>'
    )

    for item in collectibles:

        asset_id = (
            item.get("assetId")
            or item.get("id")
        )

        name = clean_item_name(
            item.get(
                "name",
                "Unknown Item"
            )
        )

        url = get_item_url(
            asset_id
        )

        if url:

            output.write(
                '<div class="item">'
                f'<a href="{html.escape(url)}" '
                f'target="_blank">'
                f'{html.escape(name)}'
                '</a> '
                f'<span class="item-id">'
                f'ID: {asset_id}</span>'
                '</div>'
            )

    output.write(
        '</div>'
    )

    output.write(
        '</div>\n'
    )

    output.flush()


def write_html_footer(output):

    output.write(
        """
</body>
</html>
"""
    )

    output.flush()


# ============================================================
# MAIN
# ============================================================

def main():

    enable_colors()
    print_banner()

    user_ids = load_user_ids()

    if not user_ids:

        print(
            RED +
            "No users to scan."
            +
            RESET
        )

        input(
            "\nPress Enter to exit..."
        )

        return

    target_items = load_item_ids()

    print(
        YELLOW +
        f"Users loaded: {len(user_ids)}"
        +
        RESET
    )

    if target_items:

        print(
            YELLOW +
            f"Item filter: {len(target_items)} IDs"
            +
            RESET
        )

    else:

        print(
            YELLOW +
            "Item filter: OFF"
            +
            RESET
        )

    print()

    scanned = 0
    public = 0
    private = 0
    errors = 0

    # --------------------------------------------------------
    # Open files before scanning so results are available
    # throughout the scan.
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as text_output, open(
        HTML_OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as html_output:

        text_output.write(
            "REMENIX LOGGER\n"
        )

        text_output.write(
            "ROBLOX INVENTORY SCAN\n"
        )

        text_output.write(
            f"Users loaded: {len(user_ids)}\n"
        )

        text_output.write(
            "=" * 70 + "\n\n"
        )

        text_output.flush()

        write_html_header(
            html_output
        )

        for user_id in user_ids:

            scanned += 1

            print(
                f"[{scanned}/{len(user_ids)}] "
                f"Checking {user_id}..."
            )

            username = get_username(
                user_id
            )

            if username is None:

                print(
                    RED +
                    "  Could not retrieve user."
                    +
                    RESET
                )

                errors += 1
                continue

            print(
                f"  Username: {username}"
            )

            # ------------------------------------------------
            # PUBLIC / PRIVATE
            # ------------------------------------------------

            is_public = inventory_is_public(
                user_id
            )

            if not is_public:

                print(
                    RED +
                    "  Inventory: PRIVATE"
                    +
                    RESET
                )

                private += 1

                # Keep a record in TXT so you know
                # the user was checked.
                text_output.write(
                    "=" * 70 + "\n"
                )

                text_output.write(
                    f"USERNAME: {username}\n"
                )

                text_output.write(
                    f"USER ID: {user_id}\n"
                )

                text_output.write(
                    "STATUS: PRIVATE\n"
                )

                text_output.write(
                    "=" * 70 + "\n\n"
                )

                text_output.flush()

                continue

            public += 1

            print(
                GREEN +
                "  Inventory: PUBLIC"
                +
                RESET
            )

            # ------------------------------------------------
            # COLLECTIBLES
            # ------------------------------------------------

            print(
                "  Scanning collectibles..."
            )

            collectibles = get_collectibles(
                user_id
            )

            # ------------------------------------------------
            # ACCESSORIES
            # ------------------------------------------------

            print(
                "  Scanning accessories..."
            )

            accessories = get_accessories(
                user_id
            )

            # ------------------------------------------------
            # FILTER
            # ------------------------------------------------

            if target_items:

                collectibles = [
                    item
                    for item in collectibles
                    if (
                        item.get("assetId")
                        or item.get("id")
                    ) in target_items
                ]

                accessories = [
                    item
                    for item in accessories
                    if item.get("assetId")
                    in target_items
                ]

            print(
                f"  Accessories: {len(accessories)}"
            )

            print(
                f"  Collectibles: {len(collectibles)}"
            )

            # ------------------------------------------------
            # WRITE IMMEDIATELY
            # ------------------------------------------------

            if accessories or collectibles:

                write_text_result(
                    text_output,
                    username,
                    user_id,
                    accessories,
                    collectibles
                )

                write_html_user(
                    html_output,
                    username,
                    user_id,
                    accessories,
                    collectibles
                )

            else:

                # Still record the user.
                text_output.write(
                    "=" * 70 + "\n"
                )

                text_output.write(
                    f"USERNAME: {username}\n"
                )

                text_output.write(
                    f"USER ID: {user_id}\n"
                )

                text_output.write(
                    "PUBLIC INVENTORY - "
                    "NO MATCHING ITEMS\n"
                )

                text_output.write(
                    "=" * 70 + "\n\n"
                )

                text_output.flush()

            print()

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    print(
        "=" * 70
    )

    print(
        YELLOW +
        "SCAN COMPLETE"
        +
        RESET
    )

    print(
        f"Users scanned: {scanned}"
    )

    print(
        GREEN +
        f"Public inventories: {public}"
        +
        RESET
    )

    print(
        RED +
        f"Private inventories: {private}"
        +
        RESET
    )

    print(
        f"Errors: {errors}"
    )

    print()

    print(
        f"TXT: {Path(OUTPUT_FILE).resolve()}"
    )

    print(
        f"HTML: {Path(HTML_OUTPUT_FILE).resolve()}"
    )

    input(
        "\nPress Enter to exit..."
    )


if __name__ == "__main__":
    main()
