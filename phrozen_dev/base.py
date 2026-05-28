import json
import time

# prz version
# lancaigang240416:
# lancaigang240417:
# lancaigang240423:
# lancaigang240427: 24040
# lancaigang240428: 24040
# lancaigang240506: 24050
FW_VERSION = "25384"  # Vendor-managed firmware version stamp
HW_VERSION = "16"
IMAGE_VERSION = "16"
# DRIVER_CODE notes:
# When a Linux host controls multiple MCU boards running the same firmware,
# the protocol uses SN identifiers to distinguish each board.
# Format: V-H1-I1-F24045-SN1
# Format: V-H1-I1-F24045-SN2
# Format: V-H1-I1-F24045-SN3
# Format: V-H1-I1-F24045-SN4
# Format: V-H16-I16-F24045
# IMAGEID HWID FW_VERSION
# // AMS main board 1 firmware - 1 1 25164
# // AMS main board 2 firmware - 1 1 25164
# // AMS main board 3 firmware - 1 1 25164
# // AMS main board 4 firmware - 1 1 25164
# // Buffer board firmware - 6 6 25164 (reserved)
# // 16-color HUB board firmware - 7 7 25164
# // Leveling board firmware - 8 8 25164 (reserved)
# // TJC serial-screen foreground HMI firmware - 11 11 25164
# // ARCO300-MKS-RK3328 TJC serial-screen virtual app - 12 12 25164 (reserved)
# // ARCO300-MKS-RK3328 klipper-phrozen plugin - 16 16 25164
# // ARCO300-MKS-RK3328 OTA subprogram (AMS serial upgrader) - 5 5 25164
# // ARCO300-MKS-RK3328 TJC serial-screen backend - 10 10 25164
# //    Used as the phrozen_dev.zip image version for cloud-version comparison.
# // ARCO300-MKS-RK3328 OTA main program - 15 15 25164
# // DLP2K-YO2 sink machine STM32F401 Marlin - 17 17 25164
# // AMS outage-screen new mainboard STM32F103VET6 - 18 18 25164
# // 14K 13.5-inch SSD202 UI LVGL - 21 21 25164
# //    (SSD202 firmware on the in-house SSD202/FPGA/STM32F407 board)
# // 14K 13.5-inch Gowin FPGA - 22 22 25164
# //    (FPGA firmware on the in-house SSD202/FPGA/STM32F407 board)
# // 14K 13.5-inch STM32F4 MCU - 23 23 25164
# //    (STM32F407 firmware on the in-house SSD202/FPGA/STM32F407 board)
# // 14K 17-inch SSD202 UI LVGL - 24 24 25164
# // 14K 17-inch Gowin FPGA - 25 25 25164
# // 14K 17-inch STM32F4 MCU - 26 26 25164
# // 16KMax 13.5-inch SSD202 UI LVGL - 27 27 25164
# //    (SSD202 firmware on the in-house SSD202/FPGA/STM32F407 board)
# // 16KMax 13.5-inch Gowin FPGA - 28 28 25164
# // 16KMax 13.5-inch STM32F4 MCU - 29 29 25164
# // Smoke purifier - 30 30 25164
# // ARCO300-phrozen-RK3308 klipper-phrozen plugin - 31 31 25164
# // ARCO300-phrozen-RK3308 OTA subprogram (AMS serial upgrader) - 32 32 25164
# // ARCO300-phrozen-RK3308 TJC serial-screen backend - 33 33 25164
# //    Used as the phrozen_dev.zip image version for cloud-version comparison.
# // ARCO300-phrozen-RK3308 OTA main program - 34 34 25164
# // ARCO300-phrozen-RK3308 lower controller STM32F407VET6 - 35 35 25164
# // ARCO300-phrozen-RK3308 nozzle board STM32F103CBT6 - 36 36 25164
# // ARCO300-MKS-RK3328 lower controller STM32F407VET6 - 37 37 25164
# // ARCO300-MKS-RK3328 nozzle board STM32F103CBT6 - 38 38 25164
# // ARCO300-phrozen-RK3308 LVGL program KLIPPER - 39 39 25164
# //    Phrozen in-house LVGL UI controlling Klipper.

