#!/bin/sh
docker build . -t localhost/basic-media-gallery
mkdir -pv www cache
docker run -it --rm -v ./www:/www:ro -v ./cache:/cache -p 8000:80 localhost/basic-media-gallery

