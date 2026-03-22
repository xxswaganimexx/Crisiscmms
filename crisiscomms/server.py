# =============================================================
#  CrisisComms — server.py
#  WHO RUNS THIS: Person 1 (Python person) on their laptop
#  HOW TO RUN: python server.py
#  WHAT IT DOES: Becomes the brain. All phones talk to this.
# =============================================================

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import json
import os
import math
import time

app = Flask(__name__, static_folder="static")
CORS(app)  # This allows phones on the hotspot to talk to this server

# =============================================================
#  IN-MEMORY STORAGE
#  These are just Python lists/dicts that hold data while
#  the server is running. If server restarts, data resets.
#  That's fine for a 6-hour hackathon.
# =============================================================

messages = []    # All alerts broadcasted by survivors
survivors = []   # All people who have checked in
resources = {    # Global resource levels (0-100)
    "water": 34,
    "food": 61,
    "medical": 78
}

# =============================================================
#  STARTUP: CHECK INTERNET
#  This runs when server.py first starts.
#  If internet is found → download maps + herbs automatically.
#  If not → load from cache folder (already downloaded before).
# =============================================================

def check_internet():
    """Returns True if internet is available, False if not."""
    try:
        requests.get("https://8.8.8.8", timeout=3)
        return True
    except:
        return False


def download_herb_data():
    """
    Downloads the herb/medicine database from the internet
    and saves it to cache/herbs.json on disk.
    
    Person 3 should upload their herbs.json to a GitHub Gist
    and paste the raw URL here.
    """
    os.makedirs("cache", exist_ok=True)
    
    # PERSON 3: Replace this URL with your GitHub Gist raw URL
    # To get it: Go to gist.github.com → create new gist → paste herbs.json → 
    # click "Raw" → copy that URL and paste below
    HERBS_URL = "https://gist.githubusercontent.com/xxswaganimexx/e4eeab029e7dd5b6d3f9a53d96bddcfa/raw/5cb1f77860b5396b925b6d2b0046c6c3e2507941/herbs.json"
    
    try:
        response = requests.get(HERBS_URL, timeout=10)
        with open("cache/herbs.json", "w") as f:
            f.write(response.text)
        print("[✓] Herb database downloaded and cached")
    except Exception as e:
        print(f"[!] Could not download herbs: {e}")
        print("[!] Make sure cache/herbs.json exists manually")


def lat_lon_to_tile(lat, lon, zoom):
    """
    Converts a GPS coordinate to an OpenStreetMap tile number.
    You don't need to understand this math — it's a standard formula.
    """
    x = int((lon + 180) / 360 * 2**zoom)
    y = int((1 - math.log(
        math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))
    ) / math.pi) / 2 * 2**zoom)
    return x, y


def download_map_tiles():
    """
    Downloads map image tiles for the VIT-AP area from OpenStreetMap.
    Saves them to cache/tiles/ folder.
    
    radius=2 means it downloads a small area around the center point.
    zoom levels 13, 14, 15 = zoomed out to zoomed in views.
    
    Total download: ~8MB, takes about 20-30 seconds.
    """
    # VIT-AP University coordinates
    CENTER_LAT = 16.544
    CENTER_LON = 80.621
    ZOOM_LEVELS = [13, 14, 15]
    RADIUS = 2  # tiles in each direction from center

    os.makedirs("cache/tiles", exist_ok=True)
    headers = {"User-Agent": "CrisisComms/1.0 (hackathon project)"}

    total = 0
    for zoom in ZOOM_LEVELS:
        cx, cy = lat_lon_to_tile(CENTER_LAT, CENTER_LON, zoom)
        for x in range(cx - RADIUS, cx + RADIUS + 1):
            for y in range(cy - RADIUS, cy + RADIUS + 1):
                path = f"cache/tiles/{zoom}/{x}/{y}.png"
                os.makedirs(os.path.dirname(path), exist_ok=True)

                if os.path.exists(path):
                    continue  # already downloaded, skip

                url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
                try:
                    img = requests.get(url, headers=headers, timeout=10)
                    with open(path, "wb") as f:
                        f.write(img.content)
                    total += 1
                    time.sleep(0.1)  # be polite to OpenStreetMap servers
                except Exception as e:
                    print(f"[!] Could not download tile {zoom}/{x}/{y}: {e}")

    print(f"[✓] {total} map tiles downloaded and cached")


def startup_sync():
    """
    This runs once when the server starts and internet is available.
    Downloads everything needed to run fully offline later.
    """
    print("\n[BOOT] Internet detected — syncing data before going offline...")
    download_herb_data()
    download_map_tiles()
    print("[BOOT] Sync complete. Server is now offline-ready.\n")


# =============================================================
#  ROUTES / ENDPOINTS
#  These are the "doors" that phones knock on.
#  Each @app.route defines one door and what happens when used.
# =============================================================

# --- SERVE THE APP ---
@app.route("/")
def index():
    """
    When a phone opens http://YOUR_IP:5000 in their browser,
    this sends them the index.html file (your whole app).
    """
    return send_file("static/index.html")


# --- MAP TILES ---
@app.route("/tiles/<int:z>/<int:x>/<int:y>.png")
def serve_tile(z, x, y):
    """
    When Leaflet (the map library) needs a map image,
    it asks here. We serve it from our cached files on disk.
    This is what makes the map work offline.
    """
    path = f"cache/tiles/{z}/{x}/{y}.png"
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return "", 404