# =====DriveCodeFile.dat
# Data_ID 95 is used for version-report payloads
# 1 , 18 , 24053 , 18 , 0# // AMS board 1 firmware-18
# 2 , 18 , 24053 , 18 , 0# // AMS board 2 firmware-18
# 3 , 18 , 24053 , 18 , 0# // AMS board 3 firmware-18
# 4 , 18 , 24053 , 18 , 0# // AMS board 4 firmware-18
# 5 , 5 , 24046 , 5 , 0# // ARCO300-MKS-RK3328-STM32F407VET6-OTA sub-program - AMS serial upgrade-5 5
# 6 , 0 , 0 , 0 , 0# // buffer board firmware-6 6
# 7 , 7 , 24051 , 7 , 0# // 16-color HUB board firmware-7 7
# 8 , 0 , 0 , 0 , 0
# 9 , 0 , 0 , 0 , 0
# 10 , 10 , 24054 , 10 , 0# // ARCO300-MKS-RK3328-STM32F407VET6-OTA sub-program - TJC display background-10
# 11 , 11 , 24047 , 11 , 0# // TJC serial display HMI firmware-11
# 12 , 0 , 0 , 0 , 0
# 13 , 0 , 0 , 0 , 0
# 14 , 0 , 0 , 0 , 0
# 15 , 15 , 25042 , 15 , 0 # // ARCO300-MKS-RK3328-STM32F407VET6-OTA main program-15 15 25164
# 16 , 16 , 25042 , 16 , 0 # // ARCO300-MKS-RK3328-STM32F407VET6-klipper-phrozen plugin-16 16 25164
# 17 , ? , 25042 , ? , 0
# 18 , ? , 25042 , ? , 0
# 19 , ? , 25042 , ? , 0
# 20 , ? , 25042 , ? , 0


# Downlink example
# {"Cluster_ID":0,"Command":95,"Data":{}}
# Uplink example
# {
#     "Data_ID": 95,
#     "Data": {
#         "GwId": "000000000000",
#         "GwMac": "000000000000",
#         "GwIP": "169.254.17.112",
#         "Mask": 0,
#         "GwName": "Gateway-000000000000",
#         "StartTime": 1700683341,
#         "JoinMode": 1,
#         "RouteESSID": "",
#         "DNSServer": "",
#         "DriveCodeList": [
#             {
#                 "DriveCode": 16,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 15,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 14,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 13,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 12,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 11,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 10,
#                 "DriveImageType": 10,
#                 "DriveHwVersion": 10,
#                 "DriveFwVersion": 24045,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 9,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 8,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 7,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 6,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 5,
#                 "DriveImageType": 5,
#                 "DriveHwVersion": 5,
#                 "DriveFwVersion": 24046,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 4,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 3,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 2,
#                 "DriveImageType": 0,
#                 "DriveHwVersion": 0,
#                 "DriveFwVersion": 0,
#                 "DriveId": 0
#             },
#             {
#                 "DriveCode": 1,
#                 "DriveImageType": 1,
#                 "DriveHwVersion": 1,
#                 "DriveFwVersion": 24042,
#                 "DriveId": 0
#             }
#         ],
#         "ProductId": "ARCO",
#         "MainImage": 3,
#         "MainHWVersion": 3,
#         "MainFWVersion": 24041,
#         "Gw_Ram": 334560,
#         "Gw_Rom": 346508
#     }
# }
# Gateway passthrough serial bytes to node (forwarded to MCU for control/upgrade)
# {"DeviceAddr":"0000000000000000","Epoint":8,"Cluster_ID":64513,"Command":0,"SendMode":2,
# "Data":{"PassData":"B5C305D51669B239C6A52397937A40D3FE8319ABC503004B1200"}}

# /*
# STM32 <-> Linux SoC packet protocol summary
# UART: 115200bps, 1 start bit, 8 data bits, no parity, 1 stop bit
#
# 1) Header (2 bytes): 0xAAAA start flag
# 2) Data length (2 bytes): payload length after this field (includes CRC16)
# 3) Sequence ID (1 byte): anti-replay counter
# 4) Data type ID:
#    0x01 STM32 upgrade payload
#    0x02 Zigbee payload
#    0x03 App JSON payload
#    0x04 Modbus-RTU payload
# 5) Payload: type-specific data
# 6) CRC16 (2 bytes)
# */


# Vendor note (240509): 16-channel AMS models may use /dev/ttyUSB0 and /dev/ttyUSB1.
# Defaults
SERIAL_PORT1 = "/dev/ttyACM1"
SERIAL_PORT2 = "/dev/ttyACM2"
# Channel count
AMS_MAX_CHANNEL = 32
# Poll interval (seconds)
SERIAL_PORT_POLL_INTERVAL = 5.0
# USB serial baud rate
SERIAL_PORT_BAUD = 19200


#
AMS_WORK_MODE_UNKNOW = 0  # unknown mode; detection enabled
AMS_WORK_MODE_MC = 1  # multi-color mode
AMS_WORK_MODE_MA = 2  # refill mode
AMS_WORK_MODE_FILA_RUNOUT = 3  # single-color runout mode


