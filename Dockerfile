FROM docker.io/alpine:3.19.1
RUN apk add --no-cache python3 py3-pillow
COPY ./basic-media-gallery.py /basic-media-gallery.py
CMD /usr/bin/python3 /basic-media-gallery.py -l 0.0.0.0 -p 80 -r /www -d /cache/thumbs.db

