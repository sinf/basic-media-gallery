# Basic media gallery

Github is full of nice web gallery apps, but none work when they have been unmaintained for just 1-2 years because some javascript package has vanished from the internet. Boo! This project aims to fix that.

Design goals:
- barebones web photo directory viewer
- see new images immediately when manually refreshing page
- this code should still run in 10 years without maintenance (only builtins and PIL)
- only few concurrent clients (fix with caching proxy if needed)

Security considerations:
- no https, no authentication, no (D)DOS protection (protect with nginx/whatever in front)
- server only serves files it has indexed and accepts no filename input, but run in container to be sure

# Usage

testing
```
python3 basic-media-gallery.py -r /path/to/images -d /tmp/thumbnail-cache.db -l 127.0.0.1 -p 3000
```

in container
```
ln -s /foo/bar ./www
mkdir ./cache
sh run.sh
```

# Structure

basic-media-gallery.py: the main program
some file .db: database of thumbnails
some directory: directory tree containing media files

