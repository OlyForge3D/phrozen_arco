
import usb.util
import usb.core


ID_VENDOR = 0x1993
ID_PRODUCT = 0x2021

# transfer interfaces
INTF_BULK = 0
INTF_INTR = 1
INTF_ISO = 2

# endpoints address
EP_BULK = 1
EP_INTR = 2
EP_ISO = 3

# test type
TEST_NONE = 0
TEST_PCREAD = 1
TEST_PCWRITE = 2
TEST_LOOP = 3

# Vendor requests
PICFW_SET_TEST = 0x0e
PICFW_SET_TEST = 0x0f
PICFW_SET_VENDOR_BUFFER = 0x10
PICFW_GET_VENDOR_BUFFER = 0x11

#hid_dev=Init_usb_hid_device(0x1993,0x2021)
devices = usb.core.find(find_all=True)
#devices=usb.core.find(idVendor=0x1993, idProduct=0x2021)
for device in devices:
	if device.idVendor==0x1993:
		print("Vendor ID: 0x{:04x}".format(device.idVendor))
		print("Product ID: 0x{:04x}".format(device.idProduct))
		print("Manufacturer: {}".format(usb.util.get_string(device, device.iManufacturer)))
		print("Product: {}".format(usb.util.get_string(device, device.iProduct)))
		print("-------------------------------------------")