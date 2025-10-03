# Add your plugins and plugin settings here.
# Of course uncomment this file out.

# To learn how to build images with your required plugins
# See https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins

PLUGINS = [
        "netbox_qrcode",
        "netbox_topology_views",
        "netbox_lifecycle",
        "netbox_reorder_rack",
        "netbox_floorplan",
        "netbox_interface_synchronization",
        "netbox_diode_plugin",
]

PLUGINS_CONFIG = {
   "netbox_topology_views": {
     "allow_coordinates_saving": True
   }
 }

