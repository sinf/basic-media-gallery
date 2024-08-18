#!/usr/bin/env python3
# vim: set ts=2 sw=2 et:
import os
import traceback
import io
import base64
import argparse
import sqlite3
import mimetypes
import hashlib
import time
from PIL import Image
from http.server import SimpleHTTPRequestHandler, HTTPServer

def wrap_cdata(x):
  # fix filenames turning into html, in case someone creates a file named <script>
  return ''.join(c if c.isalnum() or c in './-() ' else '' for c in x)

def hazh(x):
  return hashlib.sha256(x.encode()).digest().hex()

class ContentItem:
  def __init__(self, relpath):
    self.relpath = relpath
    self.abspath = os.path.realpath(relpath)
    self.key = hazh(relpath.lstrip('.').lstrip('/'))
    self.pageid = hazh(os.path.dirname(relpath))
    self.mimetype, _ = mimetypes.guess_type(self.relpath)

  def is_supported(self):
    t=self.mimetype
    return t and (t.startswith('image/') or t.startswith('video'))

  def page_name(self):
    p = os.path.dirname(self.relpath)
    if p == '' or p == '.':
      p='(root)'
    return p

  def get_mtime(self):
    return int(os.stat(self.abspath).st_mtime)

  def read(self):
    with open(self.abspath,'rb') as f:
      return f.read()

  def thumbnabularize(self):
    buf = io.BytesIO()
    with Image.open(self.abspath) as img:
      #thumb = img.resize((64,64))
      img.thumbnail((64,64)); thumb=img
      thumb.save(buf, format='JPEG')
    buf.seek(0)
    data = buf.read()
    return data

  def html(self):
    name = wrap_cdata(os.path.basename(self.relpath))
    bad = lambda msg: f'<div><img src="/favicon.ico"/><p class="label">{name} ({msg})</p></div>'
    t = self.mimetype
    if t.startswith('image/'):
      try:
        data = self.thumbnabularize()
      except Exception as ex:
        traceback.print_exc()
        return bad('error')
      b = base64.b64encode(data).decode('ascii')
      img = f'<img src="data:image/jpeg;base64,{b}"/>'
      label = f'<p class="label">{name}</p>'
      #mt = f'<p class="mtime">{time.ctime(self.get_mtime())}</p>'
      return f'<a href="/view/{self.key}"><div>{img}{label}</div></a>'
    return bad('unsupported type')

class DbCache:
  def __init__(self, dbpath):
    self.db = sqlite3.connect(dbpath)
    cursor = self.db.cursor()
    try:
      cursor.execute('''
CREATE TABLE items (
    key TEXT PRIMARY KEY,
    data BLOB NOT NULL,
    mtime INTEGER NOT NULL
)''')
      self.db.commit()
    except sqlite3.OperationalError:
      pass #already exist

  def put(self, key, data, mtime):
    mtime=int(mtime)
    cursor = self.db.cursor()
    cursor.execute('''
INSERT INTO items (key, data, mtime)
VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET data=excluded.data, mtime=excluded.mtime
    ''', (key, data, mtime))
    self.db.commit()

  def get(self, key):
    cursor = self.db.cursor()
    cursor.execute('SELECT data, mtime FROM items WHERE key = ?', (key,))
    return cursor.fetchone() # (data,mtime)

  def getput(self, key, mtime_should_be, make_data):
    result = self.get(key)
    if result is not None:
      data, mtime = result
      #print('read cached', key, mtime)
    if result is None or int(mtime) != int(mtime_should_be):
      #print('generate new', key, mtime_should_be)
      mtime = int(mtime_should_be)
      data = make_data()
      self.put(key, data, mtime)
    return data

