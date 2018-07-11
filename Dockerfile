FROM alpine:3.6
MAINTAINER Ya Chang <yachang@google.com>
# Install all the standard packages we need
RUN apk update && apk add python python-dev py2-pip gcc g++ libc-dev bash rsync tar
# Install all the python requirements
ADD requirements.txt /requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt -U
# Install scraper
ADD scamper.py /scamper.py
RUN chmod +x /scamper.py
ADD scamper /scamper
RUN chmod +x /scamper
ADD ss /ss
RUN chmod +x /ss
ADD timeout /timeout
RUN chmod +x /timeout
EXPOSE 7070
# The :- syntax specifies a default value for the variable, so the deployment
# need not set it unless you want to specify something other than that default.
CMD python /scamper.py
