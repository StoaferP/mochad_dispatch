from setuptools import setup

VERSION = "1.0.0"

REQUIRES = [
    "paho-mqtt",
    "pytz",
]

setup(
    name="mochad_dispatch",
    version=VERSION,
    description="mochad_dispatch is a daemon written in Python that translates mochad's tcp-based events to MQTT messages",
    url="https://github.com/StoaferP/mochad_dispatch",
    download_url="https://github.com/StoaferP/mochad_dispatch/archive/{}.zip".format(VERSION),
    author="Chris Przybycien",
    author_email="chrisisdiy@gmail.com",
    license="MIT",
    packages=["mochad_dispatch"],
    long_description=open("README.rst").read(),
    zip_safe=False,
    install_requires=REQUIRES,
    test_suite="tests",
    entry_points={"console_scripts": ["mochad_dispatch = mochad_dispatch.main:main"]},
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.4",
    ],
)
