import sys
import os
import signal
import socket
import time
from datetime import datetime
import pytz
import argparse
import urllib.parse
import paho.mqtt.client as mqtt
import json
from paho.mqtt.enums import CallbackAPIVersion

import threading

import logging
from logging.handlers import RotatingFileHandler

base_path = None
args = None
dispatcher_type = None
main_logger = None
loop = None
killer = None

class GracefulKiller:
    kill_now = False

    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True
        main_logger.info("Caught signal, mochad_dispatch is exiting...")
        #exit(0)
    
    def do_kill_now(self):
        os.kill(os.getpid(), signal.SIGTERM)

class SocketReader:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.sock_file = None

    def open_connection(self):
        """Open the socket and prepare the file-like object."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock_file = self.sock.makefile('r')
        except Exception as e:
            raise Exception("Could not connect to {}: {}".format(self.host, e))

    def read_line(self):
        """Read a single line from the socket."""
        if self.sock_file:
            return self.sock_file.readline().strip()
        else:
            raise ValueError("Connection is not open. Call open_connection first.")

    def read_to_eof(self):
        """Read all remaining content until EOF."""
        if self.sock_file:
            return self.sock_file.read()
        else:
            raise ValueError("Connection is not open. Call open_connection first.")

    def close_connection(self):
        """Close the socket and associated file."""
        if self.sock_file:
            self.sock_file.close()
        if self.sock:
            self.sock.close()

class MqttDispatcher:
    """
    MqttDispatcher object

    Used by MochadClient object to dispatch messages via MQTT

    :param mochad_host: The hostname of the mochad server.  This will be used in the topic name
    :param dispatch_uri: The URI that describes an MQTT broker.  Messages dispatched from MochadClient will be published to this broker.
    :param logger: Logger object to use
    :param cafile: The file containing trusted CA certificates.  Specifying this will enable SSL/TLS encryption to the MQTT broker
    """
    def __init__(self, mochad_host, dispatch_uri, logger, cafile, killer):
        use_password = False
        if ',' in dispatch_uri:
            real_uri = dispatch_uri.split(',')[0]
            if 'user' in dispatch_uri and 'pass' in dispatch_uri:
                user = dispatch_uri.split(',')[1].split('=')[1]
                password = dispatch_uri.split(',')[2].split('=')[1]
                logger.debug(f"real_uri: {real_uri}, user: {user}, password: {password}")
                use_password = True
        else:
            real_uri = dispatch_uri
        uri = urllib.parse.urlparse(real_uri)
        self.mochad_host = mochad_host
        self.logger = logger
        self.killer = killer
        self.host = uri.hostname
        self.port = uri.port if uri.port else 1883
        mqtt_client_id = "mochadc/{}-{}".format(os.getpid(),
                                                socket.gethostname())
        self.logger.info(f"mqtt_client_id: {mqtt_client_id}, mqtt host: {self.host}, mqtt port: {self.port}")
        self.mqttc = mqtt.Client(CallbackAPIVersion.VERSION2, mqtt_client_id)
        if use_password:
            self.logger.info(f"mqtt connection with username and password.")
            self.mqttc.username_pw_set(user, password)

        self.logger.debug("self.mqttc: {}".format(self.mqttc))
        # connection error handling
        self.reconnect_time = -1
        def on_connect(client, userdata, flags, rc, properties):
            self.reconnect_time = 0

        def on_disconnect(client, userdata, flags, rc, properties):
            # reconnect_time = -1 here means the first connection failed
            if self.reconnect_time == -1:
                # Why suggest SSL here?  If on_disconnect is called BEFORE
                # on_connect that means the socket initially connected but
                # failed BEFORE gettin got he MQTT-specific negotiation.  To my
                # knowledge only SSL happens in between those two
                self.logger.error("Could not connect to MQTT broker: possibly SSL/TLS failure")
                self.killer.do_kill_now()
            elif self.reconnect_time == 0:
                self.reconnect_time = time.time()

        self.mqttc.on_connect = on_connect
        self.mqttc.on_disconnect = on_disconnect

        # configure TLS if argument "cafile" is given
        if cafile:
            self.mqttc.tls_set(cafile)

        try:
            rc = self.mqttc.connect(self.host, self.port)
            self.logger.info(f"mqtt connect return code: {rc}")
        except Exception as e:
            raise Exception("Could not connect to MQTT broker: {}".format(e))
        self.mqttc.loop_start()

    def dispatch_message(self, addr, message_dict, kind):
        """
        Publish, in json format, a dict to an MQTT broker
        """
        # X10 topic format
        #    X10/MOCHAD_HOST/security/DEVICE_ADDRESS
        #
        # (based on discussion at below URL)
        # https://groups.google.com/forum/#!topic/homecamp/sWqHvQnLvV0
        topic = "X10/{}/{}/{}".format(
              self.mochad_host, kind, addr)
        payload = json.dumps(message_dict)
        # Distinguish between status messages (security) and
        # button presses per Andy Stanford-Clark's suggestion at
        # https://groups.google.com/d/msg/mqtt/rIp1uJsT9Nk/7YOWNCQO3ZEJ
        if kind == 'button':
            qos, retain = 0, False
        else:
            qos, retain = 1, True
        result, mid = self.mqttc.publish(topic, payload, qos=qos, retain=retain)
        pass

    def watchdog(self):

        """
        Continually watches the MQTT broker connection health.  Exits gracefully if the connection is retried for 60 seconds straight without success.

        Why not just do this in the on_disconnect callback?  The on_disconnect callback is not called while loop_start/loop_forever is doing an automatic reconnect.  This makes it impossible to use on_disconnect to handle reconnect issues in the loop_start/loop_forever functions.
        """
        while self.killer.kill_now == False:
            if (self.reconnect_time > 0 and 
                time.time() - self.reconnect_time > 60):

                self.logger.error(
                      "Could not reconnect to MQTT broker after 60s")
                self.killer.do_kill_now()
                break
            else:
                time.sleep(1)

class MochadClient:
    """
    MochadClient object

    Makes a persistent connection to mochad and translates RFSEC messages to MQTT

    :param host: IP/hostname of system running mochad
    :param logger: Logger object to use
    :param dispatcher: object to use for dispatching messages.  Must be MqttDispatcher

    """
    def __init__(self, host, logger, dispatcher, house_codes, killer):
        self.host = host
        self.logger = logger
        self.reconnect_time = -1
        self.reader = None
        self.dispatcher = dispatcher
        self.house_codes = house_codes
        self.killer = killer
        self.pl_houseunit = None
        self.reader = None

    def parse_mochad_line(self, line):
        """
        Parse a raw line of output from mochad
        """
        if type(line) == bytes:
            line = line.decode()
        # bail out unless it's an incoming RFSEC message
        if line[15:23] == 'Rx RFSEC':

            # decode message. format is either:
            #   09/22 15:39:07 Rx RFSEC Addr: 21:26:80 Func: Contact_alert_min_DS10A
            #     ~ or ~
            #   09/22 15:39:07 Rx RFSEC Addr: 0x80 Func: Motion_alert_SP554A
            line_list = line.split(' ')
            addr = line_list[5]
            func = line_list[7]

            func_dict = self.decode_func(func)

            return addr, {'func': func_dict}, 'security'

        elif line[16:20] == 'x RF':

            # decode RF message. format is:
            #   02/13 23:54:28 Rx RF HouseUnit: B1 Func: On
            #   12/15 21:30:45 Tx RF HouseUnit: A4 Func: On\n
            line_list = line.split(' ')
            house_code = line_list[5]
            hc = house_code[0:1]
            if hc in self.house_codes:
                house_func = line_list[7]
                return house_code, {'func': house_func}, 'button'

        elif line[15:20] == 'Rx PL':

            # decode PL message. format is in 2 parts:
            #   02/13 23:54:28 Rx PL HouseUnit: B1
            #   02/13 23:54:28 Rx PL House: B Func: On
            line_list = line.split(' ')
            if line_list[4] == 'HouseUnit:':
                hc = line_list[5][0:1]
                if hc in self.house_codes:
                    self.pl_houseunit = line_list[5]
            if line_list[4] == 'House:' and self.pl_houseunit != None:
                house_func = line_list[7]
                house_unit = self.pl_houseunit
                return house_unit, {'func': house_func}, 'button'
        
        return '', '', ''


    def decode_func(self, raw_func):
        """
        Decode the "Func:" parameter of an RFSEC message
        """
        MOTION_DOOR_WINDOW_SENSORS = ['DS10A', 'DS12A', 'MS10A', 'SP554A']
        SECURITY_REMOTES = ['KR10A', 'KR15A', 'SH624']
        func_list = raw_func.split('_')
        func_dict = dict()

        func_dict['device_type'] = func_list.pop()

        # set event_type and event_state for motion and door/window sensors
        if func_dict['device_type'] in MOTION_DOOR_WINDOW_SENSORS:
            func_dict['event_type'] = func_list[0].lower()
            func_dict['event_state'] = func_list[1]
            i = 2
        elif func_dict['device_type'] in SECURITY_REMOTES:
            i = 0
        # bail out if we have an unknown device type
        else:
            raise Exception("Unknown device type in {}: {}".format(
                  raw_func, func_dict['device_type']))

        # crawl through rest of func parameters
        while i < len(func_list):
            # delay setting
            if func_list[i] == 'min' or func_list[i] == 'max':
                func_dict['delay'] = func_list[i]
            # tamper detection
            elif func_list[i] == 'tamper':
                func_dict['tamper'] = True
            # low battery
            elif func_list[i] == 'low':
                func_dict['low_battery'] = True
            # Home/Away switch on SP554A
            elif func_list[i] == 'Home' and func_list[i+1] == 'Away':
                func_dict['home_away'] = True
                # skip over 'Away' in func_list
                i += 1
            # Arm system
            elif func_list[i] == 'Arm' and i+1 == len(func_list):
                func_dict['command'] = 'arm'
            # Arm system in Home mode
            elif func_list[i] == 'Arm' and func_list[i+1] == 'Home':
                func_dict['command'] = 'arm_home'
                # skip over 'Home' in func_list
                i += 1
            # Arm system in Away mode
            elif func_list[i] == 'Arm' and func_list[i+1] == 'Away':
                func_dict['command'] = 'arm_away'
                # skip over 'Away' in func_list
                i += 1
            # Disarm system
            elif func_list[i] == 'Disarm':
                func_dict['command'] = 'disarm'
            # Panic
            elif func_list[i] == 'Panic':
                func_dict['command'] = 'panic'
            # Lights on
            elif func_list[i] == 'Lights' and func_list[i+1] == 'On':
                func_dict['command'] = 'lights_on'
                # skip ovedr 'On' in func_list
                i += 1
            # Lights off
            elif func_list[i] == 'Lights' and func_list[i+1] == 'Off':
                func_dict['command'] = 'lights_off'
                # skip ovedr 'Off' in func_list
                i += 1
            # unknown
            else:
                raise Exception("Unknown func parameter in {}: {}".format(
                      raw_func, func_list[i]))

            i += 1

        return func_dict

    def connect(self):
        """
        Connect to mochad
        """

        self.reader = SocketReader(self.host, 1099)
        try:
            self.reader.open_connection()
        except Exception as e:
            self.logger.error("Could not connect to mochad: {}".format(e))
            raise

    def dispatch_message(self, addr, message_dict, kind):
        """
        Use dispatcher object to dispatch decoded RFSEC message
        """
        try:
            self.dispatcher.dispatch_message(addr, message_dict, kind)
        except Exception as e:
            self.logger.error(
                  "Failed to dispatch mochad message {}: {}".format(
                  message_dict, e))

    def worker(self):

        """
        Maintain the connection to mochad, read output from mochad and dispatch any RFSEC messages
        """
        # CONNECTION LOOP
        while self.killer.kill_now == False:
            # if we are in reconnect status, sleep before connecting
            if self.reconnect_time > 0:
                time.sleep(1)

                # if we've been reconnecting for over 60s, bail out
                if (time.time() - self.reconnect_time) > 60:
                    self.logger.error("Could not reconnect to mochad after 60s")
                    break

            try:
                self.connect()
            except OSError as e:
                if self.reconnect_time == 0:
                    self.reconnect_time = time.time()
                    self.logger.warn(
                          "Could not connect to mochad. Retrying: {}".format(e))
                # reconnect_time = -1 here means the first connection failed
                elif self.reconnect_time == -1:
                    self.logger.error(
                          "Could not connect to mochad: {}".format(e))
                    self.killer.do_kill_now()
                    break

                # keep trying to reconnect
                continue

            # if we make it this far we've successfully connected, reset the
            # reconnect time
            self.reconnect_time = 0
            self.logger.info(f"Connected to mochad host: {self.host}")

            # READ FROM NETWORK LOOP
            while True:
                line = self.reader.read_line()
                # an empty string means connection lost, exit read loop
                if not line:
                    break
                # parse the line
                try:
                    addr, message_dict, kind = self.parse_mochad_line(
                          line.rstrip())
                except Exception as e:
                    self.logger.error(
                          "Failed to parse mochad message {}: {}".format(
                          line, e))
                    continue

                # addr/func will be blank when we have nothing to dispatch
                if addr and message_dict:
                    # we don't to use mochad's timestamp because it lacks a year
                    message_dict['dispatch_time'] = datetime.now(
                          pytz.UTC).isoformat()
                    self.dispatch_message(addr, message_dict, kind)

            # we broke out of the read loop: we got disconnected, retry connect
            self.logger.warn("Lost connection to mochad. Retrying.")
            self.reconnect_time = time.time()

def daemon_main():
    """
    Main function which will be executed by Daemonize after initializing
    """
    global main_logger, killer, args

    main_logger.info("daemon_main()")

    try:
        main_logger.debug(f"dispatcher_type({args.server}, {args.dispatch_uri}, logger, {args.cafile}), killer")
        dispatcher = dispatcher_type(args.server,
                                     args.dispatch_uri,
                                     main_logger,
                                     args.cafile,
                                     killer)
        main_logger.debug("dispatcher 1: {}".format(dispatcher))
    except Exception as e:
        main_logger.error("Startup error: {}".format(e))
        sys.exit(1)
        
    main_logger.debug("dispatcher 2: {}".format(dispatcher))
    mochad_client = MochadClient(args.server, main_logger, dispatcher, args.housecodes.upper(), killer)

    main_logger.info("start task dispatcher.watchdog()")
    dispacther_watchdog_task_handle = threading.Thread(target=dispatcher.watchdog)
    dispacther_watchdog_task_handle.daemon = (
        True  # Daemon threads will shut down when the main process exits
    )
    dispacther_watchdog_task_handle.start()

    main_logger.info("start task mochad_client.worker()")
    mochad_client_worker_task_handle = threading.Thread(target=mochad_client.worker)
    mochad_client_worker_task_handle.daemon = (
        True  # Daemon threads will shut down when the main process exits
    )
    mochad_client_worker_task_handle.start()

    while killer.kill_now == False:
        time.sleep(2)

def errordie(message):
    """
    Print error message then quit with exit code
    """
    global main_logger
    prog = os.path.basename(sys.argv[0])
    main_logger.error("{}: error: {}\n".format(prog, message))
    sys.exit(1)

def main():
    """
    Main entry point into mochad_dispatch.  Processes command line arguments then hands off to Daemonize and MochadClient
    """
    global args, dispatcher_type, main_logger, base_path, killer

    killer = GracefulKiller()

    # parse command line args
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--server', default="127.0.0.1",
          help="IP/host of server running mochad (default 127.0.0.1)")
    parser.add_argument('-f', '--foreground',
          action='store_true', default=False,
          help="Don't fork; run in foreground (for debugging)")
    parser.add_argument('--cafile',
          help="File containing trusted CA certificates")
    parser.add_argument('-c', '--housecodes', default="ABCDEFGHIJKLMNOP",
          help="House codes for X10 devices (default ABCDEFGHIJKLMNOP)")
    parser.add_argument('dispatch_uri', help='dispatch messages to this URI')

    args = parser.parse_args()

    if base_path is None:
        base_path = os.path.abspath("./")

    main_logger = logging.getLogger("mochad_dispatch")
    main_logger.setLevel(logging.INFO)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # create formatter
    formatter = logging.Formatter("%(asctime)s %(name)s: %(levelname)s: %(message)s")

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    main_logger.addHandler(ch)
    main_file_handler = RotatingFileHandler(
        os.path.join(base_path, "mochad_dispatch.log"), maxBytes=5000000, backupCount=2
    )
    main_file_handler.setLevel(logging.INFO)
    main_file_handler.setFormatter(formatter)
    main_logger.addHandler(main_file_handler)

    main_logger.info("Starting mochad_dispatch")
    main_logger.debug("args: {}".format(args))

    # set dispatcher type based on dispatch_uri
    uri = urllib.parse.urlparse(args.dispatch_uri)

    if uri.scheme == 'mqtt':
        dispatcher_type = MqttDispatcher
    else:
        errordie("unsupported URI scheme '{}'".format(uri.scheme))

    daemon_main()

if __name__ == "__main__":
    main()
    exit(0)