class Gallery:
  def __init__(self, rootdir, dbpath):
    self.rootdir = rootdir
    self.cache = DbCache(dbpath)

  def scan(self):
    print('scanning files..')
    itemsk = {}
    items = {}
    pagenam = {}
    self.page_mt = {}
    for root, dirs, files in os.walk(self.rootdir, topdown=True, followlinks=False):
      dirs[:] = sorted(dirs)
      for f in sorted(files):
        relpath = os.path.join(root, f)
        item = ContentItem(relpath)
        if item.is_supported():
          p = item.pageid
          print(relpath)
          itemsk[item.key] = item
          items[p] = items.get(p,[]) + [item]
          pagenam[p] = wrap_cdata(item.page_name())
          self.cache.getput(item.key, item.get_mtime(), item.html)
          self.page_mt[p] = max(self.page_mt.get(p,float('-inf')), item.get_mtime())
    self.items_by_pageid = items
    self.items_by_key = itemsk
    # sorted so the latest modified appear first
    self.sorted_pageid = sorted(items.keys(), key=lambda k: -self.page_mt[k])
    self.page_name_by_id = pagenam

  def _header(self):
    h='''<!DOCTYPE html>
<html>
<head>
<title>Basic media gallery</title>
<style>
html { background: black; }
* { color: white; }
.pageitem { float:left; display:inline-block; margin:0.5em; }
.pageitem img { width: 10em; border: 1px solid white; }
.pageitem p { margin: 0.1em 0.1em 0 0.1em; }
.label { max-width: 10em; }
</style>
</head>
<body>'''
    h+='<a href="/">index</a><br/>'
    if self.sorted_pageid:
      h+=f'<a href="/page/{self.sorted_pageid[0]}">most recent</a><br/>'
    return h

  def _footer(self):
    return '''</body></html>'''

  def index(self):
    self.scan()
    h=self._header()
    h+='<ol>'
    for p in self.sorted_pageid:
      nam = self.page_name_by_id[p]
      h += f'<li><a href="/page/{p}">{nam}</a></li>'
    h += '</ol>'
    h+=self._footer()
    return h

  def page(self, pageid):
    self.scan()
    if pageid not in self.sorted_pageid:
      return self._header() + '<h1>page not found</h1>' + self._footer()
    h=self._header()
    cur = self.sorted_pageid.index(pageid)
    if cur > 0:
      prev=f'/page/{self.sorted_pageid[cur-1]}'
      h+=f'<a href="{prev}">previous page</a><br/>'
    else:
      h+=f'no previous page<br/>'
    if cur < len(self.sorted_pageid)-1:
      Next=f'/page/{self.sorted_pageid[cur+1]}'
      h+=f'<a href="{Next}">next page</a><br/>'
    else:
      h+=f'no next page<br/>'
    nam = self.page_name_by_id[pageid]
    h+=f'<p>This page: {nam} , {time.ctime(self.page_mt[pageid])} , {len(self.items_by_pageid[pageid])} items</p>'
    h+='<ol>'
    mi = [(it,it.get_mtime()) for it in self.items_by_pageid[pageid]]
    for item, mt in sorted(mi, key=lambda x: -x[1]):
      h += '<li class="pageitem">'
      h += self.cache.getput(item.key, item.get_mtime(), item.html)
      h += '</li>'
    h+='</ol>'
    h+=self._footer()
    return h 

