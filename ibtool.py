#!/usr/bin/python

import sys
import xml.etree.ElementTree as ET
import xibparser
import genlib
import getopt
import ibdump

class IBCommands(object):
	Compile = 0
	Dump = 1

def main():

	ops, args = getopt.getopt(sys.argv[1:], 'e', ['compile=', 'write=', 'dump'])

	# print ops
	# print args

	if len(args) == 0:
		print "Error: No input file given."
		sys.exit(1)
	elif len(args) > 1:
		print "Error: ibtool currently only supports one input file."
		sys.exit(1)

	command = IBCommands.Dump
	inpath = args[0] 

	_write = None
	_compile = None
	shortflags = []

	for option, value in ops:
		if option == '--compile':
			command = IBCommands.Compile
			_compile = value
		elif option == '--write':
			_write = value
		elif option == '--dump':
			command = IBCommands.Dump
		elif option == '-e':
			shortflags.append('e')

	if command is None:
		print "Error: No command given."
		sys.exit(1)

	if command == IBCommands.Compile:
		ib_compile(inpath, _write or _compile)
	elif command == IBCommands.Dump:
		ib_dump(inpath, shortflags)


def ib_compile(inpath, outpath):
	def die_if(condition, message):
		if condition:
			print message
			exit(1)

	die_if(not outpath, "ib_compile: No input path given")

	suffix = None
	if inpath.endswith(".xib"):
		suffix = "xib"
	elif inpath.endswith(".storyboard"):
		suffix = "storyboard"

	die_if(suffix is None, "ib_compile: Only .xib and .storyboard files are currently supported.")
	if suffix == 'xib':
		ib_compile_xib(inpath, outpath)
	elif suffix == 'storyboard':
		ib_compile_storyboard(inpath, outpath)

def ib_compile_xib(inpath, outpath):
	tree = ET.parse(inpath)
	root = tree.getroot()
	objects = root.iter('objects').next()
	nibroot = xibparser.ParseXIBObjects(objects)
	outbytes = genlib.CompileNibObjects([nibroot])

	with open(outpath, 'wb') as fl:
		fl.write(outbytes)

def ib_compile_storyboard(inpath, outpath):
	tree = ET.parse(inpath)
	xibparser.CompileStoryboard(tree, outpath)

def ib_dump(inpath, shortflags):
	showencoding = 'e' in shortflags
	ibdump.ibdump(inpath, showencoding)

if __name__ == '__main__':
	main()