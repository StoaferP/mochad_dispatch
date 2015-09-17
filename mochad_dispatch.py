import asyncio
import daemonize
import sys
import time
import logging, logging.handlers



class MochadClient:
    """ MochadClient object
    
    """
    def __init__(self, host, logger):
        self.host = host
        self.logger = logger
        self.reconnect_time = 0
        self.reader = None
        self.writer = None

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
                self.logger.warn("Lost connection to mochad")
                break
            # dispatch RFSEC messages
            if line[15:23] == b'Rx RFSEC':
                asyncio.Task(self.dispatch_message(line.decode("utf-8")))

    @asyncio.coroutine
    def dispatch_message(self, message):
        self.logger.info(message)

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
                continue

            # if we make it this far we've successfully connected, reset the
            # reconnect time
            self.reconnect_time = 0
            self.logger.info("Connected to mochad")

            yield from self.read_messages()

            # if read_messages() returns it means we got disconnected, retry
            self.reconnect_time = time.time()

def daemon_main():
    mochad_client = MochadClient("127.0.0.1", daemon.logger)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(mochad_client.worker())



if __name__ == "__main__":
    daemon = daemonize.Daemonize(app="mochad_dispatch", 
                                 pid="/var/run/mochad_dispatch.pid",
                                 action=daemon_main)
    daemon.start()