# Vendor note (240115): default options
# Defaultsdevice
AMS_AUTO_CONNECT = False
# DefaultsAMS presence flag in [phrozen_dev]
AMS_ATTACHED = False
# Defaultsdebug command visibility in UI/command lists
AMS_ENABLE_DEBUG_COMMANDS = False
# DefaultsfilamentXcoordinates
AMS_FILA_CUT_X_POSITION = 313
# Vendor note (240325): tune Y coordinate
AMS_FILA_CUT_Y_POSITION = 307
# DefaultsfilamentZcoordinates 1.2
# Vendor note (240603): account for heated-bed conditions
AMS_FILA_CUT_Z_POSITION_LIFTING = 0.2
AMS_FILA_CUT_Z_POSITION_UP = 0.2
# DefaultsfilamentADC
AMS_TOOLHEAD_FILA_EXIST_ADC_VALUE = 0.3
# DefaultsfilamentADC
AMS_TOOLHEAD_FILA_EMPTY_ADC_VALUE = 0.5


# Speed (mm/min)
CHANGE_CHANNEL_WAIT_MAX_MOVEMENT_SPEED = 180
# Line width (mm)
CHANGE_CHANNEL_WAIT_LINE_WIDTH = 0.5
# lancaigang20231016：120
# Defaultstime(s)
# lancaigang240912：AMS，100
# lancaigang250111：90
# lancaigang250113：50
CHANGE_CHANNEL_WAIT_TIMEOUT = 80


# Z-axis movement control source
# 0 = execute default gcode path
CHANGE_CHANNEL_IF_Z_LIFTING_UP_BY_GCODE = 0


# ADC detection configuration
# Previous fast-sample settings kept for reference
# TOOLHEAD_ADC_REPORT_TIME = 0.015
# TOOLHEAD_ADC_DEBOUNCE_TIME = 0.025
# Vendor note (250409): relaxed ADC timing for stability
TOOLHEAD_ADC_REPORT_TIME = 0.50
TOOLHEAD_ADC_DEBOUNCE_TIME = 0.70
# ADC sample window
TOOLHEAD_ADC_SAMPLE_TIME = 0.100
# ADC sample count
TOOLHEAD_ADC_SAMPLE_COUNT = 4


AMS_MC_MODE = 0  # multi-color mode
AMS_MA_MODE = 1  #


MC_STANDBY = 0  # standby phase
MC_PREPARTION = 1  # phase
MC_CHANGING_P1 = 2  # filament change phase 1
MC_CHANGING_P2 = 3  # filament change phase 2
MC_FORCE_FEED = 4  # filament changephase
MC_PRINTING = 5  # phase
MC_ROLLBACK = 6  # full retract
MC_PARKBACK = 7  #
MC_PARKALL = 8  #
MC_CLEANING = 9  # clear all filaments
MC_ERR_TIMEOUT = 10  # timeout error state
MC_ERR_RUNOUT = 11  # runout error state
MC_ERR_BLOCKUP = 12  #


MA_STANDBY = 0  # standby phase
MA_FIND_WORK_CHAN = 1  #
MA_FAST_FEED = 2  #
MA_FORCE_FEED = 3  #
MA_PRINTING_FEED = 4  # phase
MA_MANUAL_ADD_FILA = 5  # filament
MA_AUTO_CHANGE_FILA = 6  # auto filament change
MA_ROLLBACK = 7  # full retract
MA_CLEANING = 8  # clear all filaments
MA_ERR_TIMEOUT = 9  # timeout error state


# lancaigang231104：13
# detectperiodtime(S)
# lancaigang230104：36
AMS_FILA_RUNOUT_TIMER = 2.0
# periodtime(S)
# lancaigang240104:0.2
# lancaigang240104:0.20.1
AMS_SERIALPORT_RECV_TIMER = 0.1  # 100ms
# lancaigang231104：815
# timecount(S)
RUNOUT_MAX_PAUSE_TIME_COUNT = 15

# CS 00 N0 M03 T04 C0
# //
# // CS device id  run mode  prev mc state  current mc state  channel
# // CS00       N0      M09         T09         C5
# // CS00       N0      M02         T03         C0
# // CS00       N0      M08         T10         C1
#    deviceid   mode    pre_state   state       chan
#
AMS_SERIALPORT_RECEIV_PARSE_PATTERN = (
    r"CS(?P<id>\d{2})N(?P<mode>\d{1})M(?P<pre_state>\d{2})T(?P<state>\d{2})C(?P<chan>\d{1})"
)


G_EmptyString = ""  #


# querydevice
G_DictPhrozenCmdP114 = {  # pythondictkey-value
    "cmd": "P114",  # websocket
    "params": [G_EmptyString],  # parameter
    "mcu_cmd": ["SD"],  # SD
    "desc": "Query AMS board sensor state",
}


# querydevice
G_DictPhrozenCmdP104 = {  # pythondictkey-value
    "cmd": "P104",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": ["SB"],  # pythonarraylist
    "desc": "Query AMS board basic state",
}


# device
G_DictPhrozenCmdP28 = {  # pythondictkey-value
    "cmd": "P28",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Connect AMS board",
}


# disconnect
G_DictPhrozenCmdP29 = {  # pythondictkey-value
    "cmd": "P29",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Disconnect AMS board",
}


