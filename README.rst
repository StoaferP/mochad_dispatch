mochad_dispatch
===============
**mochad_dispatch** allows you to connect your X10 security devices (door/window sensors, motion sensors, remotes) to home automation software like `OpenHAB <http://www.openhab.org/>`_, `Home Assistant <https://home-assistant.io/>`_ or `Domoticz <https://domoticz.com/>`_

What exactly does it do?
------------------------
**mochad_dispatch** connects to `mochad <https://sourceforge.net/projects/mochad/>`_ (which reads messages from a USB receiver like the X10 CM15a) and listens for X10 security messages then publishes those to an MQTT broker.

How do I use it?
----------------
Run mochad_dispatch with a mochad hostname and a MQTT URI
::

    $ mochad_dispatch -s hal9000 mqtt://localhost:1833

Then subscribe to the appropriate device topics.  The general format is

    X10/**MOCHAD_HOST**/security/**ADDRESS**

Troubleshooting
---------------
Start by making sure your MQTT broker is relaying X10 messages by subscribing to the topic

    X10/#

For example, using the mosquitto broker:
::

    $ mosquitto_sub -v -t X10/#
    X10/hal9000/security/C8:21:B2 {"dispatch_time": "2016-02-18T18:36:12.147877+00:00", "func": {"event_type": "contact", "event_state": "normal", "device_type": "DS10A", "delay": "min"}}
    X10/hal9000/security/33:8C:30 {"dispatch_time": "2016-02-18T18:30:42.763780+00:00", "func": {"event_state": "normal", "device_type": "DS10A", "delay": "min", "event_type": "contact"}}

