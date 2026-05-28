import binascii
import logging
import time
import struct
import serial
import re

from .cwebsocketapis import *

from .kaos_logging import install_kaos_logging
from . import phrozen_sdcard_ext


class PhrozenDev(Apis):
    # constructor initialization
    def __init__(self, config):
        super(PhrozenDev, self).__init__(config)
        # KAOS: install external logging/filter/translation shim.
        # Keeps vendor dev.py mostly stock and preserves Arco protocol/status output.
        install_kaos_logging(self)
        # register connect event for klipper
        self.G_PhrozenPrinter.register_event_handler(
            "klippy:connect", self.Device_KlipperConnectHandle
        )
        # register disconnect event for klipper
        self.G_PhrozenPrinter.register_event_handler(
            "klippy:disconnect", self.Device_KlipperDisconnectHandle
        )

        # dev.py;reset AMS runtime parameters
        self.Device_ResetParams()

        # cmds.py;Phrozen custom G-code commands
        self.Cmds_RegisterCmds()

        # cwebsocketapis.py;web WebSocket API
        self.WebsocketAPIs_RegisterAPIs()

        # Patch virtual_sdcard with touchscreen subdirectory browsing
        phrozen_sdcard_ext.install(self.G_PhrozenPrinter)

        # dev.py;test command PRZ_TEST
        if self.G_EnableDebugCommands:
            self.G_PhrozenGCode.register_command(
                "PRZ_TEST", self.Device_CmdPhrozenTest, desc="Phrozen AMS unit test command"
            )

    # AMS reset parameters
    def Device_ResetParams(self):
        self.kaos_log(
            "DEBUG", "[(dev.python)Device_ResetParams]Reset AMS runtime parameters", "SERIAL"
        )
        self.G_FilaRunoutTimmer = None  #
        self.G_SerialPort1RecvTimmer = None  #
        self.G_SerialPort2RecvTimmer = None  #

        self.AMSRunoutPauseTimeCount = 0  # timecount
        self.G_ToolheadFirstInputFila = False  #
        self.P0M3FilaRunoutSpittingFinished = False
        self.AMSErrorRetryTimes = 0  #
        # AMS multi-material status
        self.G_AMS1DeviceState = {}
        self.G_AMS2DeviceState = {}

    # register periodic disconnect timer thread
    def Device_RegisterRunoutErrorThread(self):
        self.kaos_log("DEBUG", "[(dev.python)Device_RegisterRunoutErrorThread]", "SERIAL")
        # register disconnect handler periodic thread
        self.G_FilaRunoutTimmer = self.G_PhrozenReactor.register_timer(
            self.Device_TimmerRunoutCheck, self.G_PhrozenReactor.NOW + 0.5
        )

    def Device_UnregisterDaemonThread(self):
        self.kaos_log("DEBUG", "[(dev.python)Device_UnregisterDaemonThread]", "SERIAL")
        # unregister
        self.G_PhrozenReactor.unregister_timer(self.G_FilaRunoutTimmer)
        # self.G_PhrozenReactor.unregister_timer(self.G_SerialPort1RecvTimmer)

    def Device_ConnectAMSDevice(self):
        self.kaos_log(
            "DEBUG",
            "[(dev.python)Device_ConnectAMSDevice]Phrozen extension module connecting to the AMS multi-material unit",
            "SERIAL",
        )
        # auto-connect AMS multi-material unit
        # Vendor note (240116): do not auto-connect AMS
        # if self.G_AMSIfAutoConnectFlag:
        # ttyUSB0 serial connect AMS multi-material unit
        # self.Cmds_CmdP28(None)
        # # Vendor note (231122): ttyUSB0before,needIAPhdl_zigbee_gateway

    def Device_DisconnectAMSDevice(self):
        self.kaos_log(
            "DEBUG",
            "[(dev.python)Device_DisconnectAMSDevice]Phrozen extension module disconnecting from the AMS multi-material unit",
            "SERIAL",
        )
        self.Cmds_CmdP29(None)

    def Device_CmdPhrozenTest(self, gcmd):
        self.kaos_log(
            "DEBUG",
            "[(dev.python)Device_CmdPhrozenTest]PRZ_TEST command='%s'" % (gcmd.get_commandline(),),
            "SERIAL",
        )
        self.kaos_log("DEBUG", "self.prz_test command='%s'" % (gcmd.get_commandline(),), "SERIAL")
        # klipper pause
        self.Cmds_PhrozenKlipperPause(None)

    # initial event registration; phrozen plugin connect klipper
    def Device_KlipperConnectHandle(self):
        self.kaos_log(
            "DEBUG",
            "[(dev.python)Device_KlipperConnectHandle]Phrozen extension module connected to Klipper",
            "SERIAL",
        )

        # Vendor note (250724): read system image id to distinguish product/board/firmware variants
        # Vendor note (250724): read image id
        self.Cmds_GetImageId()
        if self.G_ImageId == 16:
            self.kaos_log("DEBUG", "Image ID==16: ARCO300-MKS-RK3328-STM32F407VET6-I16", "SERIAL")
            os.system("sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &")
            self.kaos_log(
                "DEBUG", "sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &", "SERIAL"
            )
        elif self.G_ImageId == 31:
            self.kaos_log(
                "DEBUG", "Image ID==31: ARCO300-phrozen-RK3308-STM32F407VET6-I31", "SERIAL"
            )
            os.system("sh /home/prz/klipper/klippy/extras/phrozen_dev/stop.sh &")
            self.kaos_log(
                "DEBUG", "sh /home/prz/klipper/klippy/extras/phrozen_dev/stop.sh &", "SERIAL"
            )
        elif self.G_ImageId == -1:
            self.kaos_log(
                "DEBUG", "Image ID==-1, default: ARCO300-MKS-RK3328-STM32F407VET6-I16", "SERIAL"
            )
            os.system("sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &")
            self.kaos_log(
                "DEBUG", "sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &", "SERIAL"
            )
        else:
            self.kaos_log(
                "DEBUG",
                "Image ID could not be read, default: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                "SERIAL",
            )
            os.system("sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &")
            self.kaos_log(
                "DEBUG", "sh /home/mks/klipper/klippy/extras/phrozen_dev/stop.sh &", "SERIAL"
            )

        # get toolhead action
        self.G_ProzenToolhead = self.G_PhrozenPrinter.lookup_object("toolhead")
        # toolhead manual move
        self.G_ToolheadManualMovement = self.G_ProzenToolhead.manual_move
        # toolhead wait move end
        self.G_ToolheadWaitMovementEnd = self.G_ProzenToolhead.wait_moves
        # toolhead last position
        self.G_ToolheadLastPosition = self.G_ProzenToolhead.get_position()
        # register periodic disconnect thread
        self.Device_RegisterRunoutErrorThread()

        # Vendor note (240430): power-loss resume: if AMS state saved, do not overwrite after restart
        # if klipper reconnects, tell AMS enter idle state
        try:
            # open serial port 1, baud 19200
            self.G_SerialPort1Obj = serial.Serial(
                self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3
            )
            if self.G_SerialPort1Obj.is_open:
                # Vendor note (231213): open serial port
                self.G_SerialPort1Obj.flushInput()
                self.G_SerialPort1Obj.flush()
                # Vendor note (250115): multi-material power-loss resume
                self.kaos_log("DEBUG", "Sending command: M0", "SERIAL")
                self.G_SerialPort1Obj.write("M0".encode())
                self.G_SerialPort1Obj.flush()
                # close serial port, prevent subsequent P28 errors
                self.G_SerialPort1Obj.close()
        except:
            self.kaos_log(
                "DEBUG", "Unable to open tty1. Check the USB connection or try rebooting.", "SERIAL"
            )

        try:
            # open serial port 2, baud 19200
            self.G_SerialPort2Obj = serial.Serial(
                self.G_Serialport2Define, SERIAL_PORT_BAUD, timeout=3
            )
            if self.G_SerialPort2Obj.is_open:
                self.G_SerialPort2Obj.flushInput()
                self.G_SerialPort2Obj.flush()
                self.kaos_log("DEBUG", "Sending command: M0", "SERIAL")
                self.G_SerialPort2Obj.write("M0".encode())
                self.G_SerialPort2Obj.flush()
                # close serial port, prevent subsequent P28 errors
                self.G_SerialPort2Obj.close()
        except:
            self.kaos_log(
                "DEBUG", "Unable to open tty2. Check the USB connection or try rebooting.", "SERIAL"
            )

        # Vendor note (240427): AMS error restart, needs logging
        self.G_AMS1ErrorRestartFlag = False
        self.G_AMS1ErrorRestartCount = 0

        self.G_AMS2ErrorRestartFlag = False
        self.G_AMS2ErrorRestartCount = 0

        # Vendor note (250514): read json file for single-color refill config and channel-color mapping
        # /home/prz/klipper/klippy/extras/phrozen_dev/serial-screen/test.json

    # initial event registration; phrozen plugin disconnect klipper
    def Device_KlipperDisconnectHandle(self):
        self.kaos_log(
            "DEBUG",
            "[(dev.python)Device_KlipperDisconnectHandle]Phrozen extension module disconnected from Klipper",
            "SERIAL",
        )
        # disconnect AMS multi-material unit
        self.Device_DisconnectAMSDevice()
        self.Device_UnregisterDaemonThread()
        # reset AMS runtime parameters
        self.Device_ResetParams()

    # single-color M3 runout
    # single-color refill MA runout
    # 2s
    def Device_TimmerRunoutCheck(self, eventtime):
        # Vendor note (240528): during P114 state read, block STM32 report processing
        if self.G_P114RunFlag >= 1:
            self.G_P114RunFlag = self.G_P114RunFlag + 1
            if self.G_P114RunFlag >= 3:
                self.kaos_log(
                    "DEBUG", "[(dev.python)Device_TimmerRunoutCheck]P114 failed", "SERIAL"
                )
                # self.emit_p114(2)
                # self.G_P114RunFlag=0
                # empty Python dict
                Lo_AMSDetailState = {
                    "dev_id": -1,
                    "active_dev_id": -1,
                    "dev_mode": -1,
                    "cache_empty": -1,
                    "cache_full": -1,
                    "cache_exist": -1,
                    "mc_state": -1,
                    "ma_state": -1,
                    "entry_state": -1,
                    "park_state": -1,
                }
                # response data JSON conversion
                self.kaos_log("DEBUG", json.dumps(Lo_AMSDetailState), "SERIAL")

                self.kaos_log("DEBUG", "P114 failed", "SERIAL")
                self.emit_p114(2)
                self.G_P114RunFlag = 0

            # self.emit_p114(1)
            # self.G_P114RunFlag=False
            # return eventtime + AMS_FILA_RUNOUT_TIMER

        # default to unknown mode
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:  # M0
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:")
            return eventtime + AMS_FILA_RUNOUT_TIMER

        if self.G_CancelFlag == True:
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]Print cancelled")
            return eventtime + AMS_FILA_RUNOUT_TIMER

        # if last print was standalone single-color and this is single-color refill, will loop-pause if no filament; M3/M2 handled separately
        # =====M3
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:  # M3 M2
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]Single-color mode timer")
            # Vendor note (240411): ifno P0 M3 command received, skip runout detection
            if self.G_P0M3Flag == False:
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]No P0M3 command or AMS connected, skip single-color M3 detection, use AMS for single-color")
                return eventtime + AMS_FILA_RUNOUT_TIMER
            # else:
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]No AMS and P0M3 received, execute single-color M3 detection")

            if self.G_ToolheadIfHaveFilaFlag == True:
                self.G_ToolheadFirstInputFila = True
            if self.G_ToolheadFirstInputFila == False:
                self.kaos_log("DEBUG", "No filament detected during the first feed", "SERIAL")
                return eventtime + AMS_FILA_RUNOUT_TIMER
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.P0M3FilaRunoutSpittingFinished == True:  # complete
                    # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]Purge complete")
                    return eventtime + AMS_FILA_RUNOUT_TIMER
                self.kaos_log("DEBUG", "Filament detected. Starting purge", "SERIAL")
                self.kaos_log(
                    "DEBUG",
                    "Calling external macro PG108 to start purging in single-color M3 mode; automatic purge is currently disabled",
                    "SERIAL",
                )
                # Vendor note (240407): placed before purge call to prevent immediate feed-then-purge multi-command error
                self.P0M3FilaRunoutSpittingFinished = True  # complete,preventcall
                # command = """
                #     G90
                #     G1 X250 Y10 F10000
                #     G91
                #     G1 Z10 F500
                #     G92 E0
                #     G1 E100 F500
                #     G92 E0
                #     G0
                # """
                # self.G_PhrozenGCode.run_script_from_command(command)
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]command=%s" % command)
                if self.G_P0M3ToolheadHaveFilaNotSpittingFlag == True:
                    self.kaos_log(
                        "DEBUG",
                        "P0M3 entered printing and found filament already in the toolhead; no purge needed",
                        "SERIAL",
                    )
                    self.G_P0M3ToolheadHaveFilaNotSpittingFlag = False
                else:
                    self.kaos_log(
                        "DEBUG",
                        "Automatic purge is disabled; resume manually and purge afterward",
                        "SERIAL",
                    )
                    # command_string = """
                    # PG108
                    # """
                    # self.G_PhrozenGCode.run_script_from_command(command_string)
                    # self.G_PhrozenFluiddRespondInfo("command_string='%s'" % command_string)
                    # self.G_PhrozenFluiddRespondInfo("purge complete, toolhead detectedhas filamentresume printing")

                self.STM32ReprotPauseFlag = 0
                return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER

            # Vendor note (240108): already paused, no re-pause
            if self.G_KlipperIfPaused == True:
                # Vendor note (251127): suspected cause: MCU error "timer too close";
                # self.G_PhrozenFluiddRespondInfo("P0 M3 standalone mode, already paused")
                if self.G_RetryToPauseAreaFlag == False:
                    self.G_RetryToPauseAreaCount = self.G_RetryToPauseAreaCount + 1
                    self.kaos_log(
                        "DEBUG",
                        "self.G_RetryToPauseAreaCount=%d" % self.G_RetryToPauseAreaCount,
                        "SERIAL",
                    )
                    # Vendor note (251124): send extra pause commands after pause to ensure runout pause stops;
                    if self.G_RetryToPauseAreaCount >= 6:
                        self.G_RetryToPauseAreaCount = 0
                        self.G_RetryToPauseAreaFlag = True
                    else:
                        if self.G_PG108Ingoing == 1:
                            self.kaos_log(
                                "DEBUG",
                                "PG108 is purging and the toolhead Hall sensor suddenly detected filament depletion",
                                "SERIAL",
                            )
                            self.kaos_log(
                                "DEBUG",
                                "PG108 is purging. Do not pause immediately, or the current purge position will be saved as the pause position and may cause a collision with the purge box on resume",
                                "SERIAL",
                            )
                        else:
                            self.kaos_log(
                                "DEBUG",
                                "PG108 is not purging; it is safe to pause for filament runout",
                                "SERIAL",
                            )

                            if self.G_KlipperInPausing == True:
                                self.kaos_log(
                                    "DEBUG",
                                    "Pause is already in progress; duplicate pause is not allowed",
                                    "SERIAL",
                                )
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "Pause is not currently in progress; pausing is allowed",
                                    "SERIAL",
                                )
                                # Vendor note (250527): pause at feed waiting area
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] Start external macro PRZ_PAUSE_WAITINGAREA",
                                    "SERIAL",
                                )
                                command = """
                                PRZ_PAUSE_WAITINGAREA
                                """
                                self.G_PhrozenGCode.run_script_from_command(command)
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] End external macro: command=%s" % (command),
                                    "SERIAL",
                                )

                return eventtime + AMS_FILA_RUNOUT_TIMER

            # if no toolhead filament, enter pause
            if self.G_ToolheadIfHaveFilaFlag == False:
                self.kaos_log("DEBUG", "P0M3 standalone mode: no filament detected", "SERIAL")
                self.kaos_log(
                    "DEBUG", "self.G_IfChangeFilaOngoing=%d" % self.G_IfChangeFilaOngoing, "SERIAL"
                )
                # Vendor note (250522): runout detection only when AMS not feeding
                if self.G_IfChangeFilaOngoing == False:
                    self.AMSRunoutPauseTimeCount = 0
                    self.kaos_log(
                        "DEBUG", "Standalone M3 single-color runout handling: pausing", "SERIAL"
                    )

                    # #cancel
                    # self.G_PhrozenPrinterCancelPauseResume.cmd_CANCEL_PRINT(None)
                    Lo_PauseStatus = self.G_PhrozenPrinterCancelPauseResume.get_status(None)
                    self.kaos_log(
                        "DEBUG",
                        "Current pause state-Lo_PauseStatus='%s'" % Lo_PauseStatus,
                        "SERIAL",
                    )

                    self.kaos_log(
                        "DEBUG",
                        "Lo_PauseStatus['is_paused']='%s'" % Lo_PauseStatus["is_paused"],
                        "SERIAL",
                    )
                    # // current-Lo_PauseStatus='{'is_paused': True}'
                    if Lo_PauseStatus["is_paused"] == True:
                        self.kaos_log("DEBUG", "Already paused", "SERIAL")
                    else:
                        self.kaos_log("DEBUG", "Not currently paused", "SERIAL")

                        self.kaos_log("DEBUG", "Quick pause is disabled", "SERIAL")
                        self.G_KlipperQuickPause = False

                        if self.G_KlipperInPausing == True:
                            self.kaos_log(
                                "DEBUG",
                                "Pause is already in progress; duplicate pause is not allowed",
                                "SERIAL",
                            )
                        else:
                            self.kaos_log(
                                "DEBUG",
                                "Pause is not currently in progress; pausing is allowed",
                                "SERIAL",
                            )
                            if self.G_PG108Ingoing == 1:
                                self.kaos_log(
                                    "DEBUG",
                                    "PG108 is purging and the toolhead Hall sensor suddenly detected filament depletion",
                                    "SERIAL",
                                )
                                self.kaos_log(
                                    "DEBUG",
                                    "PG108 is purging. Do not pause immediately, or the current purge position will be saved as the pause position and may cause a collision with the purge box on resume",
                                    "SERIAL",
                                )
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "PG108 is not purging; it is safe to pause for filament runout",
                                    "SERIAL",
                                )

                                self.Cmds_PhrozenKlipperPauseM2M3ToSTM32(None)
                                # Vendor note (250812): single-color runout detection, return to pause zone
                                self.G_RetryToPauseAreaFlag = False
                                self.G_RetryToPauseAreaCount = 0
                                # Vendor note (250527): pause at feed waiting area
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] Start external macro PRZ_PAUSE_WAITINGAREA",
                                    "SERIAL",
                                )
                                command = """
                                PRZ_PAUSE_WAITINGAREA
                                """
                                self.G_PhrozenGCode.run_script_from_command(command)
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] End external macro: command=%s" % (command),
                                    "SERIAL",
                                )
                                # Vendor note (250521): AMS multi-material present
                                # if self.G_AMSDevice1IfNormal==True or self.G_AMSDevice2IfNormal==True:
                                #    self.emit_protocol("+PAUSE:4,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                                # else:
                                self.G_PhrozenFluiddRespondInfo(
                                    "+PAUSE:b,%d,%d"
                                    % (
                                        self.G_ChangeChannelTimeoutOldChan,
                                        self.G_ChangeChannelTimeoutNewChan,
                                    )
                                )

                                # Vendor note (250527): pause at feed waiting area
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] Start external macro PRZ_PAUSE_WAITINGAREA",
                                    "SERIAL",
                                )
                                command = """
                                PRZ_PAUSE_WAITINGAREA
                                """
                                self.G_PhrozenGCode.run_script_from_command(command)
                                self.kaos_log(
                                    "DEBUG",
                                    "[SERVICE] End external macro: command=%s" % (command),
                                    "SERIAL",
                                )

            self.P0M3FilaRunoutSpittingFinished = False  #
            return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER

        # #=====MA
        # if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:#M2
        #     # Vendor note (241106): P8 feed successful: execute runout detection and refill
        #     if self.G_P0M2MAStartPrintFlag==1:
        #         #self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]P8 feed successful, execute runout detection refill")
        #         #if self.G_ToolheadIfHaveFilaFlag==True:
        #         #    self.G_PhrozenFluiddRespondInfo("P8 feed successful, toolhead has filament")
        #         if self.G_ToolheadIfHaveFilaFlag==False:
        #             self.G_PhrozenFluiddRespondInfo("P8 finished one channel, toolhead no filament, auto-feed new channel, moving to waiting area; timeout")
        #             #self.Cmds_CmdP8(None)

        #             # Vendor note (240104): filament change in progress, pause not allowed
        #             if self.G_IfChangeFilaOngoing==False:
        #                 self.G_PhrozenFluiddRespondInfo("Single-color refill temp pause, waiting for STM32 to feed new filament")
        #                 #toolhead no filament, klipper pause
        #                 self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
        #                 self.AMSRunoutPauseTimeCount = 0
        #                 self.AMSRunoutPauseTimeoutFlag=0

        #     self.P0M3FilaRunoutSpittingFinished = False
        #     #self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]return;self.P0M3FilaRunoutSpittingFinished = False")
        #     return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER

        # =====M2MA
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:  # M2
            # Vendor note (250607): print status: 1=retracting; 2=feeding; 3=printing; 4=paused
            if self.G_KlipperPrintStatus == 3:
                # if serial error detected, start count
                if self.G_SerialPort1OpenFlag == False:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode printing in progress; if self.G_KlipperPrintStatus == 3",
                        "SERIAL",
                    )
                    self.G_ASM1DisconnectErrorCount = self.G_ASM1DisconnectErrorCount + 1
                    self.kaos_log(
                        "DEBUG",
                        "self.G_ASM1DisconnectErrorCount=%d" % self.G_ASM1DisconnectErrorCount,
                        "SERIAL",
                    )
                    if self.G_ASM1DisconnectErrorCount >= 2:  # 4s
                        try:
                            self.kaos_log("DEBUG", "Reinitializing serial port 1", "SERIAL")
                            self.G_SerialPort1Obj = serial.Serial(
                                self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3
                            )
                            # serial port opened successfully
                            if self.G_SerialPort1Obj is not None:
                                if self.G_SerialPort1Obj.is_open:
                                    self.G_SerialPort1OpenFlag = True
                                    self.kaos_log(
                                        "DEBUG", "Reinitializing serial port 1 successful", "SERIAL"
                                    )
                                    self.G_ASM1DisconnectErrorCount = 0
                                    # self.G_PauseToLCDString=""
                                    # Vendor note (231213): open serial port
                                    self.G_SerialPort1Obj.flushInput()  # clean serial write cache
                                    self.G_SerialPort1Obj.flush()
                                    self.kaos_log(
                                        "DEBUG", "Serial port 1 buffers cleared", "SERIAL"
                                    )
                                    self.kaos_log(
                                        "DEBUG", "Re-registering serial port 1 callback", "SERIAL"
                                    )
                                    self.G_SerialPort1RecvTimmer = (
                                        self.G_PhrozenReactor.register_timer(
                                            self.Device_TimmerUart1Recv,
                                            self.G_PhrozenReactor.NOW,
                                        )
                                    )
                        except:
                            self.kaos_log(
                                "DEBUG",
                                "Unable to open tty1. Check the USB connection or try rebooting.",
                                "SERIAL",
                            )
                            self.G_SerialPort1OpenFlag = False
                            self.G_ASM1DisconnectErrorCount = self.G_ASM1DisconnectErrorCount + 1
                            self.kaos_log(
                                "DEBUG",
                                "self.G_ASM1DisconnectErrorCount=%d"
                                % self.G_ASM1DisconnectErrorCount,
                                "SERIAL",
                            )
                            if self.G_ASM1DisconnectErrorCount >= 5:  # 10s
                                self.G_ASM1DisconnectErrorCount = 0
                                self.kaos_log(
                                    "DEBUG", "AMS1 connectedfilament runout10s, pause", "SERIAL"
                                )
                                if self.G_KlipperIfPaused == False:
                                    self.G_KlipperIfPaused = True
                                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                                    if self.G_CancelFlag == False:
                                        self.kaos_log("DEBUG", "AMS1 connectederrorpause", "SERIAL")
                                        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:  # M0
                                            self.kaos_log(
                                                "DEBUG", "Unknown mode, do notpause", "SERIAL"
                                            )
                                        else:
                                            if self.STM32ReprotPauseFlag == 0:
                                                self.G_PauseTriggerWhileChangeChannelFlag = True
                                                if self.PG102Flag == True:
                                                    self.kaos_log(
                                                        "DEBUG",
                                                        "Purging is in progress. Delay the pause until purging finishes",
                                                        "SERIAL",
                                                    )
                                                    self.PG102DelayPauseFlag = True
                                                    # self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                                                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                        self.G_ChangeChannelTimeoutOldChan,
                                                        self.G_ChangeChannelTimeoutNewChan,
                                                    )
                                                else:
                                                    self.kaos_log(
                                                        "DEBUG",
                                                        "No purge in progress; can pause immediately",
                                                        "SERIAL",
                                                    )

                                                    if self.G_KlipperInPausing == False:
                                                        self.kaos_log(
                                                            "DEBUG",
                                                            "No pause is in progress; a new pause is allowed",
                                                            "SERIAL",
                                                        )
                                                        self.kaos_log(
                                                            "DEBUG", "Quick pause enabled", "SERIAL"
                                                        )
                                                        self.G_KlipperQuickPause = True
                                                        # klipper active pause
                                                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(
                                                            None
                                                        )
                                                    else:
                                                        self.kaos_log(
                                                            "DEBUG",
                                                            "A pause is already in progress; a new pause is not allowed",
                                                            "SERIAL",
                                                        )

                                                    self.G_KlipperIfPaused = True
                                                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                                                    self.STM32ReprotPauseFlag = 1
                                                    # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                                                    self.G_ChangeChannelFirstFilaFlag = True
                                                    self.G_PhrozenFluiddRespondInfo(
                                                        "+PAUSE:g,%d,%d"
                                                        % (
                                                            self.G_ChangeChannelTimeoutOldChan,
                                                            self.G_ChangeChannelTimeoutNewChan,
                                                        )
                                                    )
                                                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                        self.G_ChangeChannelTimeoutOldChan,
                                                        self.G_ChangeChannelTimeoutNewChan,
                                                    )
                                            else:
                                                self.G_PauseTriggerWhileChangeChannelFlag = True
                                                self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                    self.G_ChangeChannelTimeoutOldChan,
                                                    self.G_ChangeChannelTimeoutNewChan,
                                                )

                                # if self.G_KlipperIfPaused==True:
                                else:
                                    self.kaos_log(
                                        "DEBUG", "USBerror, currentalready paused", "SERIAL"
                                    )
                                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                        self.G_ChangeChannelTimeoutOldChan,
                                        self.G_ChangeChannelTimeoutNewChan,
                                    )

            # Vendor note (241106): P8 feed successful: execute runout detection and refill
            if self.G_P0M2MAStartPrintFlag == 1:
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]P8 feed successful, execute runout detection refill")
                # if self.G_ToolheadIfHaveFilaFlag==True:
                #    self.G_PhrozenFluiddRespondInfo("P8 feed successful, toolhead has filament")
                # if self.G_ToolheadIfHaveFilaFlag==False:
                #     self.G_PhrozenFluiddRespondInfo("P8 finished one channel, toolhead no filament, auto-feed new channel, moving to waiting area; timeout")
                # self.Cmds_CmdP8(None)
                # first filament detect entry, start recording toolhead filament state
                if self.G_ToolheadIfHaveFilaFlag == True:
                    # toolhead first filament detected
                    self.G_ToolheadFirstInputFila = True
                # first time: no filament manually loaded, return
                if self.G_ToolheadFirstInputFila == False:
                    # runout handling; first feed not yet done;if not self.G_ToolheadFirstInputFila:")
                    return eventtime + AMS_FILA_RUNOUT_TIMER

                if self.G_ToolheadIfHaveFilaFlag == True:
                    # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]if self.G_ToolheadIfHaveFilaFlag==True:")

                    if self.P0M3FilaRunoutSpittingFinished == True:
                        # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]return;if self.P0M3FilaRunoutSpittingFinished==True:")
                        # Vendor note (241106): once toolhead filament detected, if continues to detect, stop
                        return eventtime + AMS_FILA_RUNOUT_TIMER
                    else:
                        self.P0M3FilaRunoutSpittingFinished = True

                    # Vendor note (240123): after final no-filament timeout, do not auto-resume
                    if self.AMSRunoutPauseTimeoutFlag == 1:
                        # Vendor note (240221): after no-filament timeout, user must manually press resume
                        # self.AMSRunoutPauseTimeoutFlag=0
                        self.kaos_log(
                            "DEBUG",
                            "single-color refill mode timeout, will not auto-resume; manual resume is required",
                            "SERIAL",
                        )
                        return eventtime + AMS_FILA_RUNOUT_TIMER

                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode; toolheadfrom noneto has detectedfilamentresume printing",
                        "SERIAL",
                    )

                    if self.AMSRunoutPauseTimeCount > 0:
                        self.kaos_log(
                            "DEBUG",
                            "AMSRunoutPauseTimeCount=%d" % self.AMSRunoutPauseTimeCount,
                            "SERIAL",
                        )
                        self.AMSRunoutPauseTimeCount = 0
                        self.G_M2MAModeResumeFlag = True
                    # Vendor note (241106): count is 0 or timeout is 0
                    else:
                        self.kaos_log(
                            "DEBUG",
                            "AMSRunoutPauseTimeCount=%d" % self.AMSRunoutPauseTimeCount,
                            "SERIAL",
                        )
                        if self.G_KlipperIfPaused == True:
                            self.kaos_log(
                                "DEBUG", "already pause, manual resume is required", "SERIAL"
                            )
                            self.G_PhrozenFluiddRespondInfo(
                                "+PAUSE:4,%d,%d"
                                % (
                                    self.G_ChangeChannelTimeoutOldChan,
                                    self.G_ChangeChannelTimeoutNewChan,
                                )
                            )
                    # Vendor note (240108): single-color refill feed OK, can restore state
                    if self.G_M2MAModeResumeFlag == True:
                        # self.Cmds_AMSSerial1Send("FA")
                        # self.G_PhrozenFluiddRespondInfo("Single-color refill; FA; STM32 feeding new filament")
                        self.kaos_log(
                            "DEBUG", "single-color refill mode; resume printing", "SERIAL"
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]if self.G_M2MAModeResumeFlag==True:")
                        # Vendor note (250611): # self.G_PhrozenFluiddRespondInfo("[PURGE] External macro PG108; heat, purge, wipe")
                        # command_string = """
                        #     PG108
                        #     """
                        # self.G_PhrozenGCode.run_script_from_command(command_string)
                        # Vendor note (250619): check if AMS reconnected successfully
                        self.Cmds_USBConnectErrorCheck()
                        if self.G_SerialPort1OpenFlag == True:
                            self.Cmds_AMSSerial1Send("AT+EBLOCKCHECK")
                            self.kaos_log(
                                "DEBUG", "serial port 1-AMSstart timingbuffer-full time", "SERIAL"
                            )
                        if self.G_SerialPort2OpenFlag == True:
                            self.Cmds_AMSSerial2Send("AT+EBLOCKCHECK")
                            self.kaos_log(
                                "DEBUG", "serial port 2-AMSstart timingbuffer-full time", "SERIAL"
                            )
                        # self.G_ProzenToolhead.dwell(1)
                        self.kaos_log("DEBUG", "[FIRMWARE] External macro PG109 heat-up", "SERIAL")
                        command_string = """
                            PG109
                            """
                        self.G_PhrozenGCode.run_script_from_command(command_string)
                        self.kaos_log(
                            "DEBUG",
                            "[FIRMWARE] External macro PG109 heat-up; command_string='%s'"
                            % command_string,
                            "SERIAL",
                        )
                        # Vendor note (251120): entering purge, set flag to prevent PG108 purge Hall-sensor pause at purge zone;
                        self.G_PG108Ingoing = 1
                        self.kaos_log(
                            "DEBUG", "[PURGE] External macro PG108; heat, purge, wipe", "SERIAL"
                        )
                        command_string = """
                            PG108
                            """
                        self.G_PhrozenGCode.run_script_from_command(command_string)
                        self.G_PG108Ingoing = 0
                        if self.G_SerialPort1OpenFlag == True:
                            self.Cmds_AMSSerial1Send("AT+EBLOCKEND")
                            self.kaos_log(
                                "DEBUG", "serial port 1-AMSfinishtimingbuffer-full time", "SERIAL"
                            )
                        if self.G_SerialPort2OpenFlag == True:
                            self.Cmds_AMSSerial2Send("AT+EBLOCKEND")
                            self.kaos_log(
                                "DEBUG", "serial port 2-AMSfinishtimingbuffer-full time", "SERIAL"
                            )

                        # if STM32 pause error, cannot resume print;
                        if self.STM32ReprotPauseFlag == 1:
                            self.kaos_log(
                                "DEBUG",
                                "automatic refill mode, detectedhas filament, but purgeSTM32 up report has pause, cannotauto-resume",
                                "SERIAL",
                            )
                            # Vendor note (240125): encapsulated function
                            # self.Cmds_PhrozenKlipperResumeCommon()

                            if self.G_KlipperInPausing == False:
                                self.kaos_log(
                                    "DEBUG",
                                    "No pause is in progress; a new pause is allowed",
                                    "SERIAL",
                                )
                                self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                                self.G_KlipperQuickPause = True
                                # klipper active pause
                                self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "A pause is already in progress; a new pause is not allowed",
                                    "SERIAL",
                                )

                            self.G_KlipperIfPaused = True
                            # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                            self.STM32ReprotPauseFlag = 1
                            # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                            self.G_ChangeChannelFirstFilaFlag = True
                            self.kaos_log("DEBUG", self.G_PauseToLCDString, "SERIAL")
                            self.G_P0M2MAStartPrintFlag = 0
                        else:
                            self.kaos_log("DEBUG", "toolhead has filament, resume", "SERIAL")
                            self.G_M2MAModeResumeFlag = False
                            # Vendor note (240125): encapsulated function
                            self.Cmds_PhrozenKlipperResumeCommon()
                            self.G_KlipperIfPaused = False
                            # Vendor note (240124): STM32 active report, allow one pause
                            self.STM32ReprotPauseFlag = 0

                        # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]self.G_KlipperIfPaused = False")
                        self.G_PhrozenFluiddRespondInfo(
                            "+RESUME:2,%d" % self.G_ChangeChannelTimeoutNewChan
                        )

                    # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER")
                    # Vendor note (240109): changed to eventtime
                    return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER
                    # return eventtime + AMS_FILA_RUNOUT_TIMER

                # Vendor note (240108): already paused, no re-pause
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "[(dev.python)Device_TimmerRunoutCheck]single-color refill mode; temporary pause, stm32 re feed new filament",
                        "SERIAL",
                    )
                    if self.AMSRunoutPauseTimeCount == 0:
                        # Vendor note (240122): after pause, immediately send command to STM32 to feed new filament
                        # time.sleep(1)
                        # self.G_ProzenToolhead.dwell(0.5)

                        # self.Cmds_AMSSerial1Send("FA")
                        self.kaos_log(
                            "DEBUG",
                            "single-color refill mode temporary pause after, P8Infila; stm32feed new filament",
                            "SERIAL",
                        )

                        # Vendor note (240511): on resume, reinitialize serial to handle AMS hot-plug serial errors
                        try:
                            self.kaos_log("DEBUG", "Reinitializing serial port 1", "SERIAL")
                            self.G_SerialPort1Obj = serial.Serial(
                                self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3
                            )
                            # serial port opened successfully
                            if self.G_SerialPort1Obj is not None:
                                if self.G_SerialPort1Obj.is_open:
                                    self.G_SerialPort1OpenFlag = True
                                    self.kaos_log(
                                        "DEBUG", "Reinitializing serial port 1 successful", "SERIAL"
                                    )
                                    # Vendor note (231213): open serial port
                                    self.G_SerialPort1Obj.flushInput()  # clean serial write cache
                                    self.G_SerialPort1Obj.flush()
                                    self.kaos_log(
                                        "DEBUG", "Serial port 1 buffers cleared", "SERIAL"
                                    )
                                    self.kaos_log(
                                        "DEBUG", "Re-registering serial port 1 callback", "SERIAL"
                                    )
                                    self.G_SerialPort1RecvTimmer = (
                                        self.G_PhrozenReactor.register_timer(
                                            self.Device_TimmerUart1Recv,
                                            self.G_PhrozenReactor.NOW,
                                        )
                                    )
                        except:
                            self.kaos_log(
                                "DEBUG",
                                "Unable to open tty1. Check the USB connection or try rebooting.",
                                "SERIAL",
                            )
                        try:
                            self.kaos_log(
                                "DEBUG",
                                "[(cmds.py)Cmds_PhrozenKlipperResume]Reinitializing serial port 2",
                                "SERIAL",
                            )
                            self.G_SerialPort2Obj = serial.Serial(
                                self.G_Serialport2Define, SERIAL_PORT_BAUD, timeout=3
                            )
                            # serial port opened successfully
                            if self.G_SerialPort2Obj is not None:
                                if self.G_SerialPort2Obj.is_open:
                                    self.G_SerialPort2OpenFlag = True
                                    self.kaos_log(
                                        "DEBUG", "Reinitializing serial port 2 successful", "SERIAL"
                                    )
                                    self.G_SerialPort2Obj.flushInput()  # clean serial write cache
                                    self.G_SerialPort2Obj.flush()
                                    self.kaos_log(
                                        "DEBUG", "Serial port 2 buffers cleared", "SERIAL"
                                    )
                                    self.kaos_log(
                                        "DEBUG", "Re-registering serial port 2 callback", "SERIAL"
                                    )
                                    self.G_SerialPort2RecvTimmer = (
                                        self.G_PhrozenReactor.register_timer(
                                            self.Device_TimmerUart2Recv,
                                            self.G_PhrozenReactor.NOW,
                                        )
                                    )
                        except:
                            self.kaos_log(
                                "DEBUG",
                                "Unable to open tty2. Check the USB connection or try rebooting.",
                                "SERIAL",
                            )
                        # Vendor note (250515): re-feed
                        self.Cmds_CmdP8Infila()

                    # Vendor note (240122): timer wait Ns for new filament;
                    self.AMSRunoutPauseTimeCount = self.AMSRunoutPauseTimeCount + 1
                    self.kaos_log(
                        "DEBUG",
                        "AMSRunoutPauseTimeCount=%d" % self.AMSRunoutPauseTimeCount,
                        "SERIAL",
                    )

                    # stm32,ifdetectfilament,already,can
                    if self.G_ToolheadIfHaveFilaFlag == True:
                        self.G_M2MAModeResumeFlag = True
                        self.AMSRunoutPauseTimeCount = 0

                        # Vendor note (250619): check if AMS reconnected successfully
                        self.Cmds_USBConnectErrorCheck()
                        if self.G_SerialPort1OpenFlag == True:
                            self.Cmds_AMSSerial1Send("AT+EBLOCKCHECK")
                            self.kaos_log(
                                "DEBUG", "serial port 1-AMSstart timingbuffer-full time", "SERIAL"
                            )
                        if self.G_SerialPort2OpenFlag == True:
                            self.Cmds_AMSSerial2Send("AT+EBLOCKCHECK")
                            self.kaos_log(
                                "DEBUG", "serial port 2-AMSstart timingbuffer-full time", "SERIAL"
                            )

                        # Vendor note (251120): entering purge, set flag to prevent PG108 purge Hall-sensor pause at purge zone;
                        self.G_PG108Ingoing = 1
                        self.kaos_log(
                            "DEBUG", "[PURGE] External macro PG108; heat, purge, wipe", "SERIAL"
                        )
                        command_string = """
                            PG108
                            """
                        self.G_PhrozenGCode.run_script_from_command(command_string)
                        self.G_PG108Ingoing = 0
                        if self.G_SerialPort1OpenFlag == True:
                            self.Cmds_AMSSerial1Send("AT+EBLOCKEND")
                            self.kaos_log(
                                "DEBUG", "serial port 1-AMSfinishtimingbuffer-full time", "SERIAL"
                            )
                        if self.G_SerialPort2OpenFlag == True:
                            self.Cmds_AMSSerial2Send("AT+EBLOCKEND")
                            self.kaos_log(
                                "DEBUG", "serial port 2-AMSfinishtimingbuffer-full time", "SERIAL"
                            )

                        # if STM32 pause error, cannot resume print;
                        if self.STM32ReprotPauseFlag == 1:
                            self.kaos_log(
                                "DEBUG",
                                "automatic refill mode, detectedhas filament, but purgeSTM32 up report has pause, cannotauto-resume",
                                "SERIAL",
                            )
                            # Vendor note (240125): encapsulated function
                            # self.Cmds_PhrozenKlipperResumeCommon()

                            if self.G_KlipperInPausing == False:
                                self.kaos_log(
                                    "DEBUG",
                                    "No pause is in progress; a new pause is allowed",
                                    "SERIAL",
                                )
                                self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                                self.G_KlipperQuickPause = True
                                # klipper active pause
                                self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "A pause is already in progress; a new pause is not allowed",
                                    "SERIAL",
                                )

                            self.G_KlipperIfPaused = True
                            # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                            self.STM32ReprotPauseFlag = 1
                            # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                            self.G_ChangeChannelFirstFilaFlag = True
                            self.kaos_log("DEBUG", self.G_PauseToLCDString, "SERIAL")
                            self.G_P0M2MAStartPrintFlag = 0
                        else:
                            # self.G_PhrozenFluiddRespondInfo("toolhead has filament, resume")
                            # self.G_M2MAModeResumeFlag=False
                            # # Vendor note (240125): encapsulated function
                            # self.Cmds_PhrozenKlipperResumeCommon()
                            # self.G_KlipperIfPaused = False
                            # # Vendor note (240124): STM32 active report, allow one pause
                            # self.STM32ReprotPauseFlag=0

                            # Vendor note (240125): encapsulated function
                            self.Cmds_PhrozenKlipperResumeCommon()
                            self.kaos_log(
                                "DEBUG",
                                "MA single-color refill mode; toolhead detectedfilament, move resume printing",
                                "SERIAL",
                            )
                            self.G_KlipperIfPaused = False
                            # Vendor note (240124): STM32 active report, allow one pause
                            self.STM32ReprotPauseFlag = 0

                    if self.AMSRunoutPauseTimeCount >= 50:
                        self.AMSRunoutPauseTimeCount = 0
                        self.AMSRunoutPauseTimeoutFlag = 1
                        # self.Cmds_PhrozenKlipperPauseMAToSTM32(None)
                        self.kaos_log(
                            "DEBUG",
                            "M2MA single-color refill mode; stm32feed new filamenttimeout100s",
                            "SERIAL",
                        )
                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:4,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )

                    return eventtime + AMS_FILA_RUNOUT_TIMER

                if self.G_ToolheadIfHaveFilaFlag == False:
                    # Vendor note (240104): filament change in progress, pause not allowed
                    if self.G_IfChangeFilaOngoing == False:
                        self.kaos_log(
                            "DEBUG",
                            "M2MA single-color refill mode temporary pause, stm32feed new filament",
                            "SERIAL",
                        )

                        if self.G_KlipperInPausing == False:
                            self.kaos_log(
                                "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                            )
                            # Vendor note (250607): #self.G_PhrozenFluiddRespondInfo("Quick pause enabled")
                            # self.G_KlipperQuickPause = True
                            # toolhead no filament, klipper pause
                            self.Cmds_PhrozenKlipperPauseMAToSTM32(None)
                        else:
                            self.kaos_log(
                                "DEBUG",
                                "A pause is already in progress; a new pause is not allowed",
                                "SERIAL",
                            )

                        self.AMSRunoutPauseTimeCount = 0
                        self.AMSRunoutPauseTimeoutFlag = 0

            self.P0M3FilaRunoutSpittingFinished = False

            return eventtime + AMS_FILA_RUNOUT_TIMER
            # return self.G_PhrozenReactor.NOW + AMS_FILA_RUNOUT_TIMER

        # =====M1MC
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:  # M1
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:")
            # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]Runout handling; multi-material mode detection")

            # Vendor note (240407): in multi-material mode: no toolhead filament during print, pause
            # Vendor note (240527): not None, confirmed P1Cn command received
            # if self.G_ChangeChannelTimeoutOldGcmd is not None:
            #     if self.G_ToolheadIfHaveFilaFlag==False:
            #         if self.G_ToolheadIfHaveFilaFlag==False:
            #             self.G_PhrozenFluiddRespondInfo("[(cmds.python)Device_TimmerRunoutCheck]MC multi-material printing: toolhead no filament detected")

            # Vendor note (250607): print status: 1=retracting; 2=feeding; 3=printing; 4=paused
            if self.G_KlipperPrintStatus == 3:

                # if serial error detected, start count
                if self.G_SerialPort1OpenFlag == False:
                    self.kaos_log(
                        "DEBUG",
                        "multi-material printing in progress; if self.G_KlipperPrintStatus == 3",
                        "SERIAL",
                    )
                    self.G_ASM1DisconnectErrorCount = self.G_ASM1DisconnectErrorCount + 1
                    self.kaos_log(
                        "DEBUG",
                        "AMSre connect; self.G_ASM1DisconnectErrorCount=%d"
                        % self.G_ASM1DisconnectErrorCount,
                        "SERIAL",
                    )
                    # Vendor note (250619): check if AMS reconnected successfully
                    self.Cmds_USBConnectErrorCheck()

                    if self.G_ASM1DisconnectErrorCount >= 5:  # 10s
                        try:
                            self.kaos_log("DEBUG", "Reinitializing serial port 1", "SERIAL")
                            self.G_SerialPort1Obj = serial.Serial(
                                self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3
                            )
                            # serial port opened successfully
                            if self.G_SerialPort1Obj is not None:
                                if self.G_SerialPort1Obj.is_open:
                                    self.G_SerialPort1OpenFlag = True
                                    self.kaos_log(
                                        "DEBUG", "Reinitializing serial port 1 successful", "SERIAL"
                                    )
                                    self.G_ASM1DisconnectErrorCount = 0
                                    # self.G_PauseToLCDString=""
                                    # Vendor note (231213): open serial port
                                    self.G_SerialPort1Obj.flushInput()  # clean serial write cache
                                    self.G_SerialPort1Obj.flush()
                                    self.kaos_log(
                                        "DEBUG", "Serial port 1 buffers cleared", "SERIAL"
                                    )
                                    self.kaos_log(
                                        "DEBUG", "Re-registering serial port 1 callback", "SERIAL"
                                    )
                                    self.G_SerialPort1RecvTimmer = (
                                        self.G_PhrozenReactor.register_timer(
                                            self.Device_TimmerUart1Recv,
                                            self.G_PhrozenReactor.NOW,
                                        )
                                    )
                        except:
                            self.kaos_log(
                                "DEBUG",
                                "Unable to open tty1. Check the USB connection or try rebooting.",
                                "SERIAL",
                            )
                            self.G_SerialPort1OpenFlag = False
                            self.G_ASM1DisconnectErrorCount = self.G_ASM1DisconnectErrorCount + 1
                            self.kaos_log(
                                "DEBUG",
                                "self.G_ASM1DisconnectErrorCount=%d"
                                % self.G_ASM1DisconnectErrorCount,
                                "SERIAL",
                            )
                            if self.G_ASM1DisconnectErrorCount >= 20:  # 40s
                                self.G_ASM1DisconnectErrorCount = 0
                                self.kaos_log(
                                    "DEBUG", "AMS1 connectedfilament runout40s, pause", "SERIAL"
                                )
                                if self.G_KlipperIfPaused == False:
                                    self.G_KlipperIfPaused = True
                                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                                    if self.G_CancelFlag == False:
                                        self.kaos_log("DEBUG", "AMS1 connectederrorpause", "SERIAL")
                                        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:  # M0
                                            self.kaos_log(
                                                "DEBUG", "Unknown mode, do notpause", "SERIAL"
                                            )
                                        else:
                                            if self.STM32ReprotPauseFlag == 0:
                                                self.G_PauseTriggerWhileChangeChannelFlag = True
                                                if self.PG102Flag == True:
                                                    self.kaos_log(
                                                        "DEBUG",
                                                        "Purging is in progress. Delay the pause until purging finishes",
                                                        "SERIAL",
                                                    )
                                                    self.PG102DelayPauseFlag = True
                                                    # self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                                                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                        self.G_ChangeChannelTimeoutOldChan,
                                                        self.G_ChangeChannelTimeoutNewChan,
                                                    )
                                                else:
                                                    self.kaos_log(
                                                        "DEBUG",
                                                        "No purge in progress; can pause immediately",
                                                        "SERIAL",
                                                    )
                                                    if self.PG102Flag == True:
                                                        self.kaos_log(
                                                            "DEBUG",
                                                            "Purging is in progress. Delay the pause until purging finishes",
                                                            "SERIAL",
                                                        )
                                                        self.PG102DelayPauseFlag = True
                                                        self.G_PauseToLCDString = (
                                                            "+PAUSE:g,%d,%d"
                                                            % (
                                                                self.G_ChangeChannelTimeoutOldChan,
                                                                self.G_ChangeChannelTimeoutNewChan,
                                                            )
                                                        )
                                                    else:
                                                        if self.G_KlipperInPausing == False:
                                                            self.kaos_log(
                                                                "DEBUG",
                                                                "No pause is in progress; a new pause is allowed",
                                                                "SERIAL",
                                                            )
                                                            self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(
                                                                None
                                                            )
                                                            self.G_KlipperIfPaused = True
                                                            # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                                                            self.STM32ReprotPauseFlag = 1
                                                            # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                                                            self.G_ChangeChannelFirstFilaFlag = True
                                                            self.G_PhrozenFluiddRespondInfo(
                                                                "+PAUSE:g,%d,%d"
                                                                % (
                                                                    self.G_ChangeChannelTimeoutOldChan,
                                                                    self.G_ChangeChannelTimeoutNewChan,
                                                                )
                                                            )
                                                            self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                                self.G_ChangeChannelTimeoutOldChan,
                                                                self.G_ChangeChannelTimeoutNewChan,
                                                            )
                                                        else:
                                                            self.kaos_log(
                                                                "DEBUG",
                                                                "A pause is already in progress; a new pause is not allowed",
                                                                "SERIAL",
                                                            )
                                            else:
                                                self.G_PauseTriggerWhileChangeChannelFlag = True
                                                self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                                    self.G_ChangeChannelTimeoutOldChan,
                                                    self.G_ChangeChannelTimeoutNewChan,
                                                )

                                # if self.G_KlipperIfPaused==True:
                                else:
                                    self.kaos_log(
                                        "DEBUG", "USBerror, currentalready paused", "SERIAL"
                                    )
                                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                                        self.G_ChangeChannelTimeoutOldChan,
                                        self.G_ChangeChannelTimeoutNewChan,
                                    )

            return eventtime + AMS_FILA_RUNOUT_TIMER

        # multi-layer guard, prevent above failure, timer stop
        return eventtime + AMS_FILA_RUNOUT_TIMER

    # 100ms
    def Device_TimmerUartRecvHandler(self, AMSNum, SerialRxBytes, SerialRxASCIIStr):
        # Vendor note (240603): no print needed
        if "+PAUSE" in SerialRxASCIIStr:
            self.kaos_log(
                "DEBUG",
                "[(dev.py)Device_TimmerUartRecvHandler]pause; %s" % SerialRxASCIIStr,
                "SERIAL",
            )
        else:
            self.kaos_log(
                "DEBUG", "[(dev.py)Device_TimmerUartRecvHandler]%s" % SerialRxASCIIStr, "SERIAL"
            )

        # #cancel
        # self.G_PhrozenPrinterCancelPauseResume.cmd_CANCEL_PRINT(None)
        Lo_PauseStatus = self.G_PhrozenPrinterCancelPauseResume.get_status(None)
        self.kaos_log("DEBUG", "Current pause state-Lo_PauseStatus='%s'" % Lo_PauseStatus, "SERIAL")
        self.kaos_log(
            "DEBUG", "Lo_PauseStatus['is_paused']='%s'" % Lo_PauseStatus["is_paused"], "SERIAL"
        )
        # // current-Lo_PauseStatus='{'is_paused': True}'
        if Lo_PauseStatus["is_paused"] == True:
            self.kaos_log("DEBUG", "Already paused", "SERIAL")
        else:
            self.kaos_log("DEBUG", "Not currently paused", "SERIAL")

        # self.G_PhrozenFluiddRespondInfo("Serial receive G_PauseToLCDString: %s" % self.G_PauseToLCDString)

        # # // AMS board 2 firmware-1 1
        # if "V-H1-I1-F?" in SerialRxASCIIStr:
        #     #=====DriveCodeFile.dat
        #     # 1 , 1 , 24053 , 1 , 0
        #     # 2 , 0 , 0 , 0 , 0
        #     # 3 , 0 , 0 , 0 , 0
        #     # 4 , 0 , 0 , 0 , 0
        #     # 5 , 5 , 24046 , 5 , 0
        #     # 6 , 0 , 0 , 0 , 0
        #     # 7 , 7 , 24051 , 7 , 0
        #     # 8 , 0 , 0 , 0 , 0
        #     # 9 , 0 , 0 , 0 , 0
        #     # 10 , 10 , 24054 , 10 , 0
        #     # 11 , 11 , 24047 , 11 , 0
        #     # 12 , 0 , 0 , 0 , 0
        #     # 13 , 0 , 0 , 0 , 0
        #     # 14 , 0 , 0 , 0 , 0
        #     # 15 , 0 , 0 , 0 , 0
        #     # 16 , 0 , 0 , 0 , 0
        #     # Vendor note (240530): write version to DriveCodeJson.dat
        #     filename='/home/prz/hdlDat/DriveCodeFile.dat'
        #     self.G_PhrozenFluiddRespondInfo("filename=%s" % filename)
        #     Lo_AllLine=""
        #     #data = [{"DriveCode":16,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":15,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":14,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":13,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":12,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":11,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":10,"DriveImageType":10,"DriveHwVersion":10,"DriveFwVersion":24045,"DriveId":0},{"DriveCode":9,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":8,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":7,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":6,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":5,"DriveImageType":5,"DriveHwVersion":5,"DriveFwVersion":24046,"DriveId":0},{"DriveCode":4,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":3,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":2,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":1,"DriveImageType":1,"DriveHwVersion":1,"DriveFwVersion":24042,"DriveId":0}]
        #     #f = open(filename, 'a')
        #     #json.dump(data, f)  #object
        #     #f.close()
        #     with open(filename,'r') as file:
        #         #for line in file:
        #         # # realine() read, "\n"
        #         # self.G_PhrozenFluiddRespondInfo(file.readline().strip())
        #         # #time.sleep(1)
        #         Lo_FileDataList=file.readlines()
        #         for line in Lo_FileDataList:
        #             #split = [i[:-1].split(',') for i in file.readlines()]
        #             #self.G_PhrozenFluiddRespondInfo(type(split))
        #             #self.G_PhrozenFluiddRespondInfo(split[1])
        #             #self.G_PhrozenFluiddRespondInfo(split[2])
        #             #self.G_PhrozenFluiddRespondInfo(split[3])
        #             #line_strip=line.strip()
        #             #self.G_PhrozenFluiddRespondInfo(line)
        #             #self.G_PhrozenFluiddRespondInfo("line.count=%d" % line.count)
        #             split=line.split(',')
        #             #self.G_PhrozenFluiddRespondInfo(type(split))
        #             #self.G_PhrozenFluiddRespondInfo("".join(split))
        #             #self.G_PhrozenFluiddRespondInfo(split[0])
        #             split[0]=split[0].strip()#driver number
        #             split[1]=split[1].strip()#hardware id
        #             split[2]=split[2].strip()#firmware version
        #             split[3]=split[3].strip()#image id
        #             split[4]=split[4].strip()#online status
        #             #split[4]='0'#online status,default0
        #             if "SN1" in SerialRxASCIIStr:
        #                 if split[0] == "1":
        #                     self.G_PhrozenFluiddRespondInfo(split[0])
        #                     self.G_PhrozenFluiddRespondInfo(split[1])
        #                     self.G_PhrozenFluiddRespondInfo(split[2])
        #                     self.G_PhrozenFluiddRespondInfo(split[3])
        #                     self.G_PhrozenFluiddRespondInfo(split[4])
        #                     #line=("%d,%d,%d," % (HW_VERSION,,))
        #                     line_modify=split[0]+','+'1'+','+SerialRxASCIIStr[9:14]+','+'1'+','+'1'
        #                     self.G_PhrozenFluiddRespondInfo(line_modify)
        #                     Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
        #                 else:
        #                     Lo_AllLine=Lo_AllLine+line
        #             if "SN2" in SerialRxASCIIStr:
        #                 if split[0] == "2":
        #                     self.G_PhrozenFluiddRespondInfo(split[0])
        #                     self.G_PhrozenFluiddRespondInfo(split[1])
        #                     self.G_PhrozenFluiddRespondInfo(split[2])
        #                     self.G_PhrozenFluiddRespondInfo(split[3])
        #                     self.G_PhrozenFluiddRespondInfo(split[4])
        #                     #line=("%d,%d,%d," % (HW_VERSION,,))
        #                     line_modify=split[0]+','+'1'+','+SerialRxASCIIStr[9:14]+','+'1'+','+'1'
        #                     self.G_PhrozenFluiddRespondInfo(line_modify)
        #                     Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
        #                 else:
        #                     Lo_AllLine=Lo_AllLine+line
        #             if "SN3" in SerialRxASCIIStr:
        #                 if split[0] == "3":
        #                     self.G_PhrozenFluiddRespondInfo(split[0])
        #                     self.G_PhrozenFluiddRespondInfo(split[1])
        #                     self.G_PhrozenFluiddRespondInfo(split[2])
        #                     self.G_PhrozenFluiddRespondInfo(split[3])
        #                     self.G_PhrozenFluiddRespondInfo(split[4])
        #                     #line=("%d,%d,%d," % (HW_VERSION,,))
        #                     line_modify=split[0]+','+'1'+','+SerialRxASCIIStr[9:14]+','+'1'+','+'1'
        #                     self.G_PhrozenFluiddRespondInfo(line_modify)
        #                     Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
        #                 else:
        #                     Lo_AllLine=Lo_AllLine+line
        #             if "SN4" in SerialRxASCIIStr:
        #                 if split[0] == "4":
        #                     self.G_PhrozenFluiddRespondInfo(split[0])
        #                     self.G_PhrozenFluiddRespondInfo(split[1])
        #                     self.G_PhrozenFluiddRespondInfo(split[2])
        #                     self.G_PhrozenFluiddRespondInfo(split[3])
        #                     self.G_PhrozenFluiddRespondInfo(split[4])
        #                     #line=("%d,%d,%d," % (HW_VERSION,,))
        #                     line_modify=split[0]+','+'1'+','+SerialRxASCIIStr[9:14]+','+'1'+','+'1'
        #                     self.G_PhrozenFluiddRespondInfo(line_modify)
        #                     Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
        #                 else:
        #                     Lo_AllLine=Lo_AllLine+line
        #     #self.G_PhrozenFluiddRespondInfo(Lo_AllLine)
        #     with open(filename,"w+") as file_w:
        #         file_w.write(Lo_AllLine)

        # # 16-color HUB board firmware-7 7
        # if "V-H7-I7-F" in SerialRxASCIIStr:
        #     # Vendor note (240530): write version to DriveCodeJson.dat
        #     filename='/home/prz/hdlDat/DriveCodeFile.dat'
        #     self.G_PhrozenFluiddRespondInfo("filename=%s" % filename)
        #     Lo_AllLine=""
        #     #data = [{"DriveCode":16,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":15,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":14,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":13,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":12,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":11,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":10,"DriveImageType":10,"DriveHwVersion":10,"DriveFwVersion":24045,"DriveId":0},{"DriveCode":9,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":8,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":7,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":6,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":5,"DriveImageType":5,"DriveHwVersion":5,"DriveFwVersion":24046,"DriveId":0},{"DriveCode":4,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":3,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":2,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":1,"DriveImageType":1,"DriveHwVersion":1,"DriveFwVersion":24042,"DriveId":0}]
        #     #f = open(filename, 'a')
        #     #json.dump(data, f)  #object
        #     #f.close()
        #     with open(filename,'r') as file:
        #         #for line in file:
        #         # # realine() read, "\n"
        #         # self.G_PhrozenFluiddRespondInfo(file.readline().strip())
        #         # #time.sleep(1)
        #         Lo_FileDataList=file.readlines()
        #         for line in Lo_FileDataList:
        #             #split = [i[:-1].split(',') for i in file.readlines()]
        #             #self.G_PhrozenFluiddRespondInfo(type(split))
        #             #self.G_PhrozenFluiddRespondInfo(split[1])
        #             #self.G_PhrozenFluiddRespondInfo(split[2])
        #             #self.G_PhrozenFluiddRespondInfo(split[3])
        #             #line_strip=line.strip()
        #             #self.G_PhrozenFluiddRespondInfo(line)
        #             #self.G_PhrozenFluiddRespondInfo("line.count=%d" % line.count)
        #             split=line.split(',')
        #             #self.G_PhrozenFluiddRespondInfo(type(split))
        #             #self.G_PhrozenFluiddRespondInfo("".join(split))
        #             #self.G_PhrozenFluiddRespondInfo(split[0])
        #             split[0]=split[0].strip()#driver number
        #             split[1]=split[1].strip()#hardware id
        #             split[2]=split[2].strip()#firmware version
        #             split[3]=split[3].strip()#image id
        #             split[4]=split[4].strip()#online status
        #             if split[0]== "7":
        #                 self.G_PhrozenFluiddRespondInfo(split[0])
        #                 self.G_PhrozenFluiddRespondInfo(split[1])
        #                 self.G_PhrozenFluiddRespondInfo(split[2])
        #                 self.G_PhrozenFluiddRespondInfo(split[3])
        #                 self.G_PhrozenFluiddRespondInfo(split[4])
        #                 #line=("%d,%d,%d," % (HW_VERSION,,))
        #                 line_modify=split[0]+','+'7'+','+SerialRxASCIIStr[9:14]+','+'7'+','+'1'
        #                 self.G_PhrozenFluiddRespondInfo(line_modify)
        #                 Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
        #             else:
        #                 Lo_AllLine=Lo_AllLine+line
        #     #self.G_PhrozenFluiddRespondInfo(Lo_AllLine)
        #     with open(filename,"w+") as file_w:
        #         file_w.write(Lo_AllLine)

        # Vendor note (240326): #self.G_PauseToLCDString=SerialRxASCIIStr
        # // ttyUSB0 serial receive: CS00N0M03T04C0
        self.kaos_log("DEBUG", "Current mode", "SERIAL")
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
            self.emit_mode(0, "unkown")
        elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
            self.emit_mode(1, "MC")
        elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
            self.emit_mode(2, "MA")
        elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
            self.emit_mode(3, "RUNOUT")
        else:
            self.emit_mode(-1, "error")

        # Vendor note (240524): unknown mode (not M1-MC/M2-MA/M3), skip pause
        # if not in print mode, skip pause
        if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:  # M1
            self.kaos_log("DEBUG", "Unknown mode, do not executeserial port number data", "SERIAL")
            return
            # Vendor note (240524): exit callback permanently
            # return self.G_PhrozenReactor.NEVER

        # old AMS
        # // lancaigang231202:+PAUSE:1,ch;1-feed used up, jam, pause
        # // lancaigang231202:+PAUSE:2,ch;2-pause ACK
        # // lancaigang231204:+PAUSE:3,ch;3-new channel slow-refill during print timeout 10s, pause
        # // lancaigang231205:+PAUSE:4,ch;4-new channel feed timeout 50s, pause
        # // lancaigang231205:+PAUSE:5,ch;5-new channel fast-refill during print timeout 10s, pause
        # // lancaigang231205:+PAUSE:6,ch;6-entry to park timeout 10s, pause
        # // lancaigang231205:+PAUSE:7,ch;7-buffer full timeout 30s, pause
        # // lancaigang231205:+PAUSE:8,ch;8-toolhead cutter or sensor error, pause
        # // lancaigang231205:+PAUSE:9,ch;9-filament change timeout 120s, pause
        # // lancaigang231202:+PAUSE:a,ch;a-park to buffer entry timeout 10s, pause
        # // lancaigang231202:+PAUSE:b,ch;b-reserved
        # // lancaigang231202:+PAUSE:c,ch;c-reserved
        # // lancaigang231202:+PAUSE:d,ch;d-reserved
        # // lancaigang231202:+PAUSE:10,ch;10-fluidd

        # AMS
        # // lancaigang231202:+PAUSE:1,oldchannel,newchannel;1-AMS
        # // lancaigang231202:+PAUSE:2,oldchannel,newchannel;2-pause ACK
        # // lancaigang231204:+PAUSE:3,oldchannel,newchannel;3-
        # // lancaigang231205:+PAUSE:4,oldchannel,newchannel;4-feed timeout, pause (1: jam 60s; 2: in-progress)
        # // lancaigang231205:+PAUSE:5,oldchannel,newchannel;5-
        # // lancaigang231205:+PAUSE:6,oldchannel,newchannel;6-entry to buffer timeout 20s, pause
        # // lancaigang231205:+PAUSE:7,oldchannel,newchannel;7-buffer full timeout 60s, pause (jam/nozzle clog/hotend clog)
        # // lancaigang231205:+PAUSE:8,oldchannel,newchannel;8-cutter/sensor error, 6s timeout; pause (empty spool/cutter fault)
        # // lancaigang231205:+PAUSE:9,oldchannel,newchannel;9-
        # // lancaigang231202:+PAUSE:a,oldchannel,newchannel;a-
        # // lancaigang231202:+PAUSE:b,oldchannel,newchannel;b-single-color runout detection; no filament ~3s, pause
        # // lancaigang231202:+PAUSE:c,oldchannel,newchannel;c-purge: nozzle clog; timeout 20s
        # // lancaigang231202:+PAUSE:d,oldchannel,newchannel;d-purge: AMS cannot feed, filament bite mark; timeout 20s
        # // lancaigang231202:+PAUSE:e,oldchannel,newchannel;e-print start: AMS not drying, temp > 45°C, pause, no print
        # // lancaigang231202:+PAUSE:f,oldchannel,newchannel;f-print start: AMS drying, temp > 45°C, pause, stop AMS drying
        # // lancaigang231202:+PAUSE:g,oldchannel,newchannel;g-AMS USB cable error during print, timeout 10s, report pause
        # // lancaigang231202:+PAUSE:h,oldchannel,newchannel;h-
        # // lancaigang231202:+PAUSE:i,oldchannel,newchannel;i-
        # // lancaigang231202:+PAUSE:j,oldchannel,newchannel;j-
        # // lancaigang231202:+PAUSE:10,oldchannel,newchannel;10-fluidd

        # MSG message
        # // lancaigang250516:+MSG:1,0/1,oldchannel,newchannel;0-purge start 1-purge end

        # Vendor note (241128): # Vendor note (250712): if print cancel, only filter AMS pause command
        if self.G_CancelFlag == True:
            self.kaos_log("DEBUG", "Print has been canceled, pause command", "SERIAL")
            return

        if "+PAUSE:1" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode, pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "feed use", "SERIAL")
            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # if self.G_IfChangeFilaOngoing== False:
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    self.kaos_log(
                        "DEBUG",
                        "Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan,
                        "SERIAL",
                    )

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:1,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                else:
                    # special refill state
                    # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                    # Vendor note (231207): during filament change, if feed jams, remove from toolhead tube, do not retract
                    self.G_IfInFilaBlockFlag = True
                    # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                    self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")

                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # [Translated vendor note] AMS
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:1,ch;1-feed, pause
                        # // Vendor note (231202):+PAUSE:2,ch;2-pauseACK
                        # [Translated vendor note] // Vendor note (231204):+PAUSE:3,ch;3-channelprinttimeout10s, pause
                        # [Translated vendor note] // Vendor note (231205):+PAUSE:4,ch;4-channelfeedtimeout50s, pause
                        # [Translated vendor note] // Vendor note (231205):+PAUSE:5,ch;5-channelprinttimeout10s, pause
                        # [Translated vendor note] // Vendor note (231205):+PAUSE:6,ch;6-inlet positionpark positiontimeout10s, pause
                        # [Translated vendor note] // Vendor note (231205):+PAUSE:7,ch;7-buffertimeout30s, pause
                        # [Translated vendor note] // Vendor note (231205):+PAUSE:8,ch;8-toolhead, pause
                        # // Vendor note (231205):+PAUSE:9,ch;9-filament changetimeout120s, pause
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:a,ch;a-park positionbuffertimeout10s, pause
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:b,ch;b-
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:c,ch;c-
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:d,ch;d-
                        # [Translated vendor note] // Vendor note (231202):+PAUSE:10,ch;10-screenfluiddpause

                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        # klipper active pause
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

                    self.G_KlipperIfPaused = True

                    self.STM32ReprotPauseFlag = 1
                    # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                    self.G_ChangeChannelFirstFilaFlag = True
                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    # [Translated vendor note] AMS
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:1,oldchannel,newchannel;1-AMS
                    # // Vendor note (231202):+PAUSE:2,oldchannel,newchannel;2-pauseACK
                    # // Vendor note (231204):+PAUSE:3,oldchannel,newchannel;3-
                    # [Translated vendor note] // Vendor note (231205):+PAUSE:4,oldchannel,newchannel;4-feedtimeout, pause(1, feedtimeout60s; 2, feed)
                    # // Vendor note (231205):+PAUSE:5,oldchannel,newchannel;5-
                    # [Translated vendor note] // Vendor note (231205):+PAUSE:6,oldchannel,newchannel;6-inlet positionbuffertimeout20s, pause
                    # [Translated vendor note] // Vendor note (231205):+PAUSE:7,oldchannel,newchannel;7-buffertimeout60s, pause(: toolheadhotend)
                    # [Translated vendor note] // Vendor note (231205):+PAUSE:8,oldchannel,newchannel;8-toolhead, 6stimeout; pause(: channelretractretracttoolhead)
                    # // Vendor note (231205):+PAUSE:9,oldchannel,newchannel;9-
                    # // Vendor note (231202):+PAUSE:a,oldchannel,newchannel;a-
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:b,oldchannel,newchannel;b-runout; filament3spause
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:c,oldchannel,newchannel;c-purgetoolheadnozzle clog; timeout20s
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:d,oldchannel,newchannel;d-purgeAMS, filament; timeout20s
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:e,oldchannel,newchannel;e-print, AMS, AMS45, pauseprint
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:f,oldchannel,newchannel;f-print, AMS, AMS45, pauseprint, AMS
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:g,oldchannel,newchannel;g-AMSUSB, printtimeout10s, pause
                    # // Vendor note (231202):+PAUSE:h,oldchannel,newchannel;h-
                    # // Vendor note (231202):+PAUSE:i,oldchannel,newchannel;i-
                    # // Vendor note (231202):+PAUSE:j,oldchannel,newchannel;j-
                    # [Translated vendor note] // Vendor note (231202):+PAUSE:10,oldchannel,newchannel;10-screenfluiddpause

                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    if "+PAUSE:1,1" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "1", "SERIAL")
                        self.emit_pause(1, 1)
                        self.G_PauseToLCDString = "+PAUSE:1,1"
                        self.G_Pause1Channel = 1
                    elif "+PAUSE:1,2" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "2", "SERIAL")
                        self.emit_pause(1, 2)
                        self.G_PauseToLCDString = "+PAUSE:1,2"
                        self.G_Pause1Channel = 2
                    elif "+PAUSE:1,3" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "3", "SERIAL")
                        self.emit_pause(1, 3)
                        self.G_PauseToLCDString = "+PAUSE:1,3"
                        self.G_Pause1Channel = 3
                    elif "+PAUSE:1,4" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "4", "SERIAL")
                        self.emit_pause(1, 4)
                        self.G_PauseToLCDString = "+PAUSE:1,3"
                        self.G_Pause1Channel = 4
                    elif "+PAUSE:1,5" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "5", "SERIAL")
                        self.emit_pause(1, 5)
                        self.G_PauseToLCDString = "+PAUSE:1,5"
                        self.G_Pause1Channel = 5
                    elif "+PAUSE:1,6" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "6", "SERIAL")
                        self.emit_pause(1, 6)
                        self.G_PauseToLCDString = "+PAUSE:1,6"
                        self.G_Pause1Channel = 6
                    elif "+PAUSE:1,7" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "7", "SERIAL")
                        self.emit_pause(1, 7)
                        self.G_PauseToLCDString = "+PAUSE:1,7"
                        self.G_Pause1Channel = 7
                    elif "+PAUSE:1,8" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "8", "SERIAL")
                        self.emit_pause(1, 8)
                        self.G_PauseToLCDString = "+PAUSE:1,8"
                        self.G_Pause1Channel = 8
                    elif "+PAUSE:1,9" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "9", "SERIAL")
                        self.emit_pause(1, 9)
                        self.G_PauseToLCDString = "+PAUSE:1,9"
                        self.G_Pause1Channel = 9
                    elif "+PAUSE:1,10" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "10", "SERIAL")
                        self.emit_pause(1, 10)
                        self.G_PauseToLCDString = "+PAUSE:1,10"
                        self.G_Pause1Channel = 10
                    elif "+PAUSE:1,11" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "11", "SERIAL")
                        self.emit_pause(1, 11)
                        self.G_PauseToLCDString = "+PAUSE:1,11"
                        self.G_Pause1Channel = 11
                    elif "+PAUSE:1,12" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "12", "SERIAL")
                        self.emit_pause(1, 12)
                        self.G_PauseToLCDString = "+PAUSE:1,12"
                        self.G_Pause1Channel = 12
                    elif "+PAUSE:1,13" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "13", "SERIAL")
                        self.emit_pause(1, 13)
                        self.G_PauseToLCDString = "+PAUSE:1,13"
                        self.G_Pause1Channel = 13
                    elif "+PAUSE:1,14" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "14", "SERIAL")
                        self.emit_pause(1, 14)
                        self.G_PauseToLCDString = "+PAUSE:1,14"
                        self.G_Pause1Channel = 14
                    elif "+PAUSE:1,15" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "15", "SERIAL")
                        self.emit_pause(1, 15)
                        self.G_PauseToLCDString = "+PAUSE:1,15"
                        self.G_Pause1Channel = 15
                    elif "+PAUSE:1,16" in SerialRxASCIIStr:
                        self.kaos_log("DEBUG", "16", "SERIAL")
                        self.emit_pause(1, 16)
                        self.G_PauseToLCDString = "+PAUSE:1,16"
                        self.G_Pause1Channel = 16
                    else:
                        self.kaos_log(
                            "DEBUG",
                            "self.G_ChangeChannelTimeoutNewChan=%d"
                            % self.G_ChangeChannelTimeoutNewChan,
                            "SERIAL",
                        )
                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:1,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:1,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PauseToLCDString = SerialRxASCIIStr
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:1,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )

            return

        if "+PAUSE:2" in SerialRxASCIIStr:
            self.kaos_log("DEBUG", "pause ACK", "SERIAL")
            # self.emit_protocol("+PAUSE:2,%d" % self.G_ChangeChannelTimeoutNewChan)

            return

        if "+PAUSE:3" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode, pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return

            self.kaos_log("DEBUG", "new printing refilltimeout10s, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:3,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    # Vendor note (240323): prone to jam, disabled for now
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:3,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # special refill state
                        # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:3,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:3,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:3,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:3,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:3,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        if "+PAUSE:5" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "new printing refilltimeout10s, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:5,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    # Vendor note (240323): prone to jam, disabled for now
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:5,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # special refill state
                        # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:5,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:5,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:5,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:5,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:5,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        if "+PAUSE:4" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "new feedtimeout50s, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:4,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # Vendor note (240323): prone to jam, disabled for now
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:4,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # special refill state
                        # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:4,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:4,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:4,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:4,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:4,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        if "+PAUSE:6" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode, pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "entryto the park positiontimeout10s, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:6,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    # Vendor note (240323): prone to jam, disabled for now
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:6,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # special refill state
                        # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:6,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:6,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:6,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:6,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:6,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        if "+PAUSE:7" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode, pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return

            self.kaos_log("DEBUG", "bufferfullstatetimeout30s, pause", "SERIAL")

            self.G_STM32PauseCount += 1
            if self.G_STM32PauseCount == 5:
                self.kaos_log(
                    "DEBUG",
                    "if self.G_STM32PauseCount==5;G_STM32PauseCount=%d" % self.G_STM32PauseCount,
                    "SERIAL",
                )
                self.G_STM32PauseCount = 0
            else:
                self.kaos_log(
                    "DEBUG", "else;G_STM32PauseCount=%d" % self.G_STM32PauseCount, "SERIAL"
                )

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    # Vendor note (240103): after resume, send command to STM32 to restore last state machine state
                    # resume state RS=F, restore last state
                    # resume state RS=0, restore to IDLE_STANDBY
                    # resume state RS=X,...
                    # resume state RS=Y,...
                    # resume state RS=Z,...
                    if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                        self.Cmds_AMSSerial1Send("AT+MARS=F")
                        self.kaos_log(
                            "DEBUG", "pause MA;AT+MARS=F; STM32resume up time state", "SERIAL"
                        )

                    if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
                        self.Cmds_AMSSerial1Send("AT+MCRS=F")
                        self.kaos_log(
                            "DEBUG", "pause MC;AT+MCRS=F; STM32resume up time state", "SERIAL"
                        )

                    # self.G_ProzenToolhead.dwell(1.0)
                    # self.Cmds_AMSSerial1Send("AT+MARS=F")
                    # self.G_PhrozenFluiddRespondInfo("AT+MARS=F")

                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:7,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True

                    # If the toolhead Hall sensor detects filament here, treat it as a likely nozzle-clog symptom during printing
                    if self.G_ToolheadIfHaveFilaFlag == True:
                        self.kaos_log("DEBUG", "purge toolhead detectedfilament, head", "SERIAL")
                        self.G_PauseToLCDString = "+PAUSE:c,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )
                    else:
                        self.kaos_log(
                            "DEBUG",
                            "purge buffer full error, toolhead detectedfilament, class is feed timeout",
                            "SERIAL",
                        )
                        self.G_PauseToLCDString = "+PAUSE:4,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                else:
                    # special refill state
                    # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        # If the toolhead Hall sensor detects filament here, treat it as a likely nozzle-clog symptom during printing
                        if self.G_ToolheadIfHaveFilaFlag == True:
                            self.kaos_log(
                                "DEBUG",
                                "printing toolhead detectedfilament, printing head",
                                "SERIAL",
                            )
                            self.G_PhrozenFluiddRespondInfo(
                                "+PAUSE:7,%d,%d"
                                % (
                                    self.G_ChangeChannelTimeoutOldChan,
                                    self.G_ChangeChannelTimeoutNewChan,
                                )
                            )
                            self.G_PauseToLCDString = "+PAUSE:7,%d,%d" % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        else:
                            self.kaos_log(
                                "DEBUG",
                                "buffer full error, toolhead detectedfilament, class is feed timeout",
                                "SERIAL",
                            )
                            self.G_PhrozenFluiddRespondInfo(
                                "+PAUSE:4,%d,%d"
                                % (
                                    self.G_ChangeChannelTimeoutOldChan,
                                    self.G_ChangeChannelTimeoutNewChan,
                                )
                            )
                            self.G_PauseToLCDString = "+PAUSE:4,%d,%d" % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:7,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:7,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:7,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

            # [Translated vendor note] Vendor note (240103): , stm32
            # [Translated vendor note] RS=F,
            # [Translated vendor note] RS=0,IDLE_STANDBY
            # [Translated vendor note] RS=X,...
            # [Translated vendor note] RS=Y,...
            # [Translated vendor note] RS=Z,...

        if "+PAUSE:a" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "park positionto bufferentrytimeout10s, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            # #if self.G_IfChangeFilaOngoing== False:
            # # Vendor note (240124): STM32-reported pause: allow only once
            # if self.STM32ReprotPauseFlag==0:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause1 time")
            #     self.STM32ReprotPauseFlag=1
            #     self.G_KlipperIfPaused = True
            #     self.G_ChangeChannelFirstFilaFlag=True
            #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            #     self.emit_protocol("+PAUSE:a,%d" % self.G_ChangeChannelTimeoutNewChan)
            #     # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
            #     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
            # else:
            #     self.G_PhrozenFluiddRespondInfo("stm32 move pause up report, pause")
            # Vendor note (240325): during resume, check for pause report
            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    # force-feed first to prevent entry sensor state error
                    # Vendor note (240323): prone to jam, disabled for now
                    # self.Cmds_AMSSerial1Send("E%d" % self.G_ChangeChannelTimeoutNewChan)
                    # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: E%d" % self.G_ChangeChannelTimeoutNewChan)

                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:a,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # special refill state
                        # self.Cmds_AMSSerial1Send("H%d" % self.G_ChangeChannelTimeoutNewChan)
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)]Sending command: H%d" % self.G_ChangeChannelTimeoutNewChan)

                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)a

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:a,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:a,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:a,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:a,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:a,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        # Vendor note (250423): print: nozzle clog detection
        if "+PAUSE:c" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )

                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; toolhead detectedfilament, but purge stm32 pause report error, cannotreturn;",
                        "SERIAL",
                    )
                    self.STM32ReprotPauseFlag = 1
                    # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                    # self.G_ChangeChannelFirstFilaFlag=True
                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    # self.emit_protocol("+PAUSE:c,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    self.G_PauseToLCDString = "+PAUSE:c,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "toolhead head, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:c,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True

                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)a

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:c,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:c,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:a,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:c,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:c,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        # Vendor note (250506): purge: refill error, filament bite mark
        if "+PAUSE:d" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )

                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; toolhead detectedfilament, but refill stm32 pause report error, cannotreturn;",
                        "SERIAL",
                    )
                    self.STM32ReprotPauseFlag = 1
                    # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                    # self.G_ChangeChannelFirstFilaFlag=True
                    # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    # self.emit_protocol("+PAUSE:c,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    self.G_PauseToLCDString = "+PAUSE:d,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "purgerefill error, filamenthas, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:d,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)a

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:d,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:d,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:a,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:d,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:d,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        # //lancaigang250507:+PAUSE:e,oldchannel,newchannel;e-not drying: AMS chamber temp too high, print not allowed
        if "+PAUSE:e" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return

            # Vendor note (250510): not in print mode, klipper pause not allowed, but notify serial display
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                self.kaos_log(
                    "DEBUG",
                    "in printingmode, not allowedpauseklipper, but to prompt show serial port disable",
                    "SERIAL",
                )
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:e,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:e,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )
                return

            self.kaos_log("DEBUG", "state down, AMS internal, not allowedprinting, pause", "SERIAL")

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:e,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)a

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:e,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:e,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:e,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:e,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:e,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        # //lancaigang250507:+PAUSE:f,oldchannel,newchannel;f-drying: print not allowed
        if "+PAUSE:f" in SerialRxASCIIStr:
            # Vendor note (240106): single-color refill: if already paused, do not re-pause
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG",
                        "single-color refill mode MA mode; pause if self.G_KlipperIfPaused == True:",
                        "SERIAL",
                    )
                    return
            # Vendor note (240413): ,ifalready,allow
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                if self.G_KlipperIfPaused == True:
                    self.kaos_log(
                        "DEBUG", "single-color M3 mode, has AMS multi-material, pause:", "SERIAL"
                    )
                    return
            self.kaos_log("DEBUG", "state down, not allowedprinting, pause", "SERIAL")

            # Vendor note (250510): not in print mode, klipper pause not allowed, but notify serial display
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                self.kaos_log(
                    "DEBUG",
                    "in printingmode, not allowedpauseklipper, but to prompt show serial port disable",
                    "SERIAL",
                )
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:f,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:f,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )
                return

            # if screen-initiated pause, ignore STM32 active report
            if self.G_ToolheadIfHaveFilaFlag == True:
                if self.G_IfToolheadHaveFilaInitiativePauseFlag == True:
                    self.kaos_log(
                        "DEBUG", "disable move pause, logical stm32 move up report", "SERIAL"
                    )
                    return
            # if manual command, filter STM32 pause report
            if self.ManualCmdFlag == True or self.G_CutCheckTest == True:
                # Vendor note (240611): manual command also reported to serial display
                self.kaos_log("DEBUG", SerialRxASCIIStr, "SERIAL")
                # self.ManualCmdFlag=False
                self.kaos_log(
                    "DEBUG", "move Test command, logical stm32 move pause up report", "SERIAL"
                )
                return

            self.G_ResumeProcessCheckPauseStatus = True
            self.G_PauseToLCDString = SerialRxASCIIStr
            # Vendor note (240124): STM32-reported pause: allow only once
            if self.STM32ReprotPauseFlag == 0:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                if self.PG102Flag == True:
                    self.kaos_log(
                        "DEBUG",
                        "Purging is in progress. Delay the pause until purging finishes",
                        "SERIAL",
                    )
                    self.PG102DelayPauseFlag = True
                    self.G_PauseToLCDString = "+PAUSE:f,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                else:
                    if self.G_KlipperInPausing == False:
                        self.kaos_log(
                            "DEBUG", "No pause is in progress; a new pause is allowed", "SERIAL"
                        )
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        # Vendor note (231209): handling business in timer causes errors; use thread for interrupt later
                        self.kaos_log("DEBUG", "stm32 move pause up report, pause1 time", "SERIAL")
                        self.kaos_log("DEBUG", "Quick pause enabled", "SERIAL")
                        self.G_KlipperQuickPause = True
                        self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                        self.G_KlipperIfPaused = True
                        self.STM32ReprotPauseFlag = 1
                        # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                        self.G_ChangeChannelFirstFilaFlag = True
                        # self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)a

                        self.G_PhrozenFluiddRespondInfo(
                            "+PAUSE:f,%d,%d"
                            % (
                                self.G_ChangeChannelTimeoutOldChan,
                                self.G_ChangeChannelTimeoutNewChan,
                            )
                        )
                        self.G_PauseToLCDString = "+PAUSE:f,%d,%d" % (
                            self.G_ChangeChannelTimeoutOldChan,
                            self.G_ChangeChannelTimeoutNewChan,
                        )

                    else:
                        self.kaos_log(
                            "DEBUG",
                            "A pause is already in progress; a new pause is not allowed",
                            "SERIAL",
                        )

            else:
                self.G_PauseTriggerWhileChangeChannelFlag = True
                self.kaos_log("DEBUG", "stm32 move pause up report, pause", "SERIAL")
                # Vendor note (240325): repeated pause, still report to serial display
                # self.emit_protocol("+PAUSE:a,%d" % self.G_ChangeChannelTimeoutNewChan)
                # self.G_PhrozenFluiddRespondInfo(self.G_PauseToLCDString)
                self.G_PhrozenFluiddRespondInfo(
                    "+PAUSE:f,%d,%d"
                    % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                )
                self.G_PauseToLCDString = "+PAUSE:f,%d,%d" % (
                    self.G_ChangeChannelTimeoutOldChan,
                    self.G_ChangeChannelTimeoutNewChan,
                )

            return

        if "+FORCEFORWARD:1" in SerialRxASCIIStr:
            self.kaos_log("DEBUG", "get output toolhead filament tube, get output", "SERIAL")
            return

        # if STM32 pause response received, pause klipper

        # // CS device id  run mode  prev mc state  current mc state  channel
        # // CS00       N0      M09         T09         C5
        # // CS00       N0      M02         T03         C0
        # // CS00       N0      M08         T10         C1
        #    deviceid   mode    pre_state   state       chan
        # regexparsedata
        # CS00N0M03T04C0
        message_obj = re.match(
            AMS_SERIALPORT_RECEIV_PARSE_PATTERN,  # regex
            SerialRxASCIIStr,
            re.M | re.I,
        )

        # parsed serial data error
        if not message_obj:
            return

        if int(message_obj.group("mode")) is AMS_MC_MODE:
            self.kaos_log("DEBUG", "mode==AMS mode==%d" % AMS_MC_MODE, "SERIAL")
        if int(message_obj.group("mode")) is AMS_MA_MODE:
            self.kaos_log("DEBUG", "mode==refill mode==%d" % AMS_MA_MODE, "SERIAL")

        if int(message_obj.group("state")) is MC_STANDBY:
            self.kaos_log("DEBUG", "current statestate== machine ==%d" % MC_STANDBY, "SERIAL")
        if int(message_obj.group("state")) is MC_PREPARTION:
            self.kaos_log("DEBUG", "current statestate====%d" % MC_STANDBY, "SERIAL")
        if int(message_obj.group("state")) is MC_CHANGING_P1:
            self.kaos_log("DEBUG", "current statestate==1==%d" % MC_CHANGING_P1, "SERIAL")
        if int(message_obj.group("state")) is MC_CHANGING_P2:
            self.kaos_log("DEBUG", "current statestate==2==%d" % MC_CHANGING_P2, "SERIAL")
        if int(message_obj.group("state")) is MC_FORCE_FEED:
            self.kaos_log("DEBUG", "current statestate==refill==%d" % MC_FORCE_FEED, "SERIAL")
        if int(message_obj.group("state")) is MC_PRINTING:
            self.kaos_log("DEBUG", "current statestate==refill==%d" % MC_PRINTING, "SERIAL")
        if int(message_obj.group("state")) is MC_ROLLBACK:
            self.kaos_log("DEBUG", "current statestate== full unload==%d" % MC_ROLLBACK, "SERIAL")
        if int(message_obj.group("state")) is MC_PARKBACK:
            self.kaos_log(
                "DEBUG", "current statestate==unloadto park position==%d" % MC_PARKBACK, "SERIAL"
            )
        if int(message_obj.group("state")) is MC_PARKALL:
            self.kaos_log(
                "DEBUG",
                "current statestate== full all unloadto park position==%d" % MC_PARKALL,
                "SERIAL",
            )
        if int(message_obj.group("state")) is MC_CLEANING:
            self.kaos_log(
                "DEBUG", "current statestate==all filamentclear==%d" % MC_CLEANING, "SERIAL"
            )
        if int(message_obj.group("state")) is MC_ERR_TIMEOUT:
            self.kaos_log(
                "DEBUG",
                "current statestate==timeout output error state==%d" % MC_ERR_TIMEOUT,
                "SERIAL",
            )
        if int(message_obj.group("state")) is MC_ERR_RUNOUT:
            self.kaos_log(
                "DEBUG",
                "current statestate==filament runout output error state==%d" % MC_ERR_RUNOUT,
                "SERIAL",
            )
        if int(message_obj.group("state")) is MC_ERR_BLOCKUP:
            self.kaos_log(
                "DEBUG", "current statestate== output error state==%d" % MC_ERR_BLOCKUP, "SERIAL"
            )
            # raise self.error("")
            # self.Cmds_PhrozenKlipperPause(None)

        self.kaos_log("DEBUG", "machine chan==%d" % int(message_obj.group("chan")), "SERIAL")
        # raise self.error(";")

        # Vendor note (20231013): filament change handling; jam, re-feed
        if int(message_obj.group("mode")) is AMS_MC_MODE:
            # Vendor note (20231114): repeated re-feed retries occur, disable for now
            cur_chan = int(message_obj.group("chan")) + 1
            # # Vendor note (20231013): filament change phase 2-->
            # if (int(message_obj.group("pre_state")) is MC_CHANGING_P2) and (int(message_obj.group("state")) is MC_FORCE_FEED):
            #     # Vendor note (20231013): no toolhead filament but buffer full: jam, retract and re-feed
            #     if not self.G_ToolheadIfHaveFilaFlag:
            #         self.AMSErrorRetryTimes += 1
            #         if self.AMSErrorRetryTimes < 5:
            #             #// =====T1~Tn;PRZ_T[n] P1 T[n]n:1 ~32(device,1 ~4),()
            #             self.Cmds_AMSSerial1Send("T%d" % cur_chan)
            #             self.G_PhrozenFluiddRespondInfo("Filament change: toolhead not detected, T? retry; cmd T%s at %d times" % (cur_chan, self.AMSErrorRetryTimes))
            #         else:
            #             self.G_PhrozenFluiddRespondInfo("Filament change: toolhead not detected, T? retried 5 times, P? retract to park")
            #             #// ;// =====P1 D[n];n:1~32(device,1~4); Yes;====="P?";
            #             self.Cmds_AMSSerial1Send("P%d" % cur_chan)
            #             self.Cmds_PhrozenKlipperPause(None)
            #             self.AMSErrorRetryTimes = 0
            #     # Vendor note (20231013): filament detected on toolhead
            #     else:
            #         # after state OK, reset error retry count
            #         self.AMSErrorRetryTimes = 0

            #     return self.G_PhrozenReactor.NOW + AMS_SERIALPORT_RECV_TIMER

            # Vendor note (231103): disable STM32 timeout state handling for now, causes execution disorder
            # Vendor note (20231013): STM32 timeout state handling
            # if int(message_obj.group("state")) is MC_ERR_TIMEOUT:
            #     # typedef enum Enum_MCStateMachine {
            #     #     // 00; Idlestandby phase
            #     #     MCSTATEMACHINE_IDLE_STANDBY,
            #     #     // 01; park position to printer feed phase;// =====P1 S0 , canretract to park;====="RD";
            #     #     MCSTATEMACHINE_PARKPOSITION_ISREADY_INFILA_TO_PRINTER,
            #     #     // 02; filament change phase 1;// =====P1 T[n]n:1 ~32(device,1 ~4),();====="T?";
            #     #     MCSTATEMACHINE_CHANGING_FILA_STAGE_P1,
            #     #     // 03; filament change phase 2;// =====P1 T[n]n:1 ~32(device,1 ~4),();====="T?";
            #     #     MCSTATEMACHINE_CHANGING_FILA_STAGE_P2,
            #     #     // 04; force-feed to printhead,P1 T?
            #     #     MCSTATEMACHINE_FORCE_FEED_INFILA_TO_PRINTER,
            #     #     // 05; printing phase (refill)
            #     #     MCSTATEMACHINE_PRINTING_INPROCESS_FEED,
            #     #     // 06; full retract;// =====B1~Bn;PRZ_B[n] P1 B[n]n:1 ~32(device,1 ~4)exit Yes
            #     #     MCSTATEMACHINE_FULLY_ROLLBACK,
            #     #     // 07; retract to park;//"P";P1 D[n];n:1~32(device,1~4); Yes
            #     #     MCSTATEMACHINE_ROLLBACK_TO_PARKPOSITION,
            #     #     // 08; all retract to park;// "AP";P2 A1  Yes
            #     #     MCSTATEMACHINE_ROLLBACK_ALL_TO_PARKPOSITION,
            #     #     // 09; clear all filaments;//====="CL"; P2 A2;exitfilament Yes
            #     #     MCSTATEMACHINE_CLEAN_ALL_CHANNEL,
            #     #     // 10; timeout error state
            #     #     MCSTATEMACHINE_ERROR_TIMEOUT,
            #     #     // 11; runout error state
            #     #     MCSTATEMACHINE_ERROR_RUNOUT,
            #     # } Enum_MCStateMachine;
            #     self.AMSErrorRetryTimes += 1
            #     if self.AMSErrorRetryTimes < 5:
            #         #// =====T1~Tn;PRZ_T[n] P1 T[n]n:1 ~32(device,1 ~4),()
            #         self.G_PhrozenFluiddRespondInfo("STM32 error state, T? command retry; cmd T%s at %d times" % (message_obj.group("chan"), self.AMSErrorRetryTimes))
            #         self.Cmds_AMSSerial1Send("T%d" % cur_chan)
            #     else:
            #         self.G_PhrozenFluiddRespondInfo("STM32 error state, T? command retried 5 times, P? command retract to park")
            #         #// ;// =====P1 D[n];n:1~32(device,1~4); Yes;====="P?";
            #         self.Cmds_AMSSerial1Send("P%d" % cur_chan)
            #         self.Cmds_PhrozenKlipperPause(None)
            #         self.AMSErrorRetryTimes = 0

            #     return self.G_PhrozenReactor.NOW + AMS_SERIALPORT_RECV_TIMER

        # Vendor note (20231013): refill mode
        if int(message_obj.group("mode")) is AMS_MA_MODE:
            pass

    # Vendor note (20231013): serial receive handler periodic timer
    # 100ms
    def Device_TimmerUart1Recv(self, eventtime):
        # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerUart1Recv]")
        # Vendor note (240427): try catch
        try:
            # if self.G_SerialPort1OpenFlag==False:
            #     self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerUart1Recv]Serial port 1 already closed")
            # if self.G_SerialPort2OpenFlag==False:
            #     self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerUart1Recv]Serial port 2 already closed")

            # tty1 connect failed
            if self.G_SerialPort1OpenFlag == False:
                self.G_ASM1DisconnectErrorCount = 0
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerUart1Recv]Serial port 1 connection error, exit callback permanently")
                # self.G_PhrozenFluiddRespondInfo("self.G_AMS1ErrorRestartCount=%d" % self.G_AMS1ErrorRestartCount)
                try:
                    if self.G_SerialPort1Obj is not None:
                        if self.G_SerialPort1Obj.is_open:
                            # tty1 closed
                            self.G_SerialPort1Obj.close()
                            self.kaos_log("DEBUG", "close serial port 1 successful", "SERIAL")
                            self.kaos_log("DEBUG", "AMS1 connectedfailed", "SERIAL")
                            # self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                            self.kaos_log("DEBUG", "pause command+PAUSE:g", "SERIAL")
                except:
                    self.kaos_log("DEBUG", "close serial port 1 error", "SERIAL")

                self.G_AMS1ErrorRestartCount = self.G_AMS1ErrorRestartCount + 1

                # Vendor note (241108): delay before pause, allow AMS restart time
                if self.G_AMS1ErrorRestartCount >= 5:
                    # self.G_PhrozenFluiddRespondInfo("if self.G_AMS1ErrorRestartCount>=5:")

                    self.G_AMS1ErrorRestartCount = 0
                    # if USB error, report only on filament-change error
                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )
                    # self.G_PhrozenFluiddRespondInfo("pause command+PAUSE:g")

                    # if self.G_KlipperIfPaused==False:
                    #     self.G_KlipperIfPaused = True
                    #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #     if self.G_CancelFlag==False:
                    #         # self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #         # self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #         self.G_PhrozenFluiddRespondInfo("AMS1 connectederrorpause")

                    #         # Vendor note (250604): #         if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:#M0
                    #             self.G_PhrozenFluiddRespondInfo("Unknown mode, do notpause")
                    #         else:
                    #             if self.STM32ReprotPauseFlag==0:
                    #                 self.G_PauseTriggerWhileChangeChannelFlag=True
                    #                 if self.PG102Flag==True:
                    #                     self.G_PhrozenFluiddRespondInfo("Purging is in progress. Delay the pause until purging finishes")
                    #                     self.PG102DelayPauseFlag=True
                    #                     #self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #                     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #                 else:
                    #                     self.G_PhrozenFluiddRespondInfo("No purge in progress; can pause immediately")
                    #                     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #                     self.G_KlipperIfPaused = True
                    #                     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #                     self.STM32ReprotPauseFlag=1
                    #                     # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                    #                     self.G_ChangeChannelFirstFilaFlag=True
                    #                     self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #                     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #             else:
                    #                 self.G_PauseTriggerWhileChangeChannelFlag=True
                    #                 self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)

                    #         #     self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #         # Vendor note (20231013): disconnect
                    #         self.Device_DisconnectAMSDevice()

                    # #if self.G_KlipperIfPaused==True:
                    # else:
                    #     self.G_PhrozenFluiddRespondInfo("USBerror, currentalready paused")
                    #     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)

                    # Vendor note (240524): exit callback permanently
                    return self.G_PhrozenReactor.NEVER

                return eventtime + AMS_SERIALPORT_RECV_TIMER

            # Vendor note (250619): USB connection OK, clear
            # self.G_PauseToLCDString=""
            self.G_AMS1ErrorRestartCount = 0

            # # Vendor note (240427): AMS error restart, needs logging
            # if self.G_AMS1ErrorRestartFlag == True:
            #     self.G_PhrozenFluiddRespondInfo("AMS1 error or restart; self.G_AMSErrorRestartCount=%d" % self.G_AMSErrorRestartCount)
            #     self.emit_protocol("+AMSReboot:%d" % self.G_AMSErrorRestartCount)
            #     self.G_AMS1ErrorRestartFlag = False

            #     try:
            #         self.G_PhrozenFluiddRespondInfo("Reinitializing serial port 1")
            #         self.G_SerialPort1Obj = serial.Serial(self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3)
            #         #serial port 1 opened successfully
            #         if self.G_SerialPort1Obj.is_open:
            #             self.G_SerialPort1OpenFlag = True
            #             self.G_PhrozenFluiddRespondInfo("Reinitializing serial port 1 successful")
            #             # Vendor note (231213): open serial port1
            #             self.G_SerialPort1Obj.flushInput()  # clean serial write cache
            #             self.G_SerialPort1Obj.flush()
            #             self.G_PhrozenFluiddRespondInfo("Serial port 1 buffers cleared")
            #             self.G_PhrozenFluiddRespondInfo("Re-registering serial port 1 callback")
            #             self.G_SerialPort1RecvTimmer = self.G_PhrozenReactor.register_timer(self.Device_TimmerUart1Recv, self.G_PhrozenReactor.NOW)
            #     except:
            #         self.G_PhrozenFluiddRespondInfo("Unable to open tty1. Check the USB connection or try rebooting.")

            #     return eventtime + AMS_SERIALPORT_RECV_TIMER

            # # Vendor note (240410): # if self.G_CancelFlag==True:
            #     #self.G_PhrozenFluiddRespondInfo("Print cancelled")
            #     return eventtime + AMS_SERIALPORT_RECV_TIMER

            # Vendor note (231103): tty1 serial data available
            if self.G_SerialPort1Obj.inWaiting() > 0:
                self.kaos_log("DEBUG", "Current mode", "SERIAL")
                if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                    self.emit_mode(0, "unkown")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
                    self.emit_mode(1, "MC")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                    self.emit_mode(2, "MA")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                    self.emit_mode(3, "RUNOUT")
                else:
                    self.emit_mode(-1, "error")

                self.kaos_log(
                    "DEBUG",
                    "[(dev.python)Device_TimmerUart1Recv]serial port 1 read get number data",
                    "SERIAL",
                )
                Lo_SerialRxLen = self.G_SerialPort1Obj.inWaiting()
                self.kaos_log("DEBUG", "byte count Lo_SerialRxLen=%d" % Lo_SerialRxLen, "SERIAL")
                # self.G_PhrozenFluiddRespondInfo("Serial port timer receive")
                Lo_SerialRxBytes = self.G_SerialPort1Obj.read(Lo_SerialRxLen)
                self.kaos_log(
                    "DEBUG", "byte streamLo_SerialRxBytes=%s" % Lo_SerialRxBytes, "SERIAL"
                )
                self.kaos_log(
                    "DEBUG",
                    "byte streambinascii.hexlify(Lo_SerialRxBytes)=%s"
                    % binascii.hexlify(Lo_SerialRxBytes),
                    "SERIAL",
                )
                # self.G_PhrozenFluiddRespondInfo("%x" % binascii.hexlify(Lo_SerialRxBytes))
                self.kaos_log(
                    "DEBUG", "byte countlen(Lo_SerialRxBytes)=%d" % len(Lo_SerialRxBytes), "SERIAL"
                )
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes.count=%d" % Lo_SerialRxBytes.count)
                # for i in Lo_SerialRxBytes:
                # self.G_PhrozenFluiddRespondInfo("%x" % i)

                self.kaos_log(
                    "DEBUG", "Lo_SerialRxBytes[0] - hex byte0x%2x" % Lo_SerialRxBytes[0], "SERIAL"
                )
                self.kaos_log(
                    "DEBUG",
                    "Lo_SerialRxBytes[0] - ASCII character%c" % Lo_SerialRxBytes[0],
                    "SERIAL",
                )
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes[1] - hex byte 0x%2x" % Lo_SerialRxBytes[1])
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes[1] - ASCII character %c" % Lo_SerialRxBytes[1])

                # Vendor note (240705): AMS multi-material present
                self.G_AMSDevice1IfNormal = True

                try:
                    # Vendor note (250411): AMS state report
                    # if "R" in self.G_SerialRxASCIIStr:
                    if Lo_SerialRxBytes[0] == 0x52 and Lo_SerialRxLen == 16:
                        self.kaos_log("DEBUG", "AMS unit 1 async response", "SERIAL")

                        # self.G_PhrozenFluiddRespondInfo("%s" % SerialRxASCIIStr)
                        Lo_AMSDeviceStateInfo = AMSDetailInfoBytes()
                        Lo_AMSDeviceStateInfo.whole[:] = Lo_SerialRxBytes
                        # empty Python dict
                        Lo_AMSDetailState = {}
                        self.G_AMS1DeviceState["dev_id"] = Lo_AMSDetailState["dev_id"] = (
                            Lo_AMSDeviceStateInfo.field.dev_id
                        )
                        self.G_AMS1DeviceState["active_dev_id"] = Lo_AMSDetailState[
                            "active_dev_id"
                        ] = Lo_AMSDeviceStateInfo.field.active_dev_id
                        self.G_AMS1DeviceState["dev_mode"] = Lo_AMSDetailState["dev_mode"] = (
                            Lo_AMSDeviceStateInfo.field.dev_mode
                        )
                        self.G_AMS1DeviceState["cache_empty"] = Lo_AMSDetailState["cache_empty"] = (
                            Lo_AMSDeviceStateInfo.field.cache_empty
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor empty state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_empty)
                        self.G_AMS1DeviceState["cache_full"] = Lo_AMSDetailState["cache_full"] = (
                            Lo_AMSDeviceStateInfo.field.cache_full
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor full state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_full)
                        self.G_AMS1DeviceState["cache_exist"] = Lo_AMSDetailState["cache_exist"] = (
                            Lo_AMSDeviceStateInfo.field.cache_exist
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor filament state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_exist)
                        self.G_AMS1DeviceState["mc_state"] = Lo_AMSDetailState["mc_state"] = (
                            Lo_AMSDeviceStateInfo.field.mc_state
                        )
                        self.G_AMS1DeviceState["ma_state"] = Lo_AMSDetailState["ma_state"] = (
                            Lo_AMSDeviceStateInfo.field.ma_state
                        )
                        self.G_AMS1DeviceState["entry_state"] = Lo_AMSDetailState["entry_state"] = (
                            Lo_AMSDeviceStateInfo.field.entry_state
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Entry position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.entry_state)
                        self.G_AMS1DeviceState["park_state"] = Lo_AMSDetailState["park_state"] = (
                            Lo_AMSDeviceStateInfo.field.park_state
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Park position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.park_state)

                        # response data JSON conversion
                        self.kaos_log("DEBUG", json.dumps(Lo_AMSDetailState), "SERIAL")

                        self.kaos_log("DEBUG", "P114 successful", "SERIAL")
                        self.emit_p114(1)
                        self.G_P114RunFlag = 0

                    else:
                        self.kaos_log("DEBUG", "AMS file", "SERIAL")
                        # Vendor note (20231013): read ttyUSB0 serial bytes, convert to ASCII
                        # Vendor note (240530): hex bytes to ASCII characters
                        self.G_SerialRxASCIIStr = Lo_SerialRxBytes.decode("ascii")
                        self.kaos_log(
                            "DEBUG",
                            "ASCII character self.G_SerialRxASCIIStr=%s" % self.G_SerialRxASCIIStr,
                            "SERIAL",
                        )

                        # Vendor note (250411): AMSfirmware version

                        # // AMS board 2 firmware-1 1
                        if "V-H18-I18-F" in self.G_SerialRxASCIIStr:
                            self.kaos_log("DEBUG", "AMS code disable unit 1 file", "SERIAL")
                            # =====DriveCodeFile.dat
                            # 1 , 18 , 24053 , 18 , 0# // AMS board 1 firmware-18
                            # 2 , 18 , 24053 , 18 , 0# // AMS board 2 firmware-18
                            # 3 , 18 , 24053 , 18 , 0# // AMS board 3 firmware-18
                            # 4 , 18 , 24053 , 18 , 0# // AMS board 4 firmware-18
                            # 5 , 5 , 24046 , 5 , 0# // OTA sub-program - AMS serial upgrade-5 5
                            # 6 , 0 , 0 , 0 , 0# // buffer board firmware-6 6
                            # 7 , 7 , 24051 , 7 , 0# // 16-color HUB board firmware-7 7
                            # 8 , 0 , 0 , 0 , 0
                            # 9 , 0 , 0 , 0 , 0
                            # 10 , 10 , 24054 , 10 , 0# // OTA sub-program - TJC display background-10
                            # 11 , 11 , 24047 , 11 , 0# // TJC serial display HMI firmware-11
                            # 12 , 0 , 0 , 0 , 0
                            # 13 , 0 , 0 , 0 , 0
                            # 14 , 0 , 0 , 0 , 0
                            # 15 , 15 , 25042 , 15 , 0
                            # 16 , 16 , 25042 , 16 , 0
                            # 17 , ? , 25042 , ? , 0
                            # 18 , ? , 25042 , ? , 0
                            # 19 , ? , 25042 , ? , 0
                            # 20 , ? , 25042 , ? , 0
                            # topic: c0f535790a90/GetZbGwInfo_Respon
                            # {
                            #     "Data_ID": 95,
                            #     "Data": {
                            #         "GwId": "c0f535790a90",
                            #         "HomeId": "",
                            #         "GWSN": "0000000000000000000",
                            #         "AccountId": "",
                            #         "GwMac": "c0f535790a90",
                            #         "GwIP": "192.168.3.53",
                            #         "GwName": "Name-c0f535790a90",
                            #         "ProductId": "ARCO",
                            #         "MainImage": 15,
                            #         "MainHWVersion": 15,
                            #         "MainFWVersion": 24064,
                            #         "Gw_Ram": 248584,
                            #         "Gw_Rom": 826536,
                            #         "JoinMode": 1,
                            #         "ESSID": "",
                            #         "MqttClientEMQfd": 31,
                            #         "MqttClientId": "c0f535790a90",
                            #         "MqttBrokerUserName": "",
                            #         "MqttBrokerPwd": "",
                            #         "DriveCodeList": [
                            #             {
                            #                 "DriveCode": 1,
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
                            #                 "DriveCode": 3,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
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
                            #                 "DriveCode": 5,
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
                            #                 "DriveCode": 7,
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
                            #                 "DriveCode": 9,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 10,
                            #                 "DriveImageType": 10,
                            #                 "DriveHwVersion": 10,
                            #                 "DriveFwVersion": 25033,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 11,
                            #                 "DriveImageType": 11,
                            #                 "DriveHwVersion": 11,
                            #                 "DriveFwVersion": 25022,
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
                            #                 "DriveCode": 13,
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
                            #                 "DriveCode": 15,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 16,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 17,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 18,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 19,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 20,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             }
                            #         ]
                            #     }
                            # }
                            # Vendor note (250724): read system image id to distinguish product/board/firmware variants
                            # Vendor note (250724): read image id
                            self.Cmds_GetImageId()
                            if self.G_ImageId == 16:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==16: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"
                            elif self.G_ImageId == 31:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==31: ARCO300-phrozen-RK3308-STM32F407VET6-I31",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/prz/hdlDat/DriveCodeFile.dat"
                            elif self.G_ImageId == -1:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==-1, default: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID could not be read, default: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"

                            self.kaos_log("DEBUG", "filename=%s" % filename, "SERIAL")
                            Lo_AllLine = ""
                            # data = [{"DriveCode":16,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":15,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":14,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":13,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":12,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":11,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":10,"DriveImageType":10,"DriveHwVersion":10,"DriveFwVersion":24045,"DriveId":0},{"DriveCode":9,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":8,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":7,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":6,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":5,"DriveImageType":5,"DriveHwVersion":5,"DriveFwVersion":24046,"DriveId":0},{"DriveCode":4,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":3,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":2,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":1,"DriveImageType":1,"DriveHwVersion":1,"DriveFwVersion":24042,"DriveId":0}]
                            # f = open(filename, 'a')
                            # json.dump(data, f)  #object
                            # f.close()
                            with open(filename, "r") as file:
                                # for line in file:
                                # # realine() read, "\n"
                                # self.G_PhrozenFluiddRespondInfo(file.readline().strip())
                                # #time.sleep(1)
                                Lo_FileDataList = file.readlines()
                                for line in Lo_FileDataList:
                                    # split = [i[:-1].split(',') for i in file.readlines()]
                                    # self.G_PhrozenFluiddRespondInfo(type(split))
                                    # self.G_PhrozenFluiddRespondInfo(split[1])
                                    # self.G_PhrozenFluiddRespondInfo(split[2])
                                    # self.G_PhrozenFluiddRespondInfo(split[3])
                                    # line_strip=line.strip()
                                    # self.G_PhrozenFluiddRespondInfo(line)
                                    # self.G_PhrozenFluiddRespondInfo("line.count=%d" % line.count)
                                    split = line.split(",")
                                    # self.G_PhrozenFluiddRespondInfo(type(split))
                                    # self.G_PhrozenFluiddRespondInfo("".join(split))
                                    # self.G_PhrozenFluiddRespondInfo(split[0])
                                    # 1 , 18 , 24053 , 18 , 0
                                    split[0] = split[0].strip()  # driver number
                                    split[1] = split[1].strip()  # hardware id
                                    split[2] = split[2].strip()  # firmware version
                                    split[3] = split[3].strip()  # image id
                                    split[4] = split[4].strip()  # online status
                                    # split[4]='0'#online status,default0
                                    # if "SN1" in self.G_SerialRxASCIIStr:
                                    if split[0] == "1":
                                        self.kaos_log(
                                            "DEBUG", "AMS code disable unit 1 file", "SERIAL"
                                        )
                                        self.kaos_log("DEBUG", split[0], "SERIAL")
                                        self.kaos_log("DEBUG", split[1], "SERIAL")
                                        self.kaos_log("DEBUG", split[2], "SERIAL")
                                        self.kaos_log("DEBUG", split[3], "SERIAL")
                                        self.kaos_log("DEBUG", split[4], "SERIAL")
                                        # line=("%d,%d,%d," % (HW_VERSION,,))
                                        line_modify = (
                                            split[0]
                                            + ","
                                            + "18"
                                            + ","
                                            + self.G_SerialRxASCIIStr[11:16]
                                            + ","
                                            + "18"
                                            + ","
                                            + "1"
                                        )
                                        self.kaos_log("DEBUG", line_modify, "SERIAL")
                                        Lo_AllLine = Lo_AllLine + line_modify + "\r\n"  # 0x0D 0x0A
                                    else:
                                        Lo_AllLine = Lo_AllLine + line
                                    # if "SN2" in self.G_SerialRxASCIIStr:
                                    #     if split[0] == "2":
                                    #         self.G_PhrozenFluiddRespondInfo(split[0])
                                    #         self.G_PhrozenFluiddRespondInfo(split[1])
                                    #         self.G_PhrozenFluiddRespondInfo(split[2])
                                    #         self.G_PhrozenFluiddRespondInfo(split[3])
                                    #         self.G_PhrozenFluiddRespondInfo(split[4])
                                    #         #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #         line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #         self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #         Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    #     else:
                                    #         Lo_AllLine=Lo_AllLine+line
                                    # if "SN3" in self.G_SerialRxASCIIStr:
                                    #     if split[0] == "3":
                                    #         self.G_PhrozenFluiddRespondInfo(split[0])
                                    #         self.G_PhrozenFluiddRespondInfo(split[1])
                                    #         self.G_PhrozenFluiddRespondInfo(split[2])
                                    #         self.G_PhrozenFluiddRespondInfo(split[3])
                                    #         self.G_PhrozenFluiddRespondInfo(split[4])
                                    #         #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #         line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #         self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #         Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    #     else:
                                    #         Lo_AllLine=Lo_AllLine+line
                                    # if "SN4" in self.G_SerialRxASCIIStr:
                                    #     if split[0] == "4":
                                    #         self.G_PhrozenFluiddRespondInfo(split[0])
                                    #         self.G_PhrozenFluiddRespondInfo(split[1])
                                    #         self.G_PhrozenFluiddRespondInfo(split[2])
                                    #         self.G_PhrozenFluiddRespondInfo(split[3])
                                    #         self.G_PhrozenFluiddRespondInfo(split[4])
                                    #         #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #         line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #         self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #         Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    #     else:
                                    #         Lo_AllLine=Lo_AllLine+line
                            # self.G_PhrozenFluiddRespondInfo(Lo_AllLine)
                            with open(filename, "w+") as file_w:
                                file_w.write(Lo_AllLine)

                        self.Device_TimmerUartRecvHandler(
                            1, Lo_SerialRxBytes, self.G_SerialRxASCIIStr
                        )

                except:
                    self.kaos_log("DEBUG", "serial port number data error, noneAMSstate", "SERIAL")

            return eventtime + AMS_SERIALPORT_RECV_TIMER

        except Exception as e:
            self.kaos_log(
                "DEBUG",
                "serial port 1 read get error, AMS1 error or restart, please checkAMS1 is no normal normal",
                "SERIAL",
            )
            self.kaos_log("DEBUG", "Current mode", "SERIAL")
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                self.emit_mode(0, "unkown")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
                self.emit_mode(1, "MC")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                self.emit_mode(2, "MA")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                self.emit_mode(3, "RUNOUT")
            else:
                self.emit_mode(-1, "error")
            # if AMS error restart, log it and send STM32 slow-feed command after restart
            # Vendor note (240427): AMS error restart, needs logging
            self.G_AMS1ErrorRestartFlag = True
            self.G_AMS1ErrorRestartCount = self.G_AMS1ErrorRestartCount + 1

            # Vendor note (241011): serial error, cannot send data
            self.G_SerialPort1OpenFlag = False

            # Vendor note (240521): on resume: if AMS restart detected (hot-plug), execute full retract/change
            self.G_ResumeCheckAMS1ErrorRestartFlag = True

            return eventtime + AMS_SERIALPORT_RECV_TIMER

    # 100ms
    def Device_TimmerUart2Recv(self, eventtime):
        try:
            # tty2 connect failed
            if self.G_SerialPort2OpenFlag == False:
                self.G_ASM1DisconnectErrorCount = 0
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerUart2Recv]Serial port 2 connection error, exit callback permanently")
                # self.G_PhrozenFluiddRespondInfo("self.G_AMS2ErrorRestartCount=%d" % self.G_AMS2ErrorRestartCount)

                self.G_AMS2ErrorRestartCount = self.G_AMS2ErrorRestartCount + 1

                try:
                    if self.G_SerialPort2Obj is not None:
                        if self.G_SerialPort2Obj.is_open:
                            # tty2 closed
                            self.G_SerialPort2Obj.close()
                            self.kaos_log("DEBUG", "close serial port 2 successful", "SERIAL")
                            self.kaos_log("DEBUG", "AMS2 connectedfailed", "SERIAL")
                            self.kaos_log("DEBUG", "pause command+PAUSE:g", "SERIAL")
                except:
                    self.kaos_log("DEBUG", "close serial port 2 error", "SERIAL")

                # Vendor note (241108): delay before pause, allow AMS restart time
                if self.G_AMS2ErrorRestartCount >= 5:
                    # self.G_PhrozenFluiddRespondInfo("if self.G_AMS2ErrorRestartCount>=5:")

                    self.G_AMS2ErrorRestartCount = 0
                    # if USB error, report only on filament-change error
                    self.G_PauseToLCDString = "+PAUSE:g,%d,%d" % (
                        self.G_ChangeChannelTimeoutOldChan,
                        self.G_ChangeChannelTimeoutNewChan,
                    )

                    # if self.G_KlipperIfPaused==False:
                    #     self.G_KlipperIfPaused = True
                    #     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #     if self.G_CancelFlag==False:
                    #         # self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #         # self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #         self.G_PhrozenFluiddRespondInfo("AMS2 connection error, pause")

                    #         # Vendor note (250604): #         if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:#M0
                    #             self.G_PhrozenFluiddRespondInfo("Unknown mode, do notpause")
                    #         else:
                    #             if self.STM32ReprotPauseFlag==0:
                    #                 self.G_PauseTriggerWhileChangeChannelFlag=True
                    #                 if self.PG102Flag==True:
                    #                     self.G_PhrozenFluiddRespondInfo("Purging is in progress. Delay the pause until purging finishes")
                    #                     self.PG102DelayPauseFlag=True
                    #                     #self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #                     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #                 else:
                    #                     self.G_PhrozenFluiddRespondInfo("No purge in progress; can pause immediately")
                    #                     self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #                     self.G_KlipperIfPaused = True
                    #                     #self.Cmds_PhrozenKlipperPauseNoneCmdToSTM32(None)
                    #                     self.STM32ReprotPauseFlag=1
                    #                     # Vendor note (231202): P1 C?auto filament change,if1,if,continue1start
                    #                     self.G_ChangeChannelFirstFilaFlag=True
                    #                     self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #                     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)
                    #             else:
                    #                 self.G_PauseTriggerWhileChangeChannelFlag=True
                    #                 self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)

                    #         #     self.emit_protocol("+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan))
                    #         # Vendor note (20231013): disconnect
                    #         self.Device_DisconnectAMSDevice()

                    # #if self.G_KlipperIfPaused==True:
                    # else:
                    #     self.G_PhrozenFluiddRespondInfo("USBerror, currentalready paused")
                    #     self.G_PauseToLCDString="+PAUSE:g,%d,%d" % (self.G_ChangeChannelTimeoutOldChan,self.G_ChangeChannelTimeoutNewChan)

                    # Vendor note (240524): exit callback permanently
                    return self.G_PhrozenReactor.NEVER

                return eventtime + AMS_SERIALPORT_RECV_TIMER

            # Vendor note (250619): USB connection OK, clear
            # self.G_PauseToLCDString=""
            self.G_AMS2ErrorRestartCount = 0

            if self.G_CancelFlag == True:
                # self.G_PhrozenFluiddRespondInfo("[(dev.python)Device_TimmerRunoutCheck]Print cancelled")
                return eventtime + AMS_SERIALPORT_RECV_TIMER

            # # Vendor note (240427): AMS error restart, needs logging
            # if self.G_AMS1ErrorRestartFlag == True:
            #     self.G_PhrozenFluiddRespondInfo("AMS1 error or restart; self.G_AMSErrorRestartCount=%d" % self.G_AMSErrorRestartCount)
            #     self.emit_protocol("+AMSReboot:%d" % self.G_AMSErrorRestartCount)
            #     self.G_AMS1ErrorRestartFlag = False

            #     try:
            #         self.G_PhrozenFluiddRespondInfo("Reinitializing serial port 1")
            #         self.G_SerialPort1Obj = serial.Serial(self.G_Serialport1Define, SERIAL_PORT_BAUD, timeout=3)
            #         #serial port 1 opened successfully
            #         if self.G_SerialPort1Obj.is_open:
            #             self.G_SerialPort1OpenFlag = True
            #             self.G_PhrozenFluiddRespondInfo("Reinitializing serial port 1 successful")
            #             # Vendor note (231213): open serial port1
            #             self.G_SerialPort1Obj.flushInput()  # clean serial write cache
            #             self.G_SerialPort1Obj.flush()
            #             self.G_PhrozenFluiddRespondInfo("Serial port 1 buffers cleared")
            #             self.G_PhrozenFluiddRespondInfo("Re-registering serial port 1 callback")
            #             self.G_SerialPort1RecvTimmer = self.G_PhrozenReactor.register_timer(self.Device_TimmerUart1Recv, self.G_PhrozenReactor.NOW)
            #     except:
            #         self.G_PhrozenFluiddRespondInfo("Unable to open tty1. Check the USB connection or try rebooting.")

            #     return eventtime + AMS_SERIALPORT_RECV_TIMER

            # # Vendor note (240410): # if self.G_CancelFlag==True:
            #     #self.G_PhrozenFluiddRespondInfo("Print cancelled")
            #     return eventtime + AMS_SERIALPORT_RECV_TIMER

            # Vendor note (231103): tty2 serial data available
            if self.G_SerialPort2Obj.inWaiting() > 0:
                self.kaos_log("DEBUG", "Current mode", "SERIAL")
                if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                    self.emit_mode(0, "unkown")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
                    self.emit_mode(1, "MC")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                    self.emit_mode(2, "MA")
                elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                    self.emit_mode(3, "RUNOUT")
                else:
                    self.emit_mode(-1, "error")

                self.kaos_log(
                    "DEBUG",
                    "[(dev.python)Device_TimmerUart2Recv]serial port 2 read get number data",
                    "SERIAL",
                )
                Lo_SerialRxLen = self.G_SerialPort2Obj.inWaiting()
                self.kaos_log("DEBUG", "byte count Lo_SerialRxLen=%d" % Lo_SerialRxLen, "SERIAL")
                # self.G_PhrozenFluiddRespondInfo("Serial port timer receive")
                Lo_SerialRxBytes = self.G_SerialPort2Obj.read(Lo_SerialRxLen)
                self.kaos_log(
                    "DEBUG", "byte streamLo_SerialRxBytes=%s" % Lo_SerialRxBytes, "SERIAL"
                )
                self.kaos_log(
                    "DEBUG",
                    "byte streambinascii.hexlify(Lo_SerialRxBytes)=%s"
                    % binascii.hexlify(Lo_SerialRxBytes),
                    "SERIAL",
                )
                # self.G_PhrozenFluiddRespondInfo("%x" % binascii.hexlify(Lo_SerialRxBytes))
                self.kaos_log(
                    "DEBUG", "byte countlen(Lo_SerialRxBytes)=%d" % len(Lo_SerialRxBytes), "SERIAL"
                )
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes.count=%d" % Lo_SerialRxBytes.count)
                # for i in Lo_SerialRxBytes:
                # self.G_PhrozenFluiddRespondInfo("%x" % i)

                self.kaos_log(
                    "DEBUG", "Lo_SerialRxBytes[0] - hex byte0x%2x" % Lo_SerialRxBytes[0], "SERIAL"
                )
                self.kaos_log(
                    "DEBUG",
                    "Lo_SerialRxBytes[0] - ASCII character%c" % Lo_SerialRxBytes[0],
                    "SERIAL",
                )
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes[1] - hex byte 0x%2x" % Lo_SerialRxBytes[1])
                # self.G_PhrozenFluiddRespondInfo("Lo_SerialRxBytes[1] - ASCII character %c" % Lo_SerialRxBytes[1])

                # Vendor note (20231013): read ttyUSB0 serial bytes, convert to ASCII
                # Vendor note (240530): hex bytes to ASCII characters
                self.G_SerialRxASCIIStr = Lo_SerialRxBytes.decode("ascii")
                # self.G_PhrozenFluiddRespondInfo("ASCII character self.G_SerialRxASCIIStr=%s" % self.G_SerialRxASCIIStr)

                # Vendor note (240705): AMS multi-material present
                self.G_AMSDevice2IfNormal = True

                try:
                    # #if "R" in self.G_SerialRxASCIIStr:
                    # if Lo_SerialRxBytes[0]==0x52:
                    #     self.G_PhrozenFluiddRespondInfo("AMS unit 2 async response")

                    #     #self.G_PhrozenFluiddRespondInfo("%s" % SerialRxASCIIStr)
                    #     Lo_AMSDeviceStateInfo = AMSDetailInfoBytes()
                    #     Lo_AMSDeviceStateInfo.whole[:] = Lo_SerialRxBytes
                    #     #empty Python dict
                    #     Lo_AMSDetailState = {}
                    #     self.G_AMS2DeviceState["dev_id"] = Lo_AMSDetailState["dev_id"] = Lo_AMSDeviceStateInfo.field.dev_id
                    #     self.G_AMS2DeviceState["active_dev_id"] = Lo_AMSDetailState["active_dev_id"] = Lo_AMSDeviceStateInfo.field.active_dev_id
                    #     self.G_AMS2DeviceState["dev_mode"] = Lo_AMSDetailState["dev_mode"] = Lo_AMSDeviceStateInfo.field.dev_mode
                    #     self.G_AMS2DeviceState["cache_empty"] = Lo_AMSDetailState["cache_empty"] = Lo_AMSDeviceStateInfo.field.cache_empty
                    #     #self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor empty state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_empty)
                    #     self.G_AMS2DeviceState["cache_full"] = Lo_AMSDetailState["cache_full"] = Lo_AMSDeviceStateInfo.field.cache_full
                    #     #self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor full state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_full)
                    #     self.G_AMS2DeviceState["cache_exist"] = Lo_AMSDetailState["cache_exist"] = Lo_AMSDeviceStateInfo.field.cache_exist
                    #     #self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor filament state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_exist)
                    #     self.G_AMS2DeviceState["mc_state"] = Lo_AMSDetailState["mc_state"] = Lo_AMSDeviceStateInfo.field.mc_state
                    #     self.G_AMS2DeviceState["ma_state"] = Lo_AMSDetailState["ma_state"] = Lo_AMSDeviceStateInfo.field.ma_state
                    #     self.G_AMS2DeviceState["entry_state"] = Lo_AMSDetailState["entry_state"] = Lo_AMSDeviceStateInfo.field.entry_state
                    #     #self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Entry position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.entry_state)
                    #     self.G_AMS2DeviceState["park_state"] = Lo_AMSDetailState["park_state"] = Lo_AMSDeviceStateInfo.field.park_state
                    #     #self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Park position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.park_state)

                    #     # response data JSON conversion
                    #     self.G_PhrozenFluiddRespondInfo(json.dumps(Lo_AMSDetailState))

                    # if "R" in self.G_SerialRxASCIIStr:
                    if Lo_SerialRxBytes[0] == 0x52 and Lo_SerialRxLen == 16:
                        self.kaos_log("DEBUG", "AMS unit 2 async response", "SERIAL")

                        # self.G_PhrozenFluiddRespondInfo("%s" % SerialRxASCIIStr)
                        Lo_AMSDeviceStateInfo = AMSDetailInfoBytes()
                        Lo_AMSDeviceStateInfo.whole[:] = Lo_SerialRxBytes
                        # empty Python dict
                        Lo_AMSDetailState = {}
                        self.G_AMS1DeviceState["dev_id"] = Lo_AMSDetailState["dev_id"] = (
                            Lo_AMSDeviceStateInfo.field.dev_id
                        )
                        self.G_AMS1DeviceState["active_dev_id"] = Lo_AMSDetailState[
                            "active_dev_id"
                        ] = Lo_AMSDeviceStateInfo.field.active_dev_id
                        self.G_AMS1DeviceState["dev_mode"] = Lo_AMSDetailState["dev_mode"] = (
                            Lo_AMSDeviceStateInfo.field.dev_mode
                        )
                        self.G_AMS1DeviceState["cache_empty"] = Lo_AMSDetailState["cache_empty"] = (
                            Lo_AMSDeviceStateInfo.field.cache_empty
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor empty state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_empty)
                        self.G_AMS1DeviceState["cache_full"] = Lo_AMSDetailState["cache_full"] = (
                            Lo_AMSDeviceStateInfo.field.cache_full
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor full state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_full)
                        self.G_AMS1DeviceState["cache_exist"] = Lo_AMSDetailState["cache_exist"] = (
                            Lo_AMSDeviceStateInfo.field.cache_exist
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Buffer sensor filament state (bool) == %d" % Lo_AMSDeviceStateInfo.field.cache_exist)
                        self.G_AMS1DeviceState["mc_state"] = Lo_AMSDetailState["mc_state"] = (
                            Lo_AMSDeviceStateInfo.field.mc_state
                        )
                        self.G_AMS1DeviceState["ma_state"] = Lo_AMSDetailState["ma_state"] = (
                            Lo_AMSDeviceStateInfo.field.ma_state
                        )
                        self.G_AMS1DeviceState["entry_state"] = Lo_AMSDetailState["entry_state"] = (
                            Lo_AMSDeviceStateInfo.field.entry_state
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Entry position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.entry_state)
                        self.G_AMS1DeviceState["park_state"] = Lo_AMSDetailState["park_state"] = (
                            Lo_AMSDeviceStateInfo.field.park_state
                        )
                        # self.G_PhrozenFluiddRespondInfo("[(cmds.python)Cmds_CmdP114]Park position sensor state (bit) == %d" % Lo_AMSDeviceStateInfo.field.park_state)

                        # response data JSON conversion
                        self.kaos_log("DEBUG", json.dumps(Lo_AMSDetailState), "SERIAL")

                        self.kaos_log("DEBUG", "P114 successful", "SERIAL")
                        self.emit_p114(1)
                        self.G_P114RunFlag = 0

                    else:
                        self.kaos_log("DEBUG", "AMS file", "SERIAL")
                        # Vendor note (20231013): read ttyUSB0 serial bytes, convert to ASCII
                        # Vendor note (240530): hex bytes to ASCII characters
                        self.G_SerialRxASCIIStr = Lo_SerialRxBytes.decode("ascii")
                        self.kaos_log(
                            "DEBUG",
                            "ASCII character self.G_SerialRxASCIIStr=%s" % self.G_SerialRxASCIIStr,
                            "SERIAL",
                        )

                        # Vendor note (250411): AMSfirmware version

                        # // AMS board 2 firmware-1 1
                        if "V-H18-I18-F" in self.G_SerialRxASCIIStr:
                            self.kaos_log("DEBUG", "AMS code disable unit 2 file", "SERIAL")
                            # =====DriveCodeFile.dat
                            # 1 , 18 , 24053 , 18 , 0# // AMS board 1 firmware-18
                            # 2 , 18 , 24053 , 18 , 0# // AMS board 2 firmware-18
                            # 3 , 18 , 24053 , 18 , 0# // AMS board 3 firmware-18
                            # 4 , 18 , 24053 , 18 , 0# // AMS board 4 firmware-18
                            # 5 , 5 , 24046 , 5 , 0# // OTA sub-program - AMS serial upgrade-5 5
                            # 6 , 0 , 0 , 0 , 0# // buffer board firmware-6 6
                            # 7 , 7 , 24051 , 7 , 0# // 16-color HUB board firmware-7 7
                            # 8 , 0 , 0 , 0 , 0
                            # 9 , 0 , 0 , 0 , 0
                            # 10 , 10 , 24054 , 10 , 0# // OTA sub-program - TJC display background-10
                            # 11 , 11 , 24047 , 11 , 0# // TJC serial display HMI firmware-11
                            # 12 , 0 , 0 , 0 , 0
                            # 13 , 0 , 0 , 0 , 0
                            # 14 , 0 , 0 , 0 , 0
                            # 15 , 15 , 25042 , 15 , 0
                            # 16 , 16 , 25042 , 16 , 0
                            # 17 , ? , 25042 , ? , 0
                            # 18 , ? , 25042 , ? , 0
                            # 19 , ? , 25042 , ? , 0
                            # 20 , ? , 25042 , ? , 0
                            # topic: c0f535790a90/GetZbGwInfo_Respon
                            # {
                            #     "Data_ID": 95,
                            #     "Data": {
                            #         "GwId": "c0f535790a90",
                            #         "HomeId": "",
                            #         "GWSN": "0000000000000000000",
                            #         "AccountId": "",
                            #         "GwMac": "c0f535790a90",
                            #         "GwIP": "192.168.3.53",
                            #         "GwName": "Name-c0f535790a90",
                            #         "ProductId": "ARCO",
                            #         "MainImage": 15,
                            #         "MainHWVersion": 15,
                            #         "MainFWVersion": 24064,
                            #         "Gw_Ram": 248584,
                            #         "Gw_Rom": 826536,
                            #         "JoinMode": 1,
                            #         "ESSID": "",
                            #         "MqttClientEMQfd": 31,
                            #         "MqttClientId": "c0f535790a90",
                            #         "MqttBrokerUserName": "",
                            #         "MqttBrokerPwd": "",
                            #         "DriveCodeList": [
                            #             {
                            #                 "DriveCode": 1,
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
                            #                 "DriveCode": 3,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
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
                            #                 "DriveCode": 5,
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
                            #                 "DriveCode": 7,
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
                            #                 "DriveCode": 9,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 10,
                            #                 "DriveImageType": 10,
                            #                 "DriveHwVersion": 10,
                            #                 "DriveFwVersion": 25033,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 11,
                            #                 "DriveImageType": 11,
                            #                 "DriveHwVersion": 11,
                            #                 "DriveFwVersion": 25022,
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
                            #                 "DriveCode": 13,
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
                            #                 "DriveCode": 15,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 16,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 17,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 18,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 19,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             },
                            #             {
                            #                 "DriveCode": 20,
                            #                 "DriveImageType": 0,
                            #                 "DriveHwVersion": 0,
                            #                 "DriveFwVersion": 0,
                            #                 "DriveId": 0
                            #             }
                            #         ]
                            #     }
                            # }
                            # Vendor note (250724): read system image id to distinguish product/board/firmware variants
                            # Vendor note (250724): read image id
                            self.Cmds_GetImageId()
                            if self.G_ImageId == 16:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==16: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"
                            elif self.G_ImageId == 31:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==31: ARCO300-phrozen-RK3308-STM32F407VET6-I31",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/prz/hdlDat/DriveCodeFile.dat"
                            elif self.G_ImageId == -1:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID==-1, default: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"
                            else:
                                self.kaos_log(
                                    "DEBUG",
                                    "Image ID could not be read, default: ARCO300-MKS-RK3328-STM32F407VET6-I16",
                                    "SERIAL",
                                )
                                # Vendor note (240530): write version to DriveCodeJson.dat
                                filename = "/home/mks/hdlDat/DriveCodeFile.dat"

                            self.kaos_log("DEBUG", "filename=%s" % filename, "SERIAL")
                            Lo_AllLine = ""
                            # data = [{"DriveCode":16,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":15,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":14,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":13,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":12,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":11,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":10,"DriveImageType":10,"DriveHwVersion":10,"DriveFwVersion":24045,"DriveId":0},{"DriveCode":9,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":8,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":7,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":6,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":5,"DriveImageType":5,"DriveHwVersion":5,"DriveFwVersion":24046,"DriveId":0},{"DriveCode":4,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":3,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":2,"DriveImageType":0,"DriveHwVersion":0,"DriveFwVersion":0,"DriveId":0},{"DriveCode":1,"DriveImageType":1,"DriveHwVersion":1,"DriveFwVersion":24042,"DriveId":0}]
                            # f = open(filename, 'a')
                            # json.dump(data, f)  #object
                            # f.close()
                            with open(filename, "r") as file:
                                # for line in file:
                                # # realine() read, "\n"
                                # self.G_PhrozenFluiddRespondInfo(file.readline().strip())
                                # #time.sleep(1)
                                Lo_FileDataList = file.readlines()
                                for line in Lo_FileDataList:
                                    # split = [i[:-1].split(',') for i in file.readlines()]
                                    # self.G_PhrozenFluiddRespondInfo(type(split))
                                    # self.G_PhrozenFluiddRespondInfo(split[1])
                                    # self.G_PhrozenFluiddRespondInfo(split[2])
                                    # self.G_PhrozenFluiddRespondInfo(split[3])
                                    # line_strip=line.strip()
                                    # self.G_PhrozenFluiddRespondInfo(line)
                                    # self.G_PhrozenFluiddRespondInfo("line.count=%d" % line.count)
                                    split = line.split(",")
                                    # self.G_PhrozenFluiddRespondInfo(type(split))
                                    # self.G_PhrozenFluiddRespondInfo("".join(split))
                                    # self.G_PhrozenFluiddRespondInfo(split[0])
                                    # 2 , 18 , 24053 , 18 , 0
                                    split[0] = split[0].strip()  # driver number
                                    split[1] = split[1].strip()  # hardware id
                                    split[2] = split[2].strip()  # firmware version
                                    split[3] = split[3].strip()  # image id
                                    split[4] = split[4].strip()  # online status
                                    # split[4]='0'#online status,default0
                                    # #if "SN1" in self.G_SerialRxASCIIStr:
                                    # if split[0] == "1":
                                    #     self.G_PhrozenFluiddRespondInfo(split[0])
                                    #     self.G_PhrozenFluiddRespondInfo(split[1])
                                    #     self.G_PhrozenFluiddRespondInfo(split[2])
                                    #     self.G_PhrozenFluiddRespondInfo(split[3])
                                    #     self.G_PhrozenFluiddRespondInfo(split[4])
                                    #     #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #     line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #     self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #     Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    # else:
                                    #     Lo_AllLine=Lo_AllLine+line

                                    # if "SN2" in self.G_SerialRxASCIIStr:
                                    if split[0] == "2":
                                        self.kaos_log("DEBUG", "AMSunit 2 file", "SERIAL")
                                        self.kaos_log("DEBUG", split[0], "SERIAL")
                                        self.kaos_log("DEBUG", split[1], "SERIAL")
                                        self.kaos_log("DEBUG", split[2], "SERIAL")
                                        self.kaos_log("DEBUG", split[3], "SERIAL")
                                        self.kaos_log("DEBUG", split[4], "SERIAL")
                                        # line=("%d,%d,%d," % (HW_VERSION,,))
                                        line_modify = (
                                            split[0]
                                            + ","
                                            + "18"
                                            + ","
                                            + self.G_SerialRxASCIIStr[11:16]
                                            + ","
                                            + "18"
                                            + ","
                                            + "1"
                                        )
                                        self.kaos_log("DEBUG", line_modify, "SERIAL")
                                        Lo_AllLine = Lo_AllLine + line_modify + "\r\n"  # 0x0D 0x0A
                                    else:
                                        Lo_AllLine = Lo_AllLine + line

                                    # if "SN3" in self.G_SerialRxASCIIStr:
                                    #     if split[0] == "3":
                                    #         self.G_PhrozenFluiddRespondInfo(split[0])
                                    #         self.G_PhrozenFluiddRespondInfo(split[1])
                                    #         self.G_PhrozenFluiddRespondInfo(split[2])
                                    #         self.G_PhrozenFluiddRespondInfo(split[3])
                                    #         self.G_PhrozenFluiddRespondInfo(split[4])
                                    #         #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #         line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #         self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #         Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    #     else:
                                    #         Lo_AllLine=Lo_AllLine+line
                                    # if "SN4" in self.G_SerialRxASCIIStr:
                                    #     if split[0] == "4":
                                    #         self.G_PhrozenFluiddRespondInfo(split[0])
                                    #         self.G_PhrozenFluiddRespondInfo(split[1])
                                    #         self.G_PhrozenFluiddRespondInfo(split[2])
                                    #         self.G_PhrozenFluiddRespondInfo(split[3])
                                    #         self.G_PhrozenFluiddRespondInfo(split[4])
                                    #         #line=("%d,%d,%d," % (HW_VERSION,,))
                                    #         line_modify=split[0]+','+'1'+','+self.G_SerialRxASCIIStr[9:14]+','+'1'+','+'1'
                                    #         self.G_PhrozenFluiddRespondInfo(line_modify)
                                    #         Lo_AllLine=Lo_AllLine+line_modify+"\r\n"#0x0D 0x0A
                                    #     else:
                                    #         Lo_AllLine=Lo_AllLine+line
                            # self.G_PhrozenFluiddRespondInfo(Lo_AllLine)
                            with open(filename, "w+") as file_w:
                                file_w.write(Lo_AllLine)

                        self.Device_TimmerUartRecvHandler(
                            2, Lo_SerialRxBytes, self.G_SerialRxASCIIStr
                        )

                except:
                    self.kaos_log("DEBUG", "serial port number data error, noneAMSstate", "SERIAL")

            return eventtime + AMS_SERIALPORT_RECV_TIMER

        except Exception as e:
            self.kaos_log(
                "DEBUG",
                "serial port 2 read get error, AMS2 error or restart, please checkAMS2 is no normal normal",
                "SERIAL",
            )
            self.kaos_log("DEBUG", "Current mode", "SERIAL")
            if self.G_AMSDeviceWorkMode == AMS_WORK_MODE_UNKNOW:
                self.emit_mode(0, "unkown")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MC:
                self.emit_mode(1, "MC")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_MA:
                self.emit_mode(2, "MA")
            elif self.G_AMSDeviceWorkMode == AMS_WORK_MODE_FILA_RUNOUT:
                self.emit_mode(3, "RUNOUT")
            else:
                self.emit_mode(-1, "error")
            # if AMS error restart, log it and send STM32 slow-feed command after restart
            # Vendor note (240427): AMS error restart, needs logging
            self.G_AMS2ErrorRestartFlag = True
            self.G_AMS2ErrorRestartCount = self.G_AMS2ErrorRestartCount + 1

            # Vendor note (241011): serial port 2 error, cannot send data
            self.G_SerialPort2OpenFlag = False

            # Vendor note (240521): on resume: if AMS restart detected (hot-plug), execute full retract/change
            self.G_ResumeCheckAMS2ErrorRestartFlag = True

            return eventtime + AMS_SERIALPORT_RECV_TIMER


# Vendor note (0914): do not move; calling PhrozenDev class
def load_config(config):
    return PhrozenDev(config)
