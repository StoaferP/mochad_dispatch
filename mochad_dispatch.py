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


class MochadClient:
    """ MochadClient object
    
    """
    def __init__(self, host, logger, entry_point):
        self.host = host
        self.logger = logger
        self.reconnect_time = 0
        self.reader = None
        self.writer = None
        self.entry_point = entry_point

        # ensure entry point ends with /
        if not self.entry_point[-1] == '/':
            self.entry_point = self.entry_point + '/'


    @asyncio.coroutine
    def connect(self):
        connection = asyncio.open_connection(self.host, 1099)
        self.reader, self.writer = yield from connection

    @asyncio.coroutine
    def read_messages(self):
        while True:
            line = yield from self.reader.readline()
            # an empty string means connection lost, bail out
            if not line:
                break
            # dispatch RFSEC messages
            if line[15:23] == b'Rx RFSEC':
                asyncio.Task(self.dispatch_message(
                        line.decode("utf-8").rstrip()))

    @asyncio.coroutine
    def dispatch_message(self, message):
        # decode message
        #   09/22 15:39:07 Rx RFSEC Addr: 21:26:80 Func: Contact_alert_min_DS10A
        # do not to use mochad's timestamp because it lacks a year
        dispatch_time = datetime.now(pytz.UTC).isoformat()
        addr = message[30:38]
        func = message[45:]
        fail_msg = ''

        post_data = "dispatch_time={};func={}".format(
            urllib.parse.quote(dispatch_time), func)
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        try:
            response = yield from aiohttp.post(
                             "{}{}".format(self.entry_point, addr),
                             data=post_data,
                             headers=headers)
            if response.status != 200:
                fail_msg = "HTTP status {}".format(response.status)
            # we don't care about the response so just release
            yield from response.release()
        except Exception as e:
            fail_msg = "Caught exception: {}".format(e)

        if fail_msg != '':
            self.logger.info(
"dispatch failed: {} epoch time {} address {} func {}".format(
                fail_msg, dispatch_time, addr, func))

    @asyncio.coroutine
    def worker(self):
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

            yield from self.read_messages()

            # if read_messages() returns it means we got disconnected, retry
            self.logger.warn("Lost connection to mochad. Retrying.")
            self.reconnect_time = time.time()

def daemon_main():
    mochad_client = MochadClient("127.0.0.1", daemon.logger, args.entry_point)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(mochad_client.worker())

def errordie(message):
    prog = os.path.basename(sys.argv[0])
    sys.stderr.write("{}: error: {}\n".format(prog, message))
    sys.exit(1)


if __name__ == "__main__":
    # parse command line args
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--foreground',
            action='store_true', default=False,
            help="Don't fork; run in foreground (for debugging)")
    parser.add_argument('entry_point', help='REST API entry point URL')
    args = parser.parse_args()

    # validate entry_point URL
    parse_res = urllib.parse.urlparse(args.entry_point)
    # bail out if the url scheme is anything but HTTP(S)
    if not parse_res.scheme == 'https' and not parse_res.scheme == 'http':
        errordie("unsupported URL scheme '{}'".format(parse_res.scheme))

    # daemonize
    daemon = daemonize.Daemonize(app="mochad_dispatch", 
                                 pid="/tmp/mochad_dispatch.pid",
                                 foreground=args.foreground,
                                 action=daemon_main)
    daemon.start()
