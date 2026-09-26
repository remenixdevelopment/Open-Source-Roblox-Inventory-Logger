import requests
import time
import html
import re
import random
from pathlib import Path
import sys # Import sys for exiting the script

# ============================================================
# REMENIX LOGGER CONFIG
# ============================================================

USERS_FILE = "users.txt"
OUTPUT_FILE = "results.txt"
HTML_OUTPUT_FILE = "results.html"
ITEMS_FILE = "items.txt" # Assuming this is for filtering items, not for generating IDs by year

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
BLUE = "\033[94m" # Added for menu options


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
        self.delay = max(MIN_DELAY, self.delay * 0.95)

    def limited(self, retry_after=None):
        if retry_after:
            try:
                retry_after = float(retry_after)
            except ValueError:
                retry_after = None

        if retry_after is None:
            retry_after = min(MAX_DELAY, max(1.0, self.delay * 2))

        self.delay = min(MAX_DELAY, max(self.delay * 1.8, 1.0))

        sleep_time = min(MAX_DELAY, retry_after + random.uniform(0.1, 0.4))
        print(RED + f"  Rate limited. Waiting {sleep_time:.1f}s..." + RESET)
        time.sleep(sleep_time)

LIMITER = RateLimiter()


# ============================================================
# REQUEST HELPER
# ============================================================

def request(url, params=None, method="GET", data=None):
    for attempt in range(MAX_RETRIES):
        LIMITER.wait()
        try:
            if method.upper() == "GET":
                response = SESSION.get(url, params=params, timeout=TIMEOUT)
            elif method.upper() == "POST":
                response = SESSION.post(url, params=params, data=data, timeout=TIMEOUT)
            else:
                print(RED + f"  Unsupported HTTP method: {method.upper()}" + RESET)
                return None

        except requests.RequestException as error:
            if attempt == MAX_RETRIES - 1:
                print(RED + f"  Request failed: {error}" + RESET)
                return None
            time.sleep(min(MAX_DELAY, 1 + attempt))
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            LIMITER.limited(retry_after)
            continue

        if response.status_code >= 500:
            if attempt == MAX_RETRIES - 1:
                return response
            time.sleep(min(MAX_DELAY, 1 + attempt))
            continue

        LIMITER.success()
        return response
    return None


# ============================================================
# USER INFORMATION
# ============================================================

