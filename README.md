# Basic media gallery

Github is full of nice web gallery apps, but none work when they have been unmaintained for just 1-2 years because some javascript package has vanished. Boo! This project aims to fix that.

Design goals:
- view images in a directory using web browser. barebones image viewer with little bloat
- dynamic updates: see new images immediately when manually refreshing page
- only builtins or stable libs. this code should work in 10 years without maintenance

Security considerations:
- protect access with nginx or something else in front 
- run in container to mitigate chance of leaking server files 

# Usage

python3 basic-media-gallery -r /path/to/images -d /tmp/thumbnail-cache.db -l 127.0.0.1 -p 3000

