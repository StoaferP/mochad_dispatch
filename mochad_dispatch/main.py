import asyncio
import aiohttp
import daemonize
import sys
import os
import time
from datetime import datetime
import pytz
import argparse
import urllib.parse
import paho.mqtt.client as mqtt
import json

class RestDispatcher:
    """
    RestDispatcher object

    Used by MochadClient object to dispatch messages via REST

    :param dispatch_uri: the URI which should be used as a REST entry point
    """
    def __init__(self, mochad_host, dispatch_uri):
        self.dispatch_uri = dispatch_uri
        self.mochad_host = mochad_host

        # ensure entry point ends with /
        if not self.dispatch_uri[-1] == '/':
            self.dispatch_uri = self.dispatch_uri + '/'

    @asyncio.coroutine
    def dispatch_message(self, addr, message_dict):
        post_data = json.dumps(message_dict)
        headers = {'content-type': 'application/json'}
        response = yield from aiohttp.post(
              "{}{}".format(self.dispatch_uri, addr),
              data=post_data,
              headers=headers)
        if response.status != 200:
            raise Exception("HTTP status {}".format(response.status))
        # we don't care about the response so just release
        yield from response.release()


class MqttDispatcher:
    """
    MqttDispatcher object

    Used by MochadClient object to dispatch messages via MQTT

    :param dispatch_uri: the URI that describes the MQTT server which should be used to receive messages
    """
    def __init__(self, mochad_host, dispatch_uri):
        uri = urllib.parse.urlparse(dispatch_uri)
        self.mochad_host = mochad_host
        self.host = uri.hostname
        self.port = uri.port if uri.port else 1883
        self.mqttc = mqtt.Client("mochadc{}".format(os.getpid()))

        self.mqttc.connect(self.host, self.port)
        self.mqttc.loop_start()

    @asyncio.coroutine
    def dispatch_message(self, addr, message_dict):
        # X10 topic format
        #    X10/MOCHAD_HOST/security/DEVICE_ADDRESS
        #
        # (based on discussion at below URL)
        # https://groups.google.com/forum/#!topic/homecamp/sWqHvQnLvV0
        topic = "X10/{}/security/{}".format(
              self.mochad_host, self.port, addr)
        payload = json.dumps(message_dict)
        result, mid = self.mqttc.publish(topic, payload, qos=1, retain=True)
        pass


class MochadClient:
    """
    MochadClient object

    Makes a persistent connection to mochad and translates RFSEC messages to MQTT or REST

    :param host: IP/hostname of system running mochad
    :param logger: Logger object to use
    :param dispatcher: object to use for dispatching messages.
                       Can be either MqttDispatcher or RestDispatcher
    
    """
    def __init__(self, host, logger, dispatcher):
        self.host = host
        self.logger = logger
        self.reconnect_time = 0
        self.reader = None
        self.writer = None
        self.dispatcher = dispatcher

    def parse_mochad_line(self, line):
        # bail out unless it's an incoming RFSEC message
        if line[15:23] != 'Rx RFSEC':
            return '', ''

        # decode message. format is either:
        #   09/22 15:39:07 Rx RFSEC Addr: 21:26:80 Func: Contact_alert_min_DS10A
        #     ~ or ~
        #   09/22 15:39:07 Rx RFSEC Addr: 0x80 Func: Motion_alert_SP554A
        line_list = line.split(' ')
        addr = line_list[5]
        func = line_list[7]

        func_dict = self.decode_func(func)

        return addr, {'func': func_dict}

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

    @asyncio.coroutine
    def connect(self):
        connection = asyncio.open_connection(self.host, 1099)
        self.reader, self.writer = yield from connection

    @asyncio.coroutine
    def dispatch_message(self, addr, message_dict):
        """
        Use dispatcher object to dispatch decoded RFSEC message
        """
        try:
            yield from self.dispatcher.dispatch_message(addr, message_dict)
        except Exception as e:
            self.logger.error(
                  "dispatch failed: {} message {}".format(e, message_dict))

    @asyncio.coroutine
    def worker(self):
        """
        Maintain the connection to mochad, read output from mochad and dispatch any RFSEC messages
        """
        # CONNECTION LOOP
        while True:
            # if we are in reconnect status, sleep before connecting
            if self.reconnect_time:
                yield from asyncio.sleep(1)

                # if we've been reconnecting for over 60s, bail out
                if (time.time() - self.reconnect_time) > 60:
                    self.logger.error("Could not reconnect after 60s")
                    break

            try:
                yield from self.connect()
            except OSError as e:
                if not self.reconnect_time:
                    self.reconnect_time = time.time()
                    self.logger.warn("Could not connect to mochad. Retrying")

                # keep trying to reconnect
                continue

            # if we make it this far we've successfully connected, reset the
            # reconnect time
            self.reconnect_time = 0
            self.logger.info("Connected to mochad")

            # READ FROM NETWORK LOOP
            while True:
                line = yield from self.reader.readline()
                # an empty string means connection lost, exit read loop
                if not line:
                    break
                # parse the line
                try:
                    addr, message_dict = self.parse_mochad_line(
                          line.decode("utf-8").rstrip())
                except Exception as e:
                    self.logger.error("parse failed for {}: {}".format(
                          line, e))
                    continue 

                # addr/func will be blank when we have nothing to dispatch
                if addr and message_dict:
                    # we don't to use mochad's timestamp because it lacks a year
                    message_dict['dispatch_time'] = datetime.now(
                          pytz.UTC).isoformat()

                    asyncio.Task(self.dispatch_message(addr, message_dict))


            # we broke out of the read loop: we got disconnected, retry connect
            self.logger.warn("Lost connection to mochad. Retrying.")
            self.reconnect_time = time.time()

def daemon_main():
    """
    Main function which will be executed by Daemonize after initializing
    """
    dispatcher = dispatcher_type(args.server, args.dispatch_uri)
    mochad_client = MochadClient(args.server, daemon.logger, dispatcher)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(mochad_client.worker())

def errordie(message):
    """
    Print error message then quit with exit code
    """
    prog = os.path.basename(sys.argv[0])
    sys.stderr.write("{}: error: {}\n".format(prog, message))
    sys.exit(1)

def main():
    """
    Main entry point into mochad_dispatch.  Processes command line arguments then hands off to Daemonize and MochadClient
    """
    # parse command line args
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--server', default="127.0.0.1",
          help="IP/host of server running mochad (default 127.0.0.1)")
    parser.add_argument('-f', '--foreground',
          action='store_true', default=False,
          help="Don't fork; run in foreground (for debugging)")
    parser.add_argument('dispatch_uri', help='dispatch messages to this URI')
    global args
    args = parser.parse_args()

    # set dispatcher type based on dispatch_uri
    uri = urllib.parse.urlparse(args.dispatch_uri)
    global dispatcher_type
    if uri.scheme == 'mqtt':
        dispatcher_type = MqttDispatcher
    # assume REST if URI scheme is http or https
    elif uri.scheme == 'https' or uri.scheme == 'http':
        dispatcher_type = RestDispatcher
    else:
        errordie("unsupported URI scheme '{}'".format(uri.scheme))

    # daemonize
    global daemon
    daemon = daemonize.Daemonize(app="mochad_dispatch", 
                                 pid="/tmp/mochad_dispatch.pid",
                                 foreground=args.foreground,
                                 action=daemon_main)
    daemon.start()

if __name__ == "__main__":
    main()
