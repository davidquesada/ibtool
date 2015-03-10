# ibtool
My attempt to reverse engineer the iOS Nib format (used for storing compiled
interface files) and create a tool to do similar things as Apple's ibtool.

## Usage
Currently, ibtool supports only compiling XIB and storyboard files and
printing NIB files in a readable way. (Only works with Interface Builder
documents for iOS, not OS X.)

    Usage: ibtool.py [OPTIONS] input-file
      --dump                       dump the contents of a NIB file in a readable format
      --compile <output pathname>  compile a XIB or storyboard file to a binary format
      -e                           show type encodings when dumping a NIB file

If no command is specified, ibtool will assume --dump,
i.e. `ibtool.py --dump somefile.nib` and `ibtool.py somefile.nib` are equivalent.

## Notes
The set of Interface Builder features supported by this application is very limited,
and requires specific functionalities to be manually added, so certain usages of
unimplemented views, scenes, layout constraints, or size classes may fail to compile
or result in NIBs that are missing functionality.
