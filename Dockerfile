FROM ubuntu:latest
MAINTAINER Ya Chang <yachang@google.com>
# Install all the standard packages we need
RUN apt-get update && apt-get install -y python python-pip make iproute2 coreutils
# Install all the python requirements
ADD requirements.txt /requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt -U
# Install scraper
ADD scamper.py /scamper.py
RUN chmod +x /scamper.py

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

CMD ["python", "/scamper.py", "--logpath", "/var/spool/scamper"]
