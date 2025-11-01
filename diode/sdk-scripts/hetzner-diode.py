import requests
from netboxlabs.diode.sdk import DiodeClient
from netboxlabs.diode.sdk.ingester import (
    Entity,
    VirtualMachine,
    VMInterface,
    Cluster,
    ClusterType,
    Platform,
    Site,
    Region,
    IPAddress,
)

# --- Diode API ---
DIODE_TARGET = "grpc://netbox.loe.internal:8080/diode"
DIODE_CLIENT_ID = "<secret>"
DIODE_CLIENT_SECRET = "<secret>"
APP_NAME = "hetzner-sync"
APP_VERSION = "0.1.0"

# --- Hetzner API ---
HETZNER_API_TOKEN = "<secret>"
HEADERS = {"Authorization": f"Bearer {HETZNER_API_TOKEN}"}
BASE_URL = "https://api.hetzner.cloud/v1"

HETZNER_STATUS_MAP = {
    "running": "active",
    "initializing": "planned",
    "starting": "planned",
    "stopping": "offline",
    "off": "offline",
    "deleting": "decommissioned",
    "migrating": "planned",
    "rebuilding": "planned",
    "unknown": "offline"
}


def get_json(path):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


servers = get_json("/servers").get("servers", [])


def build_entities():
    entities = []

    cluster_name = "hetzner"
    cluster_type_name = "cloud"

    cluster_type = ClusterType(name=cluster_type_name)
    cluster = Cluster(name=cluster_name, type=cluster_type)
    entities.append(Entity(cluster_type=cluster_type))
    entities.append(Entity(cluster=cluster))

    for srv in servers:
        region_name = srv.get("datacenter", {}).get("location", {}).get("network_zone", "unknown")
        region = Region(name=region_name)
        entities.append(Entity(region=region))

        dc = srv.get("datacenter", {}).get("location", {})
        loc_name = dc.get("name", "unknown")
        loc_desc = dc.get("description", "")
        site = Site(name=loc_desc, region=region.name, facility=loc_name, description="Hetzner")
        entities.append(Entity(site=site))

        platform_name = srv.get("image", {}).get("description", "")
        platform = None
        if platform_name != "":
            platform = Platform(name=platform_name)
            entities.append(Entity(platform=platform))

        vm_status = HETZNER_STATUS_MAP.get(srv.get("status", "unknown"), "offline")
        server_type = srv.get("server_type", {})

        vcpus = server_type.get("cores")
        memory = server_type.get("memory", 0) * 1024
        disk = server_type.get("disk", 0) * 1024

        vm = VirtualMachine(
            name=srv.get("name", "unknown"),
            status=vm_status,
            cluster=cluster,
            site=site.name,
            role="vps",
            platform=platform_name if platform_name else None,
            vcpus=vcpus,
            memory=memory,
            disk=disk,
            description=server_type.get("name", ""),
        )
        entities.append(Entity(virtual_machine=vm))

        interface = VMInterface(
            name="eth0",
            virtual_machine=vm,
            enabled=True,
        )
        entities.append(Entity(vm_interface=interface))

        fqdn = vm.name + ".loehndorf.me"
        ipv4 = IPAddress(
            address=srv.get("public_net", {}).get("ipv4", {}).get("ip"),
            site=site,
            dns_name=fqdn,
        )
        entities.append(Entity(ip_address=ipv4))

        ipv6 = IPAddress(
            address=srv.get("public_net", {}).get("ipv6", {}).get("ip").replace("::/64", "::1/64"),
            site=site,
            dns_name=fqdn,
        )
        entities.append(Entity(ip_address=ipv6))

    return entities


def sync_to_diode():
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
            print(f"✅ Synced {len(servers)} Hetzner servers to NetBox via Diode.")


if __name__ == "__main__":
    sync_to_diode()
