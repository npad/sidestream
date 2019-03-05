FROM ubuntu:latest
MAINTAINER Ya Chang <yachang@google.com>
# Install all the standard packages we need
RUN apt-get update && apt-get install -y python python-pip make iproute2 coreutils
# Install all the python requirements
ADD requirements.txt /requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt -U

RUN mkdir /source
ADD source/scamper-cvs-20190113 /source/
RUN chmod +x /source/configure
RUN /source/configure
RUN cd /source
RUN ls -l /source/scamper
RUN make
RUN make install

RUN chmod +x /usr/local/bin/scamper
RUN chmod 4755 /usr/local/bin/scamper

FROM golang:alpine as build

RUN apk update && apk add bash git pkgconfig
ADD . /go/src/github.com/npad/sidestream/blob/scamper
RUN go build github.com/npad/sidestream/blob/scamper/main.go
RUN chmod -R a+rx /go/bin/sidestream

CMD ["/go/bin/sidestream"]