# deviceID(device)
G_DictPhrozenCmdP30 = {  # pythondictkey-value
    "cmd": "P30",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": ["I"],  # array
    "desc": "Auto-assign device ID for multiple AMS boards",
}


# device
G_DictPhrozenP0 = {  # pythondictkey-value
    "cmd": "P0",
    "params": ["M", "B"],  # array
    "mcu_cmd": ["MC", "MA"],  # pythonarraylist
    "desc": "Set AMS board operating mode",
}


#
G_DictPhrozenCmdP2 = {  # pythondictkey-value
    "cmd": "P2",
    "params": ["A", "B"],  # array
    "mcu_cmd": ["AP", "CL"],  # pythonarraylist
    "desc": "AMS board filament retract commands",
}


# device
G_DictPhrozenCmdP4 = {  # pythondictkey-value
    "cmd": "P4",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": ["SP"],  # array
    "desc": "AMS board emergency stop",
}


# P1 T[n]n:1 ~32(device,1 ~4),()；====="T"；
# P1 B[n]n:1 ~32(device,1 ~4)exit Yes；====="B"；
# P1 D[n]；n:1~32(device,1~4)； Yes；====="P"；
# P1 C[n] n:1~32(device,1~4) (,, , )；====="T"；
# lancaigang231202:
# P1 E[n]；n:1~32(device,1~4)；，need Yes；====="E?"；
# lancaigang240228：distance，needstm32distance
# P1 G[n]；n:1~32(device,1~4)；distance Yes；====="G?"；
# lancaigang240319：phase，
# =====P1 H[n]；n:1~32(device,1~4)；phase， Yes；====="H?"；
# lancaigang240329：
# =====P1 I[n]；stm32need；====="I?"；
# =====P1 J[n]；；；
# =====P1 K[n]；
# =====P1 L[n]；
# =====P1 M[n]；
# =====P1 N[n]；
# =====P1 O[n]；
# =====P1 Q[n]；
# =====P1 U[n]；
# =====P1 V[n]；
# =====P1 W[n]；
# =====P1 X[n]；
# =====P1 Y[n]；
# =====P1 Z[n]；
# device
G_DictPhrozenCmdP1 = {  # pythondictkey-value
    "cmd": "P1",
    "params": [
        "S",
        "C",
        "T",
        "B",
        "D",
        "E",
        "G",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "Q",
        "U",
        "V",
        "W",
        "X",
        "Y",
        "Z",
    ],  # pythonarraylist
    "mcu_cmd": [
        "RD",
        "Tn",
        "Bn",
        "Pn",
        "En",
        "Gn",
        "In",
        "Jn",
        "Kn",
        "Ln",
        "Mn",
        "Nn",
        "On",
        "Qn",
        "Un",
        "Vn",
        "Wn",
        "Xn",
        "Yn",
        "Zn",
    ],  # pythonarraylist
    "desc": "AMS board channel command",
}


# waiting area
G_DictPhrozenCmdP9 = {  # pythondictkey-value
    # [Translated vendor note] P1 T[n]n:1 ~32(,1 ~4)channel,(); ====="T";
    # [Translated vendor note] P1 B[n]n:1 ~32(,1 ~4)channel Yes; ====="B";
    # [Translated vendor note] P1 D[n]; n:1~32(,1~4); channelpark position Yes; ====="P";
    # [Translated vendor note] P1 C[n] n:1~32(,1~4) channel(,, , ); ====="T";
    # Vendor note (231202):
    # [Translated vendor note] P1 E[n]; n:1~32(,1~4); channel, toolhead Yes; ====="E?";
    # [Translated vendor note] Vendor note (240228): toolhead, stm32
    # [Translated vendor note] P1 G[n]; n:1~32(,1~4); channel Yes; ====="G?";
    # [Translated vendor note] Vendor note (240319): , buffer
    # [Translated vendor note] =====P1 H[n]; n:1~32(,1~4); , buffer Yes; ====="H?";
    # [Translated vendor note] Vendor note (240329):
    # [Translated vendor note] =====P1 I[n]; stm32; ====="I?";
    # [Translated vendor note] =====P1 J[n]; purge; buffer;
    # =====P1 K[n];
    # =====P1 L[n];
    # =====P1 M[n];
    # =====P1 N[n];
    # =====P1 O[n];
    # =====P1 Q[n];
    # =====P1 U[n];
    # =====P1 V[n];
    # =====P1 W[n];
    # =====P1 X[n];
    # =====P1 Y[n];
    # =====P1 Z[n];
    # [Translated vendor note] mode
    "cmd": "P9",
    "params": ["X", "Y", "W", "H", "D", "T", "A"],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Filament change toolhead waiting area command",
}


# control
G_DictPhrozenCmdP10 = {  # pythondictkey-value
    "cmd": "P10",
    "params": ["S"],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Purge count control",
}


# execute
G_DictPhrozenCmdP8 = {  # pythondictkey-value
    "cmd": "P8",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": ["FA"],  # pythonarraylist
    "desc": "Auto refill command",
}

