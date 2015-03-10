#!/usr/bin/python

import os
import sys
import struct

from genlib import *




view = NibObject('UIView')
viewController = NibObject('UINavigationController')

viewController['UIView'] = view

root = NibObject('NSObject')
firstResponder = NibObject('UIProxyObject')
firstResponder['UIProxiedObjectIdentifier'] = "IBFirstResponder"
filesOwner = NibObject('UIProxyObject')
filesOwner['UIProxiedObjectIdentifier'] = "IBFilesOwner"
root['UINibTopLevelObjectsKey'] = [ filesOwner, firstResponder, viewController ]
root['UINibObjectsKey'] = [ firstResponder, filesOwner, viewController ]
root['UINibConnectionsKey'] = [ ]
root['UINibVisibleWindowsKey'] = []
root['UINibAccessibilityConfigurationsKey'] = [ ]
root['UINibTraitStorageListsKey'] = [ ]
root['UINibKeyValuePairsKey'] = [ ]






CompileNibObjects([root])

