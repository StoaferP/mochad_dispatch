from setuptools import setup

REQUIRES = [
    'aiohttp',
    'daemonize',
    'paho-mqtt',
    'pytz',
]

setup(
    name='mochad_dispatch',
    version='0.1.4',
    description="mochad_dispatch is a daemon written in Python that translates mochad's tcp-based events into REST or MQTT",
    url='https://github.com/ChrisArgyle/mochad_dispatch',
    author='Chris Przybycien',
    author_email='chrisisdiy@gmail.com',
    license='MIT',
    packages=['mochad_dispatch'],
    zip_safe=False,
    install_requires=REQUIRES,
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'mochad_dispatch = mochad_dispatch.main:main'
        ]
    },
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: Linux',
        'Programming Language :: Python :: 3.4',
    ],
)