G_DictPhrozenCmdTn = {  # pythondictkey-value
    "cmd": "T",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Orca slicer color change",
}


# queryprintheadfilamentsensorADC
G_DictPhrozenCmdToolheadAdc = {  # pythondictkey-value
    "cmd": "PRZ_ADC",
    "params": [G_EmptyString],  # pythonarraylist
    "mcu_cmd": [G_EmptyString],  # pythonarraylist
    "desc": "Get toolhead filament ADC value",
}

# 1python ()，
#  1）create：tuple = (1,2,3) data tuple[0]......  tuple[0,2].....tuple[1,2]......
# 2)modify：modify
# 3） del tuple
# 4）function：
# cmp（tuple1，tuple2）：
# len(tuple):calculate
# max（tuple）：
# min（tuple）：
# tuple（seq）：list
# 2python []list，list
# 1）createlistl = [1,2,3,4]datal[0]........
# 2)listmodify
# 3）function
# cmp（list1，list2）：
# len(list):calculate
# max（list）：
# min（list）：
# list（seq）：list
# list.append(obj):listobject
# list.pop():data
# list.remove:list
# list.sort():
# list.reverse():list
# list.count(bj):calculateobjectlist
# list.insert(index,obj) :positionobject
# 3python {} dict；dict，
# 1）createdict：dict = {"a":1,"b":2}. dict：key， value datadict['a'],
# 2）modify
# 3）：del dict["a"] data  del dict dict dict.clear()dict
# 4）function
# cmp（dict1，dict2）：
# len(dict):calculate
# dict.clear():dictdata
# dict.get(key, default=None):return，ifreturndefault
# dict.has_key(key):check，returntrue，false
# dict.item（）listreturnreturn（，）
# dict.key（）returndictkey

# 1array
# Pythonarray， arr = [];can，arrarray，array，arrarray，
# arr = [ ‘’, ‘11’, ‘’]; arrarrayalready，arraycomplete，
# 2array
# arrayafter，needarray，arrarray arr[0]，，
# 0start，arr[2]array，arr[len(arr)-1] array，len(arr)array，
# 3array
# ，forlooparray，ifforloop，canskip，forloop，
# array
# 4array
# array，cancontinuearray，， append  insert，appendarray
# array，insert canposition， arr.insert(2,’’)，arr [ ‘’, ‘’, ‘
# ’,’’]array，，， arr.pop(2)array，2array
# (index)，can
# 5checkarray
# “””“”“， arr = [‘’, ‘’, ‘’]，Pythoncheck “”， “in” ，
#
# 6array
# ，price = [207,1400,50];Python，，，
#


class error(Exception):
    pass