class CustomHandler(SimpleHTTPRequestHandler):

  def _ok(self, typ, content):
    self.send_response(200)
    self.send_header('Content-type', typ)
    self.end_headers()
    self.wfile.write(content)

  def do_GET(self):
    global the_gallery
    try:
      if self.path == '/favicon.ico':
        return self._ok('image/x-icon', b'\x00\x00\x01\x00\x01\x00  \x10\x00\x01\x00\x04\x00\xe8\x02\x00\x00\x16\x00\x00\x00(\x00\x00\x00 \x00\x00\x00@\x00\x00\x00\x01\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x1e!\x1f\x00142\x00ADB\x00OQO\x00dge\x00sus\x00\x81\x84\x82\x00\x8e\x91\x8f\x00\x9c\x9f\x9d\x00\xac\xb0\xad\x00\xbe\xc2\xbf\x00\xca\xce\xcb\x00\xda\xdd\xdb\x00\xee\xf1\xef\x00\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xdau1$h\xac\xdf\xff\xff\xff\xff\xff\xff\xff\xff\xb3\x00\x00\x00\x00\x00\x00\x04\x9f\xff\xff\xff\xff\xff\xff\xe4\x00\x00\x00\x00\x00\x00\x00\x00\x0e\xff\xff\xff\xff\xff\xfd \x00\x00\x00\x00\x00\x00\x00\x00\x0e\xff\xff\xff\xff\xff\xe3\x00\x00\x00\x02gv \x00\x00\x0e\xff\xff\xff\xff\xffp\x00\x00\x06\xcf\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xfd\x00\x00\x00\x7f\xff\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xf9\x00\x00\x04\xff\xff\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xf1\x00\x00\x0b\xff\xff\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xd0\x00\x00/\xff\xff\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xb0\x00\x00\x7f\xff\xff\xff\xff\xf9\x00\x00\x0e\xff\xff\xff\xff\xa0\x00\x00\xbf\xff\xff\x88\x88\x84\x00\x00\x0e\xff\xff\xff\xff\x90\x00\x00\xbf\xff\xff@\x00\x00\x00\x00\x0e\xff\xff\xff\xff\x80\x00\x00\xcf\xff\xff@\x00\x00\x00\x00\x0e\xff\xff\xff\xff\x80\x00\x00\xcf\xff\xff@\x00\x00\x00\x00\x0e\xff\xff\xff\xff\x90\x00\x00\xbf\xff\xff@\x00\x00\x00\x00\x0e\xff\xff\xff\xff\xa0\x00\x00\xaf\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xc0\x00\x00_\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xe0\x00\x00\r\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xf5\x00\x00\x07\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfb\x00\x00\x00\xbf\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe@\x00\x00\n\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xc0\x00\x00\x00}\xef\xff\xff\xdaK\xff\xff\xff\xff\xff\xff\xfa\x00\x00\x00\x00&\x87Q\x00\x05\xff\xff\xff\xff\xff\xff\xff\xa0\x00\x00\x00\x00\x00\x00\x00\x00\xdf\xff\xff\xff\xff\xff\xff\xfc0\x00\x00\x00\x00\x00\x00\x00\x8f\xff\xff\xff\xff\xff\xff\xff\xea0\x00\x00\x00\x00\x00\x05\xaf\xff\xff\xff\xff\xff\xff\xff\xff\xfd\xa8S\x12F\x9b\xef\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
      elif self.path.startswith('/page/'):
        pageid = self.path[6:].replace('/','').replace('.','')
        p = the_gallery.page(pageid)
        self._ok('text/html', p.encode())
      elif self.path.startswith('/view/'):
        itemid = self.path[6:].replace('/','').replace('.','')
        item = the_gallery.items_by_key[itemid]
        self._ok(item.mimetype, item.read())
      elif self.path == '/':
        p = the_gallery.index()
        self._ok('text/html', p.encode())
      else:
        print('not found', self.path)
        self.send_error(404, 'Page not found')
    except Exception as ex:
      traceback.print_exc()
      self.send_error(404, 'Page not found')

def run():
  arp = argparse.ArgumentParser()
  arp.add_argument('-l', '--listen-addr', default='127.0.0.1', help='[127.0.0.1]')
  arp.add_argument('-p', '--port', type=int, default=3000, help='[3000]')
  arp.add_argument('-r', '--root-dir', type=str, required=True)
  arp.add_argument('-d', '--db-path', type=str, required=True)
  args=arp.parse_args()
  server_address = (args.listen_addr, args.port)
  global the_gallery
  the_gallery = Gallery('.', args.db_path)
  os.chdir(args.root_dir)
  the_gallery.scan()
  print('Root dir', args.root_dir)
  print('Database', args.db_path)
  print('Starting httpd server on', server_address)
  httpd = HTTPServer(server_address, CustomHandler)
  httpd.serve_forever()

if __name__ == '__main__':
  run()