# --- MESSAGES (ALERTS) ---
@app.route("/messages", methods=["GET"])
def get_messages():
    """
    Phones call this every 2 seconds to check for new alerts.
    Returns the full list of all alerts posted so far.
    """
    return jsonify(messages)


@app.route("/messages", methods=["POST"])
def post_message():
    """
    When a survivor posts an alert, it comes here.
    We add it to the list. Next time any phone polls,
    they'll get this new alert.
    
    Expected data from phone:
    {
        "type": "critical",
        "zone": "C4",
        "resource": "Water",
        "msg": "Pipe burst here",
        "name": "RAVEN-7",
        "time": "14:47"
    }
    """
    data = request.json
    data["id"] = len(messages)  # give each message a unique ID
    messages.append(data)
    print(f"[ALERT] Zone {data.get('zone')} — {data.get('msg')[:50]}")
    return jsonify({"status": "ok", "id": data["id"]})


# --- RESOURCES ---
@app.route("/resources", methods=["GET"])
def get_resources():
    """hello
    Returns current water, food, medical levels.
    All phones show these same numbers.
    """
    return jsonify(resources)


@app.route("/resources", methods=["POST"])
def update_resources():
    """new
    When someone updates a resource level (e.g. water dropped to 20%),
    it comes here and we update the shared number.
    All phones will see the new level on their next poll.
    
    Expected data: { "water": 20 }  or  { "food": 45 }  etc.
    """
    data = request.json
    resources.update(data)
    print(f"[RESOURCE] Updated: {data}")
    return jsonify({"status": "ok", "resources": resources})


# --- SURVIVORS ---
@app.route("/survivors", methods=["GET"])
def get_survivors():
    """Returns the list of all survivors who have checked in."""
    return jsonify(survivors)


@app.route("/survivors", methods=["POST"])
def check_in():
    """
    When someone checks in their status, it comes here.
    If they already exist, update their status.
    If new, add them to the list.
    
    Expected data:
    {
        "name": "RAVEN-7",
        "status": "safe",   (safe / need / has)
        "zone": "A2"
    }
    """
    data = request.json
    name = data.get("name", "").upper()

    # Check if this person already checked in
    existing = next((s for s in survivors if s["name"] == name), None)
    if existing:
        existing["status"] = data.get("status")
        existing["zone"] = data.get("zone", existing["zone"])
        print(f"[CHECK-IN] Updated {name} → {data.get('status')}")
    else:
        survivors.append({
            "name": name,
            "status": data.get("status"),
            "zone": data.get("zone", "?")
        })
        print(f"[CHECK-IN] New survivor: {name} — {data.get('status')}")

    return jsonify({"status": "ok"})


# --- HERBS ---
@app.route("/herbs", methods=["GET"])
def get_herbs():
    """
    Returns the herb/medicine database from cache/herbs.json.
    This was downloaded on startup from the internet.
    Now works 100% offline.
    """
    try:
        with open("cache/herbs.json", "r") as f:
            herbs = json.load(f)
        return jsonify(herbs)
    except FileNotFoundError:
        return jsonify([])  # return empty list if file not found


# --- CHAOS EVENT (for demo) ---
@app.route("/chaos", methods=["POST"])
def chaos_event():
    """
    Triggered by the Chaos Event button.
    Randomly drops a resource level and posts a critical alert.
    This is your demo showstopper feature.
    """
    import random

    events = [
        {
            "resource": "water",
            "drop": 35,
            "zone": "C4",
            "msg": "Main pipe burst — water supply collapsing. Immediate action needed."
        },
        {
            "resource": "food",
            "drop": 40,
            "zone": "D3",
            "msg": "Food storage fire reported. Supply destroyed in sector."
        },
        {
            "resource": "medical",
            "drop": 45,
            "zone": "B2",
            "msg": "Medical supplies looted. Request emergency backup to Zone B2."
        },
    ]

    ev = random.choice(events)
    resources[ev["resource"]] = max(0, resources[ev["resource"]] - ev["drop"])

    # Auto-post a critical alert for this chaos event
    alert = {
        "type": "critical",
        "zone": ev["zone"],
        "resource": ev["resource"].capitalize(),
        "msg": ev["msg"],
        "name": "SYSTEM",
        "time": time.strftime("%H:%M"),
        "id": len(messages)
    }
    messages.append(alert)

    print(f"[⚡ CHAOS] {ev['msg']}")
    return jsonify({"status": "ok", "event": ev, "alert": alert})


# =============================================================
#  START THE SERVER
# =============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  CrisisComms Server — Apocalypse Protocol")
    print("=" * 50)

    # Check internet and sync data if available
    if check_internet():
        startup_sync()
    else:
        print("[BOOT] No internet — loading from cache only\n")

    # Find and print your laptop's local IP
    # This is what phones type into their browser
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"\n[READY] Server running!")
        print(f"[READY] Phones open: http://{local_ip}:5000")
        print(f"[READY] Your browser: http://localhost:5000\n")
    except:
        print("\n[READY] Server running at http://localhost:5000\n")

    # Start the server
    # host="0.0.0.0" means accept connections from ALL devices on network
    # port=5000 is the door number phones knock on
    # debug=False for stability during demo
    app.run(host="0.0.0.0", port=5000, debug=False)
