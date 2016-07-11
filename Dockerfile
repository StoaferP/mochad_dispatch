FROM jfloff/alpine-python:3.4
COPY . /src
RUN cd /src; python setup.py install