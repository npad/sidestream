#! /usr/bin/python

"""
Make up a bunch of files with assorted content of varying sizes, named per their size.
"""
import os

def sizename(name):
    """
    Rename a file to indicate it's size, preserving the path and extention
    """
    try:
        dir=name[0:name.rindex("/")]+"/"
    except ValueError:
        dir=""
    ext=name[name.rfind("."):]
    newname=dir+str(os.path.getsize(name))+ext
    os.rename(name, newname)	# errors fall through
    print "Created", newname

text = """
%06d
This paragraph is rather unremarkable, except that it is exactly
512 bytes long, including carriage returns and line feeds.
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz

"""

def writetext(count):
    f=file("temp.txt", "w")
    for i in range(count):
        f.write(text%i)
    f.close()
    sizename("temp.txt")

# main
# files of size 2^n from 512B to 1 MB
sz = 1
for n in range(12):
    writetext(sz)
    sz=sz<<1


