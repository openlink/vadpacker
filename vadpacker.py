#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# VADPacker - A small tool to create Virtuoso VAD packages
# Copyright (C) 2012 OpenLink Software <opensource@openlinksw.com>
#
# This project is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; only version 2 of the License, dated June 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
#

import hashlib
import struct
import os
import elementtree.ElementTree as ET
import sys
import argparse

# settings
verbose = False
prefix = "vad/data/"

# Our hash
ctx = hashlib.md5()

def vadWriteChar(s, val):
    """
    Writes a single char to a VAD file and
    updates the hash while at it.

    s -- The stream to write to
    val -- The value to write.
    ctx -- The hash object to update.
    """
    s.write(val)
    ctx.update(val)


def vadWriteLong(s, val):
    """
    Writes a 32bit integer to a VAD file and
    updates the hash while at it.
    The long will be written with big endian
    byte order.

    s -- The stream to write to
    val -- The value to write.
    ctx -- The hash object to update.
    """
    be = struct.pack('>i', val)
    s.write(be)
    ctx.update(be)


def vadWriteString(s, val):
    """
    Writes a string to a VAD file and
    updates the hash while at it. A string
    in a VAD is always prefixed with the
    length of the string.

    s -- The stream to write to
    val -- The value to write.
    ctx -- The hash object to update.
    """
    vadWriteLong(s, len(val))
    s.write(val)
    ctx.update(val)


def vadWriteRow(s, name, data):
    # write the row name
    vadWriteChar(s, chr(182))
    vadWriteString(s, name)

    # write the row contents
    vadWriteChar(s, chr(223))
    vadWriteString(s, data)


def vadWriteFile(s, name, fname):
    """
    Writes a file to a VAD file and
    updates the hash while at it. The file is
    supposed to be a file on the local filesystem
    rather than in the DAV.

    s -- The stream to write to
    name -- The name of the file in the VAD.
    fname -- The path of the local file.
    ctx -- The hash object to update.
    """
    with open(fname) as f:
        # write the row name
        vadWriteChar(s, chr(182))
        vadWriteString(s, name)

        # write the row contents
        vadWriteChar(s, chr(223))
        
        # write the file size
        vadWriteLong(s, os.path.getsize(fname))
        # write the file contents
        val = f.read(4069)
        while val:
            s.write(val)
            ctx.update(val)
            val = f.read(4069)


def createVad(stickerUrl, s):
    global prefix
    
    # 1. write a clean text warning
    vadWriteRow(s, 'VAD', 'This file consists of binary data and should not be touched by hands!')

    # 2. Write the contents of the sticker
    with open(stickerUrl) as sticker:
        vadWriteRow(s, 'STICKER', sticker.read())

    # 3. Write all the files defined in the sticker
    stickerTree = ET.parse(stickerUrl)
    for f in stickerTree.findall("resources/file"):
        resType = f.get("type")
        resSource = f.get("source")
        targetUri = f.get("target_uri")
        sourceUri = f.get("source_uri", "%s/%s%s" % (os.path.dirname(os.path.realpath(stickerUrl)), prefix, targetUri))
        if resSource == "dav":
            print >> sys.stderr, "Cannot handle DAV resources"
            exit(1)
        if verbose:
            print >> sys.stderr, "Packing file %s as %s" % (sourceUri, targetUri)
        vadWriteFile(s, targetUri, sourceUri)

    # 4. Write the md5 hash
    vadWriteRow(s, 'MD5', ctx.hexdigest())


def main():
    global verbose
    global prefix

    # Command line args
    optparser = argparse.ArgumentParser(description="Virtuoso VAD Packer\n(C) 2012 OpenLink Software.")
    optparser.add_argument('--output', '-o', type=str, required=True, metavar='PATH', dest='output', help='The destination VAD file.')
    optparser.add_argument('--verbose', '-v', action="store_true", dest="verbose", default=False, help="Be verbose about the packing.")
    optparser.add_argument('--prefix', '-p', type=str, default="vad/data/", metavar='PREFIX', dest='prefix', help='An optional prefix to be used for locating local files. Defaults to "vad/data/"')
    optparser.add_argument("stickerfile", type=str, help="The Sticker file for the VAD")

    # extract arguments
    args = optparser.parse_args()
    verbose = args.verbose
    prefix = args.prefix

    # Open the target file and write the VAD
    with open(args.output, "wb") as s:
        if verbose:
            print >> sys.stderr, "Packing VAD file from sticker '%s': %s" % (args.stickerfile, args.output)
        createVad(args.stickerfile, s)


if __name__ == "__main__":
    main()
