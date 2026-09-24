import requests
import time
from pathlib import Path

# ============================================================
# SETTINGS
# ============================================================

# Put Roblox user IDs in users.txt, one per line.
USERS_FILE = "users.txt"

# Results will be saved here.
OUTPUT_FILE = "results.txt"

# Optional: put specific item/asset IDs here, one per line.
# Leave the file empty if you want to log all collectible items.
ITEMS_FILE = "items.txt"

# Delay between users to avoid hammering the API.
REQUEST_DELAY = 1.0

# ============================================================
# ROBLOX API
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "RobloxInventoryLogger/1.0"
})


def get_username(user_id):
    """Get the Roblox username for a user ID."""

    url = f"https://users.roblox.com/v1/users/{user_id}"

    try:
        response = SESSION.get(url, timeout=15)

        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()
        return data.get("name")

    except requests.RequestException as error:
        print(f"Could not get username for {user_id}: {error}")
        return None


def inventory_is_public(user_id):
    """Check whether Roblox says the user's inventory can be viewed."""

    url = (
        f"https://inventory.roblox.com/v1/users/"
        f"{user_id}/can-view-inventory"
    )

    try:
        response = SESSION.get(url, timeout=15)

        if response.status_code != 200:
            return False

        data = response.json()

        return data.get("canView", False)

    except requests.RequestException as error:
        print(f"Could not check inventory for {user_id}: {error}")
        return False


def get_collectibles(user_id):
    """Get collectible assets owned by a user."""

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

        try:
            response = SESSION.get(
                url,
                params=params,
                timeout=20
            )

        except requests.RequestException as error:
            print(f"Inventory request failed: {error}")
            break

        if response.status_code == 403:
            print("Inventory is private or inaccessible.")
            break

        if response.status_code == 429:
            print("Rate limited. Waiting 10 seconds...")
            time.sleep(10)
            continue

        if response.status_code != 200:
            print(
                f"Inventory request returned "
                f"HTTP {response.status_code}"
            )
            break

        data = response.json()

        items = data.get("data", [])

        collectibles.extend(items)

        cursor = data.get("nextPageCursor")

        if not cursor:
            break

        time.sleep(0.5)

    return collectibles


def load_user_ids():
    """Load user IDs from users.txt."""

    path = Path(USERS_FILE)

    if not path.exists():
        print(f"{USERS_FILE} does not exist.")
        print("Create it and put one Roblox user ID per line.")
        return []

    user_ids = []

    with path.open("r", encoding="utf-8") as file:

        for line in file:
            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            try:
                user_ids.append(int(line))

            except ValueError:
                print(f"Skipping invalid user ID: {line}")

    return user_ids


def load_item_ids():
    """Load optional item IDs from items.txt."""

    path = Path(ITEMS_FILE)

    if not path.exists():
        return set()

    item_ids = set()

    with path.open("r", encoding="utf-8") as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            try:
                item_ids.add(int(line))

            except ValueError:
                print(f"Skipping invalid item ID: {line}")

    return item_ids


def write_result(
    file,
    username,
    user_id,
    items
):
    """Write one user's results to the TXT file."""

    file.write("=" * 70 + "\n")
    file.write(f"Username: {username}\n")
    file.write(f"User ID: {user_id}\n")
    file.write(f"Items found: {len(items)}\n")
    file.write("-" * 70 + "\n")

    for item in items:

        asset_id = item.get("assetId", "Unknown")
        name = item.get("name", "Unknown")

        file.write(
            f"Item: {name} | Asset ID: {asset_id}\n"
        )

    file.write("\n")


def main():

    print("=" * 70)
    print("ROBLOX INVENTORY LOGGER")
    print("=" * 70)

    user_ids = load_user_ids()

    if not user_ids:
        print("\nNo users to scan.")
        input("\nPress Enter to exit...")
        return

    target_items = load_item_ids()

    if target_items:
        print(
            f"\nFiltering for {len(target_items)} "
            f"specific item IDs."
        )
    else:
        print("\nNo item filter detected.")
        print("All collectible items will be logged.")

    print(f"\nUsers loaded: {len(user_ids)}")
    print()

    scanned = 0
    public = 0
    private = 0
    errors = 0

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as output:

        output.write(
            "ROBLOX INVENTORY SCAN\n"
        )

        output.write(
            f"Users scanned: {len(user_ids)}\n"
        )

        output.write(
            "=" * 70 + "\n\n"
        )

        for user_id in user_ids:

            scanned += 1

            print(
                f"[{scanned}/{len(user_ids)}] "
                f"Checking {user_id}..."
            )

            username = get_username(user_id)

            if username is None:
                print("  User not found.")
                errors += 1
                continue

            print(f"  Username: {username}")

            if not inventory_is_public(user_id):

                print("  Inventory: PRIVATE")

                private += 1

                continue

            print("  Inventory: PUBLIC")

            public += 1

            items = get_collectibles(user_id)

            # If items.txt contains IDs, only keep those items.
            if target_items:

                items = [
                    item
                    for item in items
                    if item.get("assetId") in target_items
                ]

            print(
                f"  Matching items: {len(items)}"
            )

            # Only write users who have matching items.
            if items:

                write_result(
                    output,
                    username,
                    user_id,
                    items
                )

            time.sleep(REQUEST_DELAY)

    print()
    print("=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)

    print(f"Users scanned: {scanned}")
    print(f"Public inventories: {public}")
    print(f"Private inventories: {private}")
    print(f"Errors: {errors}")

    print(f"\nResults saved to:")
    print(Path(OUTPUT_FILE).resolve())

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