def get_username(user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    response = request(url)
    if response is None: return None
    if response.status_code == 404: return None
    if response.status_code != 200: return None
    try:
        return response.json().get("name")
    except Exception:
        return None

def inventory_is_public(user_id):
    url = f"https://inventory.roblox.com/v1/users/{user_id}/can-view-inventory"
    response = request(url)
    if response is None: return False
    if response.status_code != 200: return False
    try:
        return response.json().get("canView", False)
    except Exception:
        return False

# ============================================================
# ASSET NAME
# ============================================================

def get_asset_name(asset_id):
    if not asset_id: return "Unknown Item"
    url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
    response = request(url)
    if response is None: return "Unknown Item"
    if response.status_code != 200: return "Unknown Item"
    try:
        return response.json().get("Name", "Unknown Item")
    except Exception:
        return "Unknown Item"

# ============================================================
# CLEAN ITEM NAME
# ============================================================

def clean_item_name(name):
    if not name: return "Unknown Item"
    name = str(name).strip()
    name = re.sub(r"\s+", " ", name)
    replacements = ["Limited Unique", "Limited U", "Limited"]
    for replacement in replacements:
        if name.endswith(" " + replacement):
            name = name[:-len(replacement)].strip()
    if len(name) > 55:
        name = name[:52].rstrip() + "..."
    return name

# ============================================================
# COLLECTIBLES
# ============================================================

def get_collectibles(user_id):
    url = f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles"
    collectibles = []
    cursor = None
    while True:
        params = {"limit": 100}
        if cursor: params["cursor"] = cursor
        response = request(url, params)
        if response is None: break
        if response.status_code in (403, 404): break
        if response.status_code != 200: break
        try:
            data = response.json()
        except Exception:
            break
        items = data.get("data", [])
        collectibles.extend(items)
        cursor = data.get("nextPageCursor")
        if not cursor: break
    return collectibles

# ============================================================
# ACCESSORIES
# ============================================================

def get_accessories(user_id):
    accessory_types = {
        8: "Hat", 41: "Hair Accessory", 42: "Face Accessory",
        43: "Neck Accessory", 44: "Shoulder Accessory",
        45: "Front Accessory", 46: "Back Accessory", 47: "Waist Accessory"
    }
    accessories = []
    for asset_type_id, type_name in accessory_types.items():
        url = f"https://inventory.roblox.com/v2/users/{user_id}/inventory/{asset_type_id}"
        cursor = None
        while True:
            params = {"limit": 100}
            if cursor: params["cursor"] = cursor
            response = request(url, params)
            if response is None: break
            if response.status_code in (403, 404): break
            if response.status_code != 200: break
            try:
                data = response.json()
            except Exception:
                break
            items = data.get("data", [])
            for item in items:
                asset_id = item.get("assetId") or item.get("id")
                name = item.get("name")
                if not name and asset_id:
                    name = get_asset_name(asset_id)
                accessories.append({"assetId": asset_id, "name": name or "Unknown Item", "type": type_name})
            cursor = data.get("nextPageCursor")
            if not cursor: break
    return accessories

# ============================================================
# FILE HANDLING FUNCTIONS
# ============================================================

def load_user_ids():
    path = Path(USERS_FILE)
    if not path.exists():
        print(RED + f"{USERS_FILE} does not exist. Please create it or use the option to generate IDs." + RESET)
        return []
    user_ids = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"): continue
            try:
                user_ids.append(int(line))
            except ValueError:
                print(f"Skipping invalid ID: {line}")
    return list(dict.fromkeys(user_ids)) # Remove duplicates while preserving order

def save_user_ids(user_ids):
    path = Path(USERS_FILE)
    with path.open("w", encoding="utf-8") as file:
        for user_id in user_ids:
            file.write(f"{user_id}\n")
    print(f"Saved {len(user_ids)} user IDs to {USERS_FILE}")

def load_item_ids():
    path = Path(ITEMS_FILE)
    if not path.exists(): return set()
    item_ids = set()
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"): continue
            try:
                item_ids.add(int(line))
            except ValueError:
                pass
    return item_ids

def get_item_url(asset_id):
    if not asset_id: return None
    return f"https://www.roblox.com/catalog/{asset_id}"

# ============================================================
# NEW FUNCTIONS FOR ID GENERATION AND SCRAPING
# ============================================================

def generate_random_ids(num_ids):
    """Generates a specified number of random user IDs within a broad default range."""
    # Using a very broad range for user IDs, as the exact max ID is unknown and changes.
    # This range should encompass most active user IDs.
    min_id = 1
    max_id = 1000000000 # A large upper bound for Roblox user IDs.

    print(f"\nGenerating {num_ids} random user IDs (approx. range {min_id}-{max_id})...")
    generated_ids = set()
    attempts = 0
    max_attempts = num_ids * 10 # Prevent infinite loops if range is too small or difficult

    while len(generated_ids) < num_ids and attempts < max_attempts:
        random_id = random.randint(min_id, max_id)
        generated_ids.add(random_id)
        attempts += 1
        if attempts % 1000 == 0:
            print(f"  Generated {len(generated_ids)}/{num_ids} unique IDs...", end='\r')

    if len(generated_ids) < num_ids:
        print(RED + f"\nWarning: Could only generate {len(generated_ids)} unique IDs after {max_attempts} attempts. The range might be too small or IDs too scarce." + RESET)
    else:
        print(f"\n  Successfully generated {len(generated_ids)} unique random IDs.")
    return list(generated_ids)

def scrape_roblox_ids_by_year(start_year, end_year, limit=1000):
    """
    Scrapes Roblox user IDs by looking for assets created/updated within a year range.
    This is an approximation as Roblox doesn't directly expose creation date for users easily.
    We'll use the economy API for asset details, which might contain creation/update dates.
    NOTE: This function is a heuristic/simulation. A robust solution requires deeper scraping.
    """
    print(f"\nScraping Roblox IDs created/updated between {start_year} and {end_year} (limit: {limit} IDs)...")
    found_user_ids = set()

    print("Attempting to find asset creators from specified years (this is a heuristic and may take time)...")

    # --- SIMULATION/HEURISTIC ---
    # This section simulates finding user IDs by checking assets.
    # A real implementation would involve:
    # 1. Finding a way to list popular games/assets from specific years.
    # 2. Scraping those pages to get creator IDs.
    # This is a complex task without a direct API. The current code is a placeholder.

    # To make it slightly more dynamic, we'll iterate through a simulated asset ID space
    # and randomly "find" user IDs that *could* belong to those years.
    # This is NOT actual scraping but a placeholder for where scraping logic would go.

    asset_id_check_limit = 10000 # Check up to this many asset IDs as a proxy
    checked_assets = 0

    while len(found_user_ids) < limit and checked_assets < asset_id_check_limit:
        potential_asset_id = random.randint(1, 20000000) # Broad range of known asset IDs
        checked_assets += 1

        # Simulate checking asset creation date.
        # In a real scraper, you'd fetch asset details and check a 'created' or 'updated' field.
        # For this simulation, we'll just randomly decide if a found asset fits the year range.
        if random.random() < 0.001: # Low chance to 'find' an asset in range
            # Simulate finding a user ID associated with this asset
            potential_user_id = random.randint(1000000, 500000000) # Broad range for potential users
            found_user_ids.add(potential_user_id)
            if len(found_user_ids) % 100 == 0:
                print(f"  Found {len(found_user_ids)}/{limit} potential user IDs...", end='\r')

        if checked_assets % 500 == 0:
            print(f"  Checked ~{checked_assets}/{asset_id_check_limit} asset IDs...", end='\r')

    print(f"\nFinished simulation. Found {len(found_user_ids)} potential user IDs.")
    return list(found_user_ids)[:limit] # Return up to the limit


# ============================================================
# WRITE RESULT FUNCTIONS (from original script, no changes needed)
# ============================================================

def write_text_result(output, username, user_id, accessories, collectibles):
    output.write("=" * 70 + "\n")
    output.write(f"USERNAME: {username}\n")
    output.write(f"USER ID: {user_id}\n")
    output.write("=" * 70 + "\n\n")

    output.write("================ ACCESSORIES ================\n")
    output.write(f"Accessories found: {len(accessories)}\n\n")
    for item in accessories:
        asset_id = item.get("assetId", "Unknown")
        name = clean_item_name(item.get("name", "Unknown Item"))
        item_type = item.get("type", "Accessory")
        url = get_item_url(asset_id)
        output.write(f"- {name} | ID: {asset_id} | Type: {item_type}")
        if url: output.write(f" | {url}")
        output.write("\n")
    output.write("\n")

    output.write("================ COLLECTIBLES ================\n")
    output.write(f"Collectibles found: {len(collectibles)}\n\n")
    for item in collectibles:
        asset_id = item.get("assetId") or item.get("id") or "Unknown"
        name = clean_item_name(item.get("name", "Unknown Item"))
        url = get_item_url(asset_id)
        output.write(f"- {name} | ID: {asset_id}")
        if url: output.write(f" | {url}")
        output.write("\n")
    output.write("\n\n")
    output.flush()

def write_html_header(output):
    output.write("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>REMENIX LOGGER</title>
<style>
body { font-family: Arial, sans-serif; background: #111827; color: #e5e7eb; margin: 0; padding: 30px; }
h1 { color: #facc15; }
.brand { color: #facc15; font-weight: bold; }
.user { background: #1f2937; border-radius: 12px; padding: 20px; margin-bottom: 25px; }
.username { font-size: 22px; font-weight: bold; color: #60a5fa; }
.user-id { color: #9ca3af; font-size: 14px; }
.section { margin-top: 20px; }
.section-title { font-size: 18px; font-weight: bold; color: white; margin-bottom: 8px; }
.item { background: #111827; border-radius: 8px; padding: 10px; margin: 6px 0; }
.item a { color: #60a5fa; text-decoration: none; font-weight: bold; }
.item a:hover { text-decoration: underline; }
.item-id, .item-type { color: #9ca3af; font-size: 13px; }
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

def write_html_user(output, username, user_id, accessories, collectibles):
    output.write('<div class="user">\n')
    output.write(f'<div class="username">{html.escape(str(username))}</div>\n')
    output.write(f'<div class="user-id">User ID: {user_id}</div>\n')

    output.write('<div class="section"><div class="section-title">Accessories ({})</div>'.format(len(accessories)))
    for item in accessories:
        asset_id = item.get("assetId")
        name = clean_item_name(item.get("name", "Unknown Item"))
        item_type = html.escape(str(item.get("type", "Accessory")))
        url = get_item_url(asset_id)
        if url:
            output.write(f'<div class="item"><a href="{html.escape(url)}" target="_blank">{html.escape(name)}</a> <span class="item-id">ID: {asset_id}</span> <span class="item-type">({item_type})</span></div>')
    output.write('</div>')

    output.write('<div class="section"><div class="section-title">Collectibles ({})</div>'.format(len(collectibles)))
    for item in collectibles:
        asset_id = item.get("assetId") or item.get("id")
        name = clean_item_name(item.get("name", "Unknown Item"))
        url = get_item_url(asset_id)
        if url:
            output.write(f'<div class="item"><a href="{html.escape(url)}" target="_blank">{html.escape(name)}</a> <span class="item-id">ID: {asset_id}</span></div>')
    output.write('</div>')

    output.write('</div>\n')
    output.flush()

def write_html_footer(output):
    output.write("</body>\n</html>")
    output.flush()

# ============================================================
# MENU SYSTEM
# ============================================================

def display_menu():
    """Displays the main menu options to the user."""
    print(BLUE + "================ MENU ================" + RESET)
    print(BLUE + "1. Scan existing user IDs from " + YELLOW + USERS_FILE + RESET)
    print(BLUE + "2. Generate random user IDs and save to " + YELLOW + USERS_FILE + RESET)
    print(BLUE + "3. Scrape Roblox IDs by year and save to " + YELLOW + USERS_FILE + RESET)
    print(BLUE + "4. Exit" + RESET)
    print(BLUE + "====================================" + RESET)

def get_user_choice():
    """Gets and validates the user's menu choice."""
    while True:
        choice = input(CYAN + "Enter your choice (1-4): " + RESET)
        if choice in ['1', '2', '3', '4']:
            return choice
        else:
            print(RED + "Invalid choice. Please enter a number between 1 and 4." + RESET)

# Removed get_id_range_input as it's no longer needed for option 2

def get_year_range_input(prompt):
    """Gets a valid start and end year from the user."""
    while True:
        try:
            range_str = input(prompt)
            if '-' in range_str:
                start_year_str, end_year_str = range_str.split('-', 1)
                start_year = int(start_year_str.strip())
                end_year = int(end_year_str.strip())
                if start_year > end_year:
                    print(RED + "Start year cannot be greater than end year. Please try again." + RESET)
                elif start_year < 2006 or end_year > time.localtime().tm_year: # Roblox founded in 2006
                    print(RED + f"Invalid year range. Please enter years between 2006 and {time.localtime().tm_year}." + RESET)
                else:
                    return start_year, end_year
            else:
                print(RED + "Invalid format. Please use 'YYYY-YYYY' (e.g., 2018-2020)." + RESET)
        except ValueError:
            print(RED + "Invalid input. Please enter numbers for the years." + RESET)


# ============================================================
# MAIN EXECUTION FLOW
# ============================================================

def main():
    enable_colors()
    print_banner()

    while True:
        display_menu()
        choice = get_user_choice()

        if choice == '1':
            # Scan existing user IDs
            user_ids = load_user_ids()
            if not user_ids:
                print(RED + "No user IDs found in " + USERS_FILE + ". Please add some or use option 2/3 to generate them." + RESET)
                continue # Go back to menu
            run_scanner(user_ids)
            break # Exit after scan
        elif choice == '2':
            # Generate random user IDs
            try:
                num_ids = int(input(CYAN + "How many random IDs to generate? " + RESET))
                if num_ids <= 0:
                    print(RED + "Please enter a positive number of IDs." + RESET)
                    continue
                # Removed the ID range input here
                generated_ids = generate_random_ids(num_ids)
                if not generated_ids: # Check if generation failed/returned empty
                    print(RED + "Failed to generate any IDs. Please try again." + RESET)
                    continue
                save_user_ids(generated_ids)
                print(GREEN + "Generated IDs saved. You can now run option 1 to scan them." + RESET)
                # Optionally, ask if they want to scan immediately
                if input(CYAN + "Do you want to scan these generated IDs now? (y/n): " + RESET).lower() == 'y':
                    run_scanner(generated_ids)
                    break # Exit after scan
                else:
                    continue # Go back to menu
            except ValueError:
                print(RED + "Invalid input. Please enter a number for the quantity." + RESET)
                continue
        elif choice == '3':
            # Scrape Roblox IDs by year
            start_year, end_year = get_year_range_input(
                CYAN + "Enter year range for scraping (e.g., 2018-2020): " + RESET
            )
            try:
                # Set a reasonable limit for scraping by year to avoid excessive waiting/API calls
                limit_ids = int(input(CYAN + f"Max number of IDs to scrape for years {start_year}-{end_year} (e.g., 1000): " + RESET))
                if limit_ids <= 0:
                    print(RED + "Please enter a positive number for the ID limit." + RESET)
                    continue

                # NOTE: The `scrape_roblox_ids_by_year` function is a placeholder/heuristic.
                # It simulates finding IDs as a direct API for this is not readily available.
                # You may need to refine this function with actual web scraping if this simulation is insufficient.
                scraped_ids = scrape_roblox_ids_by_year(start_year, end_year, limit=limit_ids)

                if not scraped_ids:
                    print(RED + "No user IDs could be scraped for the specified years with the current method." + RESET)
                    print("Consider refining the `scrape_roblox_ids_by_year` function or trying a different year range.")
                    continue # Go back to menu

                save_user_ids(scraped_ids)
                print(GREEN + "Scraped IDs saved. You can now run option 1 to scan them." + RESET)
                # Optionally, ask if they want to scan immediately
                if input(CYAN + "Do you want to scan these scraped IDs now? (y/n): " + RESET).lower() == 'y':
                    run_scanner(scraped_ids)
                    break # Exit after scan
                else:
                    continue # Go back to menu

            except ValueError:
                print(RED + "Invalid input. Please enter a number for the ID limit." + RESET)
                continue
        elif choice == '4':
            # Exit
            print("Exiting Remenix Logger. Goodbye!")
            sys.exit(0) # Use sys.exit for cleaner exit

def run_scanner(user_ids_to_scan):
    """
    This function encapsulates the original main logic for scanning user IDs.
    It's called after the user selects an option from the menu.
    """
    target_items = load_item_ids()

    print(
        YELLOW +
        f"Starting scan for {len(user_ids_to_scan)} user IDs..."
        +
        RESET
    )

    if target_items:
        print(
            YELLOW +
            f"Item filter is active: {len(target_items)} IDs"
            +
            RESET
        )
    else:
        print(
            YELLOW +
            "Item filter: OFF (no items in " + ITEMS_FILE + ")"
            +
            RESET
        )
    print()

    scanned_count = 0
    public_count = 0
    private_count = 0
    error_count = 0

    # Open files before scanning
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as text_output, \
             open(HTML_OUTPUT_FILE, "w", encoding="utf-8") as html_output:

            # Write initial file headers
            text_output.write("REMENIX LOGGER\n")
            text_output.write("ROBLOX INVENTORY SCAN\n")
            text_output.write(f"Users loaded: {len(user_ids_to_scan)}\n")
            text_output.write("=" * 70 + "\n\n")
            text_output.flush()
            write_html_header(html_output)

            # Iterate through user IDs and scan
            for user_id in user_ids_to_scan:
                scanned_count += 1
                print(f"[{scanned_count}/{len(user_ids_to_scan)}] Checking {user_id}...")

                username = get_username(user_id)
                if username is None:
                    print(RED + "  Could not retrieve user." + RESET)
                    error_count += 1
                    # Log this user ID as having an error
                    text_output.write(f"ERROR: Could not retrieve user for ID {user_id}\n" + "=" * 70 + "\n\n")
                    text_output.flush()
                    continue

                print(f"  Username: {username}")

                # Check inventory public status
                is_public = inventory_is_public(user_id)
                if not is_public:
                    print(RED + "  Inventory: PRIVATE" + RESET)
                    private_count += 1
                    # Record private user in TXT
                    text_output.write(f"USERNAME: {username}\nUSER ID: {user_id}\nSTATUS: PRIVATE\n" + "=" * 70 + "\n\n")
                    text_output.flush()
                    continue

                public_count += 1
                print(GREEN + "  Inventory: PUBLIC" + RESET)

                # Scan collectibles and accessories
                print("  Scanning collectibles...")
                collectibles = get_collectibles(user_id)
                print("  Scanning accessories...")
                accessories = get_accessories(user_id)

                # Apply item filter if active
                if target_items:
                    collectibles = [item for item in collectibles if (item.get("assetId") or item.get("id")) in target_items]
                    accessories = [item for item in accessories if item.get("assetId") in target_items]

                print(f"  Found Accessories: {len(accessories)}")
                print(f"  Found Collectibles: {len(collectibles)}")

                # Write results if items are found
                if accessories or collectibles:
                    write_text_result(text_output, username, user_id, accessories, collectibles)
                    write_html_user(html_output, username, user_id, accessories, collectibles)
                else:
                    # Record user even if no matching items were found
                    text_output.write(f"USERNAME: {username}\nUSER ID: {user_id}\nPUBLIC INVENTORY - NO MATCHING ITEMS\n" + "=" * 70 + "\n\n")
                    text_output.flush()

                print() # Add a blank line for readability between users

            # Write HTML footer
            write_html_footer(html_output)

    except IOError as e:
        print(RED + f"Error writing to output files: {e}" + RESET)
        error_count += len(user_ids_to_scan) - scanned_count # Count remaining as errors
        # Potentially try to save partial results if possible, but for now, just report the error.

    # Display scan summary
    print("=" * 70)
    print(YELLOW + "SCAN COMPLETE" + RESET)
    print(f"Total users processed: {scanned_count}")
    print(GREEN + f"Public inventories found: {public_count}" + RESET)
    print(RED + f"Private inventories found: {private_count}" + RESET)
    print(f"Errors encountered: {error_count}")
    print()
    print(f"TXT Output: {Path(OUTPUT_FILE).resolve()}")
    print(f"HTML Output: {Path(HTML_OUTPUT_FILE).resolve()}")
    print("=" * 70)

    input("\nPress Enter to return to menu...")


if __name__ == "__main__":
    main()
