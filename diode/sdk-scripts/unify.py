import requests
from netboxlabs.diode.sdk import DiodeClient
from netboxlabs.diode.sdk.ingester import (
    Entity,
    Device,
    Interface,
    IPAddress,
    DeviceType,
    Manufacturer,
    Site,
)

# --- Configuration ---
UNIFI_URL = "https://udm.loe.internal"
UNIFI_API_KEY = "<secret>"
UNIFI_SITE_ID = "<secret>"

DIODE_TARGET = "grpc://netbox.loe.internal:8080/diode"
DIODE_CLIENT_ID = "<secret>"
DIODE_CLIENT_SECRET = "<secret>"
APP_NAME = "unifi-sync"
APP_VERSION = "0.1.0"

VERIFY_SSL = False  # for UniFi requests

# --- UniFi API helper ---
headers = {"X-API-Key": UNIFI_API_KEY}
base = f"{UNIFI_URL}/proxy/network/integration/v1/sites/{UNIFI_SITE_ID}"

def get_json(url):
    r = requests.get(url, headers=headers, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json()

# --- Resolve Site Name ---
sites_resp = get_json(f"{UNIFI_URL}/proxy/network/integration/v1/sites")
site_name = None
for s in sites_resp.get("data", []):
    if s.get("id") == UNIFI_SITE_ID:
        site_name = s.get("name")
        break

if not site_name:
    raise RuntimeError(f"Could not find site name for site ID '{UNIFI_SITE_ID}'")

print(f"📍 Found UniFi site name: {site_name}")

# --- Fetch devices ---
device_list = get_json(f"{base}/devices").get("data", [])

# Map speed/connector to interface type
def get_iface_type(connector, max_speed):
    # RJ45 speeds
    speed_map = {
        100: "100base-tx",
        1000: "1000base-t",
        2500: "2.5gbase-t",
        5000: "5gbase-t",
        10000: "10gbase-t"
    }

    connector = connector.upper()
    if connector.startswith("SFP"):
        speed_map = {
            1000: "SFP",
            10000: "SFP+",
            25000: "SFP28",
            40000: "QSFP+",
            100000: "QSFP28",
        }

    for threshold in sorted(speed_map.keys(), reverse=True):
        if max_speed >= threshold:
            return speed_map[threshold]

    # Fallback
    return "100base-tx"

def build_entities():
    entities = []
    for dev in device_list:
        dev_id = dev["id"]
        dev_name = dev.get("name") or dev["macAddress"]
        model = dev.get("model", "Unknown")
        ip_addr = dev.get("ipAddress")

        # Determine device role
        model_upper = model.upper()
        if model_upper.startswith("UDM"):
            role = "firewall"
        elif model_upper.startswith("USW"):
            role = "switch"
        elif model_upper.startswith("U") and len(model_upper) > 1 and model_upper[1].isdigit():
            role = "accesspoint"
        else:
            role = "network"


        # Fetch full device detail
        dev_detail = get_json(f"{base}/devices/{dev_id}")

        # --- Build base entities ---
        manufacturer = Manufacturer(name="Ubiquiti")
        site = Site(name=site_name)

        dtype = DeviceType(
            model=model,
            manufacturer=manufacturer.name,
        )

        device_ent = Device(
            name=dev_name,
            device_type=dtype.model,
            manufacturer=manufacturer.name,
            site=site.name,
            role=role,
            status="active",
        )

        entities += [Entity(manufacturer=manufacturer), Entity(device_type=dtype),
                     Entity(site=site), Entity(device=device_ent)]
        
        # --- DeviceType Interfaces & Module Bay Templates ---
        ports = dev_detail.get("interfaces", {}).get("ports", [])
        for port in ports:
            idx = port.get("idx")
            connector = port.get("connector", "RJ45")
            max_speed = port.get("maxSpeedMbps", 1000)
            current_speed = port.get("speedMbps", 0)
            state = port.get("state", "DOWN")

            if connector == "RJ45":
                iface_type = get_iface_type(connector, max_speed)

                iface_ent = Interface(
                    device=device_ent.name,
                    device_type=dtype.model,
                    name=f"0/{idx}",
                    type=iface_type,
                    speed=current_speed,
                    site=site.name,
                    enabled=(state == "UP")
                )
                entities.append(Entity(interface=iface_ent))
        
        iface_mgmt = Interface(
            device=device_ent.name,
            name="mgmt0",
            type="virtual",
            site=site.name,
            mgmt_only=True,
        )
        entities.append(Entity(interface=iface_ent))

        # --- Management IP ---
        if ip_addr:
            mgmgt_ip = IPAddress(address=f"{ip_addr}/32", device=device_ent.name, dns_name=device_ent.name+".loe.internal")
            entities.append(Entity(ip_address=mgmgt_ip))

    return entities


def sync_to_diode():
    # Authenticated Diode client
    with DiodeClient(
        target=DIODE_TARGET,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        client_id=DIODE_CLIENT_ID,
        client_secret=DIODE_CLIENT_SECRET,
    ) as client:
        entities = build_entities()

        response = client.ingest(entities=entities)
        if response.errors:
            print("Errors during ingestion:")
            for e in response.errors:
                print("  -", e)
        else:
            print("All UniFi devices synced to NetBox via Diode.")


if __name__ == "__main__":
    sync_to_diode()