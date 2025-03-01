===============
mochad_dispatch
===============

**mochad_dispatch** allows you to connect your X10 security devices (door/window sensors, motion sensors, remotes) to home automation software like `OpenHAB <http://www.openhab.org/>`_, `Home Assistant <https://home-assistant.io/>`_ or `Domoticz <https://domoticz.com/>`_

What exactly does it do?
========================
**mochad_dispatch** connects to `mochad <https://sourceforge.net/projects/mochad/>`_ (which reads messages from a USB receiver like the X10 CM15a) and listens for X10 security and button-press messages which now includes power line receipt of control messages (Rx PL) then publishes those to an MQTT broker.

It will automatically reconnect to both mochad and the MQTT broker.  However, if a reconnect attempt fails for 60 seconds straight, **mochad_dispatch** will give up and exit.

Usage description
-----------------
::

    usage: mochad_dispatch [-h] [-s SERVER] [-f] [-l] [-m MQTT_DISCOVERY] [--cafile CAFILE] [-c HOUSECODES] dispatch_uri

    positional arguments:
    dispatch_uri          dispatch messages to this URI. mqtt://host:port[,user=username,pass=password]

    options:
    -h, --help            show this help message and exit
    -s SERVER, --server SERVER
                            IP/host of server running mochad (default 127.0.0.1)
    -f, --foreground      Don't fork; run in foreground (for debugging)
    -l, --legacy          Use legacy X10 topic format (default is HomeAssistant MQTT auto discovery format)
    -m MQTT_DISCOVERY, --mqtt-discovery MQTT_DISCOVERY
                            MQTT discovery for Home Assistant (default homeassistant/5A0uqYZF2_mochad_dispatch)
    --cafile CAFILE       File containing trusted CA certificates
    -c HOUSECODES, --housecodes HOUSECODES
                            House codes for X10 devices (default ABCDEFGHIJKLMNOP)

How do I use it?
================
Run mochad_dispatch with a mochad hostname and a MQTT URI
::

    $ mochad_dispatch -s hal9000 mqtt://mqtt.example.com:1883

Then subscribe to the appropriate device topics.  The general format is

    X10/**MOCHAD_HOST**/**KIND**/**ADDRESS**

where **KIND** is **security** for RFSEC alerts and **button** for button presses from an X10 remote.  Note that **button** events are sent at QoS 0 and without the retain flag so they will not persist.

What about MQTT with TLS?
-------------------------
For TLS support use the '--cafile' option like so
::

    $ mochad_dispatch -s hal9000 --cafile /etc/pki/tls/cert.pem mqtt://mqtt.example.com:8883

What about MQTT username and password?
--------------------------------------
For username and password use the ',user=theusername,pass=thepassword' appended to the URI like so
::

    $ mochad_dispatch -s hal9000 mqtt://mqtt.example.com:1883,user=theusername,pass=thepassword

What about house code filtering?
--------------------------------
You can also add filtering by house code as well using the -c/--housecodes optino and list your codes that you want to use. The default is all A thru P. To use just add -c AD or any other combination of house codes.
::
    
    $ mochad_dispatch -s hal9000 -c AD mqtt://mqtt.example.com:1883

Home Assistant Integration
==========================
Mochad Dispatch has the ability to dynamcally add binary sensors for state of devices. This is the defualt opertaion. These devices can used to trigger other automations.

To switch off the Home Addistant integration through MQTT discovery, use -l/--legacy option.

To change the mqtt category for the MQTT discovery to not use the default "homeassistant" or change the unique id for the node default of 5A0uqYZF2_mochad_dispatch
::

    $ mochad_dispatch -s hal9000 -c AD --mqtt-discovery homeassistant/5A0uqYZF2_mochad_dispatch mqtt://mqtt.example.com:1883

Also, through configuration in Home Assistant for the X10 security devices, you can use configure this under the '''mqtt:''' heading. See https://www.home-assistant.io/integrations/alarm_control_panel.mqtt/
::

    mqtt:
    - alarm_control_panel:
        name: "Alarm Panel"
        state_topic: "X10/hal9000/security/C8:21:B2"
        value_template: "{{value_json.command}}"

Troubleshooting
===============
mochad_dispatch has been tested with mochad 0.1.17 and Mosquitto 1.4.3

Start by making sure your MQTT broker is relaying X10 messages by subscribing to the topic

    X10/#

For example, using the mosquitto broker:
::

    $ mosquitto_sub -v -t X10/#
    X10/hal9000/security/C8:21:B2 {"dispatch_time": "2016-02-18T18:36:12.147877+00:00", "func": {"event_type": "contact", "event_state": "normal", "device_type": "DS10A", "delay": "min"}}
    X10/hal9000/security/33:8C:30 {"dispatch_time": "2016-02-18T18:30:42.763780+00:00", "func": {"event_state": "normal", "device_type": "DS10A", "delay": "min", "event_type": "contact"}}

Dockerized App
==============
Build the docker image (using the Dockerfile based on the jfloff/alpine-python image) and run the mochad_dispatch command.  IMPORTANT: you must use the "-f" flag (to disable background/daemon mode) else the docker container will exit immediately.
::

    $ docker build -t mochad_dispatch .
    $ docker run -d -it mochad_dispatch mochad_dispatch -s hal9000 mqtt://mqtt.example.com:1883 -f

Dockerized App Full Stack Example
=================================
Run (and background) individual Docker containers to provide an MQTT broker, a MOCHAD daemon, and a MOCHAD_DISPATCH instance (assuming you've already built an image as described above):
::

	$ docker run -d --name=mosquitto -p 1883:1883 -p 9001:9001 sourceperl/mosquitto
	$ docker run -d --name=mochad -p 1099:1099 --device "/dev/bus/usb/005" jshridha/mochad:latest
	$ docker run --link mosquitto --link mochad:hal9000 -d -it mochad_dispatch mochad_dispatch -s hal9000 mqtt://mosquitto:1883 -f
