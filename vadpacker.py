#!/usr/bin/env python2
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
import datetime
import re
import glob

# settings
verbose = False
prefix = "vad/data/"
targetprefix = ""

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


def createVad(stickerUrl, variables, files, s):
    global prefix
    global targetprefix

    # write a clean text warning
    vadWriteRow(s, 'VAD', 'This file consists of binary data and should not be touched by hands!')

    # Write the contents of the sticker
    sticker = ''
    with open(stickerUrl) as stickerFile:
        sticker = stickerFile.read()
        # replace all given variables
        for key in variables:
            sticker = sticker.replace('$%s$' % key, variables[key]);
        # replace well-known variables
        sticker = sticker.replace('$PACKDATE$', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        # Check if any variable values are missing
        missingVals = list(set(re.findall('\$([^\$]+)\$', sticker)))
        if len(missingVals) > 0:
            print >> sys.stderr, 'Missing variable values: %s' % ', '.join(missingVals)
            exit(1)

    # Change the working dir to the root of the sticker file
    os.chdir(os.path.dirname(os.path.abspath(stickerUrl)))

    # Expand any wildcards in the sticker's resource list
    resources = ""
    stickerTree = ET.fromstring(sticker)
    for f in stickerTree.findall("resources/file"):
        overwrite = f.get("overwrite") or 'yes'
        resType = f.get("type")
        resSource = f.get("source")
        targetUri = f.get("target_uri")
        sourceUri = f.get("source_uri")
        owner = f.get("dav_owner") or "dav"
        grp = f.get("dav_grp") or "administrators"
        perms = f.get("dav_perm")

        # and add a new line for each globbed one
        for filename in glob.glob(sourceUri):
            if targetUri.endswith('/'):
                targetUri += filename
            resources += '  <file overwrite="%s" type="%s" source="data" source_uri="%s" target_uri="%s" dav_owner="%s" dav_grp="%s" dav_perm="%s" makepath="yes"/>\n' % (overwrite, resType, filename, targetUri, owner, grp, perms);

    # Create the XML blob of additional files to add
    if len(targetprefix) > 0 and not targetprefix.endswith('/'):
        targetprefix = targetprefix + '/'
    for f in files:
        f = re.sub('^./', '', f)
        executable = 0
        if f.endswith('.vsp') or f.endswith('.vspx') or f.endswith('.php'):
            executable = 1
        resources += '  <file overwrite="yes" type="dav" source="data" source_uri="%s" target_uri="%s%s" dav_owner="dav" dav_grp="administrators" dav_perm="11%d10%d10%dNN" makepath="yes"/>\n' % (f, targetprefix, f, executable, executable, executable);

    # Replace the resources in the sticker with our expanded ones the dumb way (we want to preserve the original sticker formatting if possible)
    sticker = re.sub('<resources>.*</resources>', '<resources>\n' + resources + '</resources>\n', sticker, 0, re.DOTALL)

    # Write the final sticker contents
    vadWriteRow(s, 'STICKER', sticker)

    # Write all the files defined in the sticker
    stickerTree = ET.fromstring(sticker)
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

    # Write the md5 hash
    vadWriteRow(s, 'MD5', ctx.hexdigest())


def buildVariableMap(variables):
    "Converts a list of key=val pairs into a map"
    values = {}
    for v in variables:
        # small hack to work around the fact that argparse gives us a list in a list which I do not understand
        v = v[0]
        x = v.split('=')
        if len(x) != 2:
          print >> sys.stderr, "Invalid variable value: '%s'. Expecting 'key=val'." % v
          exit(1)
        values[x[0]] = x[1]
    return values


def main():
    global verbose
    global prefix
    global targetprefix

    # Command line args
    optparser = argparse.ArgumentParser(description="Virtuoso VAD Packer\n(C) 2012 OpenLink Software.")
    optparser.add_argument('--output', '-o', type=str, required=True, metavar='PATH', dest='output', help='The destination VAD file.')
    optparser.add_argument('--verbose', '-v', action="store_true", dest="verbose", default=False, help="Be verbose about the packing.")
    optparser.add_argument('--prefix', '-p', type=str, default="vad/data/", metavar='PREFIX', dest='prefix', help='An optional prefix to be used for locating local files. Defaults to "vad/data/"')
    optparser.add_argument('--targetprefix', '-t', type=str, default="", metavar='PREFIX', dest='targetprefix', help='An optional prefix to be used for target_uri values in additional resource entries created through the files list."')
    optparser.add_argument('--var', type=str, nargs='*', metavar='VAR', dest='var', default=[], action="append", help='Set variable values to be replaced in the sticker. Example: --variable VARNAME=xyz')
    optparser.add_argument("stickerfile", type=str, help="The Sticker file for the VAD")
    optparser.add_argument("files", type=str, nargs="*", default=[], help="An optional list of files to pack in addition to the files in the sticker. vadpacker will create additional resource entries with default permissions (dav, administrators, 111101101NN for vsp and php pages, 110100100NN for all other files) in the packed sticker using the relative paths of the given files.")

    # extract arguments
    args = optparser.parse_args()
    verbose = args.verbose
    prefix = args.prefix
    targetprefix = args.targetprefix

    # Open the target file and write the VAD
    with open(args.output, "wb") as s:
        if verbose:
            print >> sys.stderr, "Packing VAD file from sticker '%s': %s" % (args.stickerfile, args.output)
        createVad(args.stickerfile, buildVariableMap(args.var), args.files, s)


if __name__ == "__main__":
    main()
