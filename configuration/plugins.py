# Add your plugins and plugin settings here.
# Of course uncomment this file out.

# To learn how to build images with your required plugins
# See https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins

PLUGINS = [
        "netbox_qrcode",
        "netbox_topology_views",
        "netbox_lifecycle",
        "netbox_reorder_rack",
        "netbox_interface_synchronization",
        "netbox_floorplan",
        "netbox_diode_plugin",
]

PLUGINS_CONFIG = {
  "netbox_diode_plugin": {
      "diode_target_override": "grpc://netbox-diode-01:8080/diode",
      "diode_username": "diode",
      "netbox_to_diode_client_secret": "Ps9oN26BhxeLBkT4JtTyfbnaUh4QbyycSyfqEuW6BAo="
  },
  "netbox_topology_views": {"allow_coordinates_saving": True},
  "netbox_qrcode": {
      "rack": {
          "label_height": "24mm",
          "label_width": "95mm",
          "label_edge_left": "2mm",
          "label_edge_right": "2mm",
          "label_qr_height": "18mm",
          "label_qr_width": "18mm",
          "label_qr_text_distance": "5mm",
          "text_align_horizontal": "center",
          "font_size": "12.0mm",
          "font_weight": "bold",
      },
      "device": {
          "with_qr": True,
              "label_height": "12mm",
              "with_text": False,
              "label_edge_top": "0mm",
          "label_edge_left": "0mm",
          "label_edge_right": "0mm",
              "label_qr_width": "10mm",
          "label_qr_height": "10mm",
              "label_width": "12mm",
          },
      "powerfeed": {
          "with_qr": False,
          "label_height": "24mm",
          "label_width": "95mm",
          "text_align_horizontal": "center",
          "font_size": "12.0mm",
          "font_weight": "bold",
      },
      'cable': {
          'title': 'Cable Barcode',
          'with_qr': False,
          'label_edge_left': '0.00mm',
          'label_edge_right': '0.00mm',
          'label_edge_top': '0.00mm',
          'text_align_vertical': 'middle',
          'text_align_horizontal': 'center',

          # QR-Code Image File
          'qr_version': 1,
          'qr_error_correction': 1,
          'qr_box_size': 2,
          'qr_border': 0,

          'text_template': '<svg id="barcode"></svg>'
                             '<svg id="barcode"></svg>'
                             '<svg id="barcode"></svg>'
                             '<svg id="barcode"></svg>'
                             ''
                             '<style>'
                             '   #barcode {'
                             '   max-width: 48mm;'
                             '   width: 100%;'
                             '   max-height: 6mm;'
                             '   height: 100%;'
                             '   }'
                             '</style>'
                             ''
                             '<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.0/dist/JsBarcode.all.min.js"></script>'
                             ''
                             '<script>'
                             '   JsBarcode("#barcode", "{{ obj.id }}", {'
                             '   background: "transparent",'
                             '   format: "CODE128",'
                             '   displayValue: true,'
                             '   margin: 0,'
                             '   height: 15'
                             '   });'
                             '</script>'
      },
  },
}