class Base(object):
    # constructor initialization
    def __init__(self, config):
        if type(self) is Base:
            raise error("Base class cannot be instantiated")
        #
        self.G_AMSSerialCmdLock = False
        # defaultfilament
        self.G_ToolheadIfHaveFilaFlag = False

        #
        self.G_FilaRunoutTimmer = None

        #
        self.G_SerialPort1RecvTimmer = None
        #
        self.G_SerialPort2RecvTimmer = None

        # printer.cfgconfig
        self.G_PhrozenConfig = config
        self.G_PhrozenPrinter = config.get_printer()
        self.G_PhrozenReactor = self.G_PhrozenPrinter.get_reactor()
        #
        self.G_PhrozenPrinterCancelPauseResume = self.G_PhrozenPrinter.load_object(
            config, "pause_resume"
        )
        # gcode
        self.G_PhrozenGCode = self.G_PhrozenPrinter.lookup_object("gcode")
        # fluidd
        self.G_PhrozenFluiddRespondInfo = self.G_PhrozenGCode.respond_info

        # lancaigang241105:
        self.G_AMS1DeviceState = {}
        self.G_AMS2DeviceState = {}

        # usbttl
        self.G_Serialport1Define = self.G_PhrozenConfig.get("dev_port", SERIAL_PORT1)
        self.G_Serialport2Define = self.G_PhrozenConfig.get("dev_port2", SERIAL_PORT2)

        # printer.cfg;
        self.G_AMSIfAutoConnectFlag = self.G_PhrozenConfig.getboolean(
            "auto_connect", AMS_AUTO_CONNECT
        )

        # KAOS: AMS presence flag — read from [phrozen_dev] ams_attached option.
        # When False, AMS serial timers and command handlers no-op.
        self.G_AmsAttached = self.G_PhrozenConfig.getboolean("ams_attached", AMS_ATTACHED)

        # KAOS: debug command visibility flag — keeps test/service commands hidden by default.
        self.G_EnableDebugCommands = self.G_PhrozenConfig.getboolean(
            "enable_debug_commands", AMS_ENABLE_DEBUG_COMMANDS
        )

        # printer.cfg;defaultxposition
        self.G_AMSFilaCutXPosition = self.G_PhrozenConfig.getfloat(
            "fila_cut_x_pos", AMS_FILA_CUT_X_POSITION
        )
        # lancaigang240409：ycoordinates
        self.G_AMSFilaCutYPosition = self.G_PhrozenConfig.getfloat(
            "fila_cut_y_pos", AMS_FILA_CUT_Y_POSITION
        )
        # printer.cfg;defaultzposition
        self.G_AMSFilaCutZPositionLiftingUp = self.G_PhrozenConfig.getfloat(
            "fila_cut_x_pos_up", AMS_FILA_CUT_Z_POSITION_UP
        )

        # printer.cfg;defaultfilamentADC
        self.G_ToolheadFilaExistAdcValueDefault = self.G_PhrozenConfig.getfloat(
            "fila_exist_value", AMS_TOOLHEAD_FILA_EXIST_ADC_VALUE
        )
        # printer.cfg;defaultfilamentADC
        self.G_ToolheadFilaEmptyAdcValueDefault = self.G_PhrozenConfig.getfloat(
            "fila_empty_value", AMS_TOOLHEAD_FILA_EMPTY_ADC_VALUE
        )
        # printer.cfg;filamentADC；(exist+empty)/2
        self.G_ToolheadFilaAdcThresholdValue = (
            self.G_ToolheadFilaExistAdcValueDefault + self.G_ToolheadFilaEmptyAdcValueDefault
        ) / 2.0  # ADC

        # ：fila_sensor_pin: _THR:PA2
        # printer.cfg;ADCdetect
        self.G_ToolheadFilaSensorPin = self.G_PhrozenConfig.get("fila_sensor_pin", None)
        # ADC sample count
        Lo_ToolheadAdcPins = self.G_PhrozenPrinter.lookup_object("pins")
        # ：fila_sensor_pin: _THR:PA2
        self.G_ToolheadAdc = Lo_ToolheadAdcPins.setup_pin("adc", self.G_ToolheadFilaSensorPin)
        if hasattr(self.G_ToolheadAdc, 'setup_adc_sample'):
            import inspect
            try:
                adc_params = inspect.signature(
                    self.G_ToolheadAdc.setup_adc_sample
                ).parameters
                use_new_api = 'report_time' in adc_params
            except (ValueError, TypeError):
                use_new_api = False
            if use_new_api:
                # Klipper post-v0.13.0 (report_time merged into setup_adc_sample)
                self.G_ToolheadAdc.setup_adc_sample(
                    TOOLHEAD_ADC_REPORT_TIME,
                    sample_time=TOOLHEAD_ADC_SAMPLE_TIME,
                    sample_count=TOOLHEAD_ADC_SAMPLE_COUNT
                )
                self.G_ToolheadAdc.setup_adc_callback(
                    self.Base_ToolheadAdcCallback
                )
            else:
                # Klipper v0.13.0 (setup_minmax renamed to setup_adc_sample)
                self.G_ToolheadAdc.setup_adc_sample(
                    TOOLHEAD_ADC_SAMPLE_TIME, TOOLHEAD_ADC_SAMPLE_COUNT
                )
                self.G_ToolheadAdc.setup_adc_callback(
                    TOOLHEAD_ADC_REPORT_TIME, self.Base_ToolheadAdcCallback
                )
        else:
            # Klipper <= v0.12 (pinned builds)
            self.G_ToolheadAdc.setup_minmax(
                TOOLHEAD_ADC_SAMPLE_TIME, TOOLHEAD_ADC_SAMPLE_COUNT
            )
            self.G_ToolheadAdc.setup_adc_callback(
                TOOLHEAD_ADC_REPORT_TIME, self.Base_ToolheadAdcCallback
            )
        Lo_ToolheadQueryAdc = self.G_PhrozenPrinter.lookup_object("query_adc")
        Lo_ToolheadQueryAdc.register_adc("prz_adc", self.G_ToolheadAdc)

        # printer.cfg;speed
        self.G_ChangeChannelWaitMaxMovementSpeed = self.G_PhrozenConfig.getint(
            "wait_max_velocity", CHANGE_CHANNEL_WAIT_MAX_MOVEMENT_SPEED
        )
        # printer.cfg;
        self.G_ChangeChannelWaitLineWidth = self.G_PhrozenConfig.getfloat(
            "wait_line_width", CHANGE_CHANNEL_WAIT_LINE_WIDTH
        )
        # printer.cfg;time，printer.cfgdefaulttime
        self.G_ChangeChannelTimeout = self.G_PhrozenConfig.getint(
            "wait_timeout", CHANGE_CHANNEL_WAIT_TIMEOUT
        )
        # printer.cfg;gcodez
        self.G_ChangeChannelIfZLiftingUpByGcode = self.G_PhrozenConfig.getint(
            "switch_fila_zup_by_gcode", CHANGE_CHANNEL_IF_Z_LIFTING_UP_BY_GCODE
        )

        # lancaigang231207：during filament change, if feed jams, remove from toolhead tube, do not retract
        self.G_IfInFilaBlockFlag = False

        # lancaigang231207：stm32data
        self.G_SerialRxASCIIStr = None

        # lancaigang231207：filament change
        self.G_IfChangeFilaOngoing = False

        # lancaigang231215：stm32，count
        self.G_STM32PauseCount = 0

        # lancaigang231212：flag，if，detectfilament，
        self.G_IfToolheadHaveFilaInitiativePauseFlag = False

        # lancaigang240108：flag，complete
        self.G_M2MAModeResumeFlag = False

        # lancaigang240108：
        self.P0M3FilaRunoutSpittingFinished = True  # completeflag

        # lancaigang240113：T?smt32
        self.ManualCmdFlag = False

        # lancaigang240123：MA
        self.AMSRunoutPauseTimeCount = 0
        self.AMSRunoutPauseTimeoutFlag = 0

        # lancaigang240124：stm32，1
        self.STM32ReprotPauseFlag = 0

        # lancaigang240223：failed
        self.ToolheadCutFlag = False

        # lancaigang240229：PG101
        self.IfDoPG102Flag = False

        # lancaigang240320：PG102
        self.PG102Flag = False

        # lancaigang240320：PG102
        self.PG102DelayPauseFlag = False

        # lancaigang240325：MCcanlabel
        self.G_MCModeCanResumeFlag = False

        # lancaigang240325：channel number
        self.G_Pause1Channel = -1
        # lancaigang240325：
        self.G_PauseTriggerWhileChangeChannelFlag = False

        # lancaigang240325：
        self.G_ResumeProcessCheckPauseStatus = False

        # lancaigang240325：
        self.G_PauseToLCDString = ""

        # lancaigang240410：
        self.G_CancelFlag = False

        # lancaigang240411：if no P0 M3 command received, skip runout detection
        self.G_P0M3Flag = False

        # lancaigang240412:AMSlabel
        self.G_AMSDevice1IfNormal = False

        # lancaigang241029:AMSlabel
        self.G_AMSDevice2IfNormal = False

        # lancaigang240415：filament，
        self.G_P0M3ToolheadHaveFilaNotSpittingFlag = False

        # lancaigang240427：AMS error restart, needs logging
        self.G_AMS1ErrorRestartFlag = False
        self.G_AMS1ErrorRestartCount = 0
        # lancaigang240521：on resume: if AMS restart detected (hot-plug), execute full retract/change
        self.G_ResumeCheckAMS1ErrorRestartFlag = False

        # lancaigang241030:
        self.G_AMS2ErrorRestartFlag = False
        self.G_AMS2ErrorRestartCount = 0
        self.G_ResumeCheckAMS2ErrorRestartFlag = False

        # lancaigang240528：P114label
        self.G_P114RunFlag = 0

        # lancaigang241101：control
        self.G_P10SpitNum = 0

        # lancaigang241106：MAflag
        self.G_P0M2MAStartPrintFlag = 0

        # lancaigang250102：filament changecalculate
        self.G_PrintCountNum = 0

        # lancaigang250104：P2A3flag
        self.G_P2A3Flag = 0

        # lancaigang250514：parseconfigdata
        self.G_P0M1MCNoneAMS = -1

        self.G_AutoReplaceState = -1
        self.G_ChromaKitNum = -1
        self.G_ChromaKitAccessT0 = -1
        self.G_ChromaKitAccessT1 = -1
        self.G_ChromaKitAccessT2 = -1
        self.G_ChromaKitAccessT3 = -1
        self.G_ChromaKitAccessT4 = -1
        self.G_ChromaKitAccessT5 = -1
        self.G_ChromaKitAccessT6 = -1
        self.G_ChromaKitAccessT7 = -1
        self.G_ChromaKitAccessT8 = -1
        self.G_ChromaKitAccessT9 = -1
        self.G_ChromaKitAccessT10 = -1
        self.G_ChromaKitAccessT11 = -1
        self.G_ChromaKitAccessT12 = -1
        self.G_ChromaKitAccessT13 = -1
        self.G_ChromaKitAccessT14 = -1
        self.G_ChromaKitAccessT15 = -1

        # lancaigang250526：，allowgcode，complete
        self.G_KlipperInPausing = False

        # lancaigang250527：execute
        self.G_KlipperQuickPause = False

        # lancaigang250607：print status: 1=retracting; 2=feeding; 3=printing; 4=paused
        self.G_KlipperPrintStatus = -1

        # lancaigang250619：
        self.G_PauseToUSBConnectString = ""

        # lancaigang250724:image id
        self.G_ImageId = -1
        self.G_HwId = -1

        # lancaigang250805:
        self.G_CutCheckTest = False

        # lancaigang250812:single-color runout detection, return to pause zone
        self.G_RetryToPauseAreaFlag = False
        self.G_RetryToPauseAreaCount = 0

        # lancaigang251120：PG108executeflag；
        self.G_PG108Ingoing = 0

    # ─── HMI/AMS Protocol Emitters ─────────────────────────────────────
    # Typed helpers for wire protocol messages consumed by the touchscreen
    # and AMS subsystems. These call Klipper's respond_info directly,
    # bypassing any logging filter on G_PhrozenFluiddRespondInfo.

    def emit_protocol(self, msg):
        """Emit a raw protocol string to the console bus (bypass filters)."""
        self.G_PhrozenGCode.respond_info(msg)

    def emit_pause(self, reason, *args):
        """Emit +PAUSE: protocol message.
        Usage: emit_pause("b", old_chan, new_chan)
               emit_pause(1, sub_code)
        """
        if args:
            self.G_PhrozenGCode.respond_info(
                "+PAUSE:%s,%s" % (reason, ",".join(str(a) for a in args))
            )
        else:
            self.G_PhrozenGCode.respond_info("+PAUSE:%s" % reason)

    def emit_resume(self, reason, chan):
        """Emit +RESUME: protocol message."""
        self.G_PhrozenGCode.respond_info("+RESUME:%d,%d" % (reason, chan))

    def emit_mode(self, code, name):
        """Emit +Mode: protocol message."""
        self.G_PhrozenGCode.respond_info("+Mode:%d,%s" % (code, name))

    def emit_p114(self, status):
        """Emit +P114: AMS state protocol message."""
        self.G_PhrozenGCode.respond_info("+P114:%d" % status)

    # Valid AMS channel operations for emit_channel_op:
    #   E     = Force forward (extrude filament into nozzle)
    #   G     = Retract from hotend
    #   H     = Special refill state
    #   J     = Manual spit filament
    #   I     = Manual extrude control
    #   B     = Full rollback (complete retract to hub)
    #   D     = Move to park position
    #   Cut   = Filament cut (toolhead traverses to cutter)
    #   Zero  = Home/reset axes (G28)
    #   P1END = End-of-sequence marker (phase 0 only)
    _VALID_CHANNEL_OPS = frozenset(
        (
            "E",
            "G",
            "H",
            "J",
            "I",
            "B",
            "D",
            "Cut",
            "Zero",
            "P1END",
        )
    )

    def emit_channel_op(self, op, phase, chan):
        """Emit channel operation phase message (+E:, +G:, +H:, etc.).
        op: one of _VALID_CHANNEL_OPS
        phase: 0=start, 1=complete
        """
        if op not in self._VALID_CHANNEL_OPS:
            self.kaos_log("WARN", "emit_channel_op: unknown op '%s'" % op, "SERIAL")
            return
        self.G_PhrozenGCode.respond_info("+%s:%d,%d" % (op, phase, chan))

    def emit_ams_state(self, state_dict):
        """Emit AMS state JSON to console bus."""
        self.G_PhrozenGCode.respond_info(json.dumps(state_dict))

    #
    def Base_AMSSerialCmdLock(self):
        self.kaos_log("DEBUG", "[(base.python)Base_AMSSerialCmdLock]", "SERIAL")
        for _ in range(8):
            if self.G_AMSSerialCmdLock == False:
                #
                # lock
                self.G_AMSSerialCmdLock = True
                return True
            # 0.2sloop
            time.sleep(0.2)
        return False

    #
    def Base_AMSSerialCmdUnlock(self):
        self.kaos_log("DEBUG", "[(base.python)Base_AMSSerialCmdUnlock]", "SERIAL")
        # unlock
        self.G_AMSSerialCmdLock = False

    # period,
    def Device_TimmerUart1Recv(self, eventtime):
        self.kaos_log(
            "DEBUG", "[(base.python)Device_TimmerUart1Recv]Serial port 1 receive thread", "SERIAL"
        )
        pass

    def Device_TimmerUart2Recv(self, eventtime):
        self.kaos_log(
            "DEBUG", "[(base.python)Device_TimmerUart2Recv]Serial port 2 receive thread", "SERIAL"
        )
        pass

    # detectfilamentADC；mscallback
    # 250ms
    def Base_ToolheadAdcCallback(self, read_time, read_value):
        # self.G_PhrozenFluiddRespondInfo("[(base.python)Base_ToolheadAdcCallback]")
        _ = read_time
        # filament，ADCfilament
        # lancaigang231213：(+)/2
        self.G_ToolheadIfHaveFilaFlag = read_value < self.G_ToolheadFilaAdcThresholdValue
        # self.G_PhrozenFluiddRespondInfo("[(base.python)Base_ToolheadAdcCallback]self.G_ToolheadIfHaveFilaFlag=%d" % (self.G_ToolheadIfHaveFilaFlag))
        # print(read_value)
        # print(self.G_ToolheadFilaAdcThresholdValue)
