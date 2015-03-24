
from genlib import *

'''
TODO:
- Translate autoresizing masks into layout constraints.
'''


# Parses xml Xib data and returns a NibObject that can be used as the root
# object in a compiled NIB archive.
# element: The element containing the objects to be included in the nib.
#          For standalone XIBs, this is typically document->objects
#          For storyboards, this is typically document->scenes->scene->objects
def ParseXIBObjects(element, context = None, resolveConnections = True, parent = None):

	toplevel = []

	context = context or ArchiveContext()

	for nib_object_element in element:
		obj = __xibparser_ParseXIBObject(context, nib_object_element, parent)
		if obj:
			toplevel.append(obj)

	if resolveConnections:
		context.resolveConnections()

	root = NibObject("NSObject")
	root['UINibTopLevelObjectsKey'] = toplevel
	root['UINibConnectionsKey'] = context.connections# __xibparser_resolveConnections(ib_connections, ib_objects)
	root['UINibObjectsKey'] = list(toplevel)
	root['UINibObjectsKey'].extend(context.extraNibObjects)

	return root


def CompileStoryboard(tree, foldername):

	import os
	if os.path.isdir(foldername):
		import shutil
		shutil.rmtree(foldername)

	os.mkdir (foldername)

	root = tree.getroot()
	init = root.attrib.get('initialViewController')

	scenesNode = root.iter('scenes').next()

	identifierMap = { }
	idToNibNameMap = { }
	idToViewControllerMap = { }

	# Make some constants before

	fowner = NibProxyObject("IBFilesOwner")
	sbplaceholder = NibProxyObject('UIStoryboardPlaceholder')

	# A list of tuples containing:
	#  - The view controller of the scene.
	#  - The root objects for the scene.
	#  - The view controller nib name.
	# We can't write the scene nibs as we read the scenes, because some things might depend on having
	# seen all the scenes. (e.g. Segues, which need to know how to translate ID into storyboardIdentifier)
	scenesToWrite = []

	for sceneNode in scenesNode:

		toplevel = []

		sceneID = sceneNode.attrib['sceneID']
		objects = sceneNode.iter('objects').next()
		viewController = None
		viewControllerNibName = None

		context = ArchiveContext()
		context.isStoryboard = True

		for elem in objects:

			obj = __xibparser_ParseXIBObject(context, elem, None)
			if not obj:
				continue
			viewNibFilename = None
			
			toplevel.append(obj)
			context.toplevel.append(obj)

		viewController = context.storyboardViewController
		if not viewController:
			raise Exception("Storyboard scene did not have associated view controller.")

		context.resolveConnections()
			
		viewControllerNibName = viewController.xibattributes.get('storyboardIdentifier') or "UIViewController-" + viewController.xibattributes['id']
		identifierMap[viewControllerNibName] = viewControllerNibName
		idToNibNameMap[viewController.xibattributes['id']] = viewControllerNibName
		idToViewControllerMap[viewController.xibattributes['id']] = viewController
		view = viewController.properties.get('UIView')
		if view:
			del viewController.properties['UIView']
			context.extraNibObjects.remove(view)  # Don't encode the view in the scene nib's objects.

			view.extend('UISubviews', context.viewControllerLayoutGuides)

			ViewConnection = NibObject('UIRuntimeOutletConnection')
			ViewConnection['UILabel'] = 'view'
			ViewConnection['UISource'] = fowner
			ViewConnection['UIDestination'] = view

			viewNibFilename = "%s-view-%s" % (viewController.xibattributes.get('id'), view.repr().attrib.get('id'))

			root = NibObject('NSObject')
			root['UINibTopLevelObjectsKey'] = [ view ] # + context.viewConnections
			root['UINibObjectsKey'] = [ view ] # + context.viewConnections
			root['UINibConnectionsKey'] = [ ViewConnection ] + context.viewConnections
			# root['UINibConnectionsKey']

			with open("%s/%s%s" % (foldername, viewNibFilename, ".nib"), 'wb') as fl:
				fl.write(CompileNibObjects([root]))


		# Not setting the UINibName key is acceptable.
		# I'm guessing things like UINavigationController scenes do that.
		print 'viewNibFilename:', viewNibFilename
		viewController['UINibName'] = viewNibFilename
		
		toplevel.append(fowner)
		toplevel.append(sbplaceholder)

		FilesOwnerConnection = NibObject('UIRuntimeOutletConnection')
		FilesOwnerConnection['UILabel'] = 'sceneViewController'
		FilesOwnerConnection['UISource'] = fowner
		FilesOwnerConnection['UIDestination'] = viewController

		StoryboardConnection = NibObject('UIRuntimeOutletConnection')
		StoryboardConnection['UILabel'] = 'storyboard'
		StoryboardConnection['UISource'] = viewController
		StoryboardConnection['UIDestination'] = sbplaceholder
		viewController.sceneConnections.append(StoryboardConnection)
		
		nibconnections = [ FilesOwnerConnection, StoryboardConnection ] + context.sceneConnections

		root = NibObject("NSObject")
		root['UINibTopLevelObjectsKey'] = toplevel
		root['UINibConnectionsKey'] = nibconnections
		root['UINibObjectsKey'] = list(toplevel)
		root['UINibObjectsKey'].extend(context.extraNibObjects)

		scenesToWrite.append( (viewController, root, viewControllerNibName) )


	# Do some additional processing before the scenes are written.
	# This includes resolving references for storyboard segues and assigning 
	# all the appropriate values for relationship segues in the storyboard.
	for finalScene in scenesToWrite:

		viewController, root, viewControllerNibName = finalScene

		for segue in viewController.get('UIStoryboardSegueTemplates') or []:
			dest = segue['UIDestinationViewControllerIdentifier']
			if isinstance(dest, NibString):
				dest = dest._text
			if isinstance(dest, basestring):
				segue['UIDestinationViewControllerIdentifier'] = idToNibNameMap[dest]

		# This is kinda ugly. It's inspired by the need to set certain properties on the view controller,
		# like UIParentViewController, which we only want set when we're including the view controller
		# inside another view controller's nib. We make a copy of the properties array, add what we need,
		# then put the dict back when we're done.
		resetProperties = [ ]

		if viewController.relationshipsegue is not None:
			segue = viewController.relationshipsegue
			relationship = segue.attrib['relationship']
			if relationship == 'rootViewController':
				rootViewController = idToViewControllerMap[segue.attrib['destination']]
				viewController['UIChildViewControllers'] = [rootViewController]
				viewController['UIViewControllers'] = [rootViewController]

				if viewController.sceneConnections:
					root['UINibConnectionsKey'].extend(rootViewController.sceneConnections)
				
				resetProperties.append( (rootViewController, dict(rootViewController.properties)) )

				rootViewController['UIParentViewController'] = viewController
				# Maybe also set a default UINavigationItem?

		bytes = CompileNibObjects([root])
		with open("%s/%s%s" %(foldername,viewControllerNibName,".nib"), 'wb') as fl:
			fl.write(bytes)

		for viewController, oldProperties in resetProperties:
			viewController.properties = oldProperties



	storyboard_info = {
		"UIViewControllerIdentifiersToNibNames": identifierMap,
		"UIStoryboardVersion" : 1
		}

	if init:
		init = idToNibNameMap.get(init) or init
		storyboard_info['UIStoryboardDesignatedEntryPointIdentifier'] = init

	print "INIT:", init

	import plistlib
	plistlib.writePlist(storyboard_info, foldername + "/Info.plist")


def makexibid():
	import random
	chars = random.sample('0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM', 10)
	chars[3] = '-'
	chars[6] = '-'
	return ''.join(chars)

def makePlaceholderIdentifier():
	return "UpstreamPlaceholder-" + makexibid()

class ArchiveContext:
	def __init__(self):
		self.connections = []
		self.objects = { }		# When parsing a storyboard, this doesn't include the main view or any of its descendant objects.
		self.toplevel = [ ]

		self.extraNibObjects = [ ]
		self.isStoryboard = False

		# These are used only for storyboards.
		self.storyboardViewController = None
		self.isParsingStoryboardView = False
		self.viewObjects = { }
		self.viewConnections = []
		self.sceneConnections = []
		self.segueConnections = []

		self.isPrototypeList = False


		# What I plan on using after the context revision:

		self.upstreamPlaceholders = { }
		self.parentContext = None
		self.viewReferences = [] # List of tuples ( view id, referencing object, referencing key )
		self.viewControllerLayoutGuides = [ ]
		# self.view = None
		# self.viewController = None

	def contextForSegues(self):
		if self.isPrototypeList:
			return self.parentContext
		return self

	def addObject(self, objid, obj, forceSceneObject = None):
		dct = self.viewObjects if self.isParsingStoryboardView else self.objects
		if forceSceneObject is not None:
			dct = self.objects if forceSceneObject else self.viewObjects
		dct[objid] = obj

		# if self.isParsingStoryboardView:
		# 	self.viewObjects[objid] = obj
		# else:
		# 	self.objects[objid] = obj

	# to be used for objects that are known to be in the same context, given a valid document. (For possibly
	# unkown values, use getObject)
	# Also this meant to be an abstraction around the shitty 'objects' vs 'viewObjects' vs $whatever organization scheme.
	def findObject(self, objid):
		obj = self.getObject(objid)
		if obj is None and objid is not None:
			raise Exception("Object with id %s not found in archive context." % (objid))
		return obj

	def getObject(self, objid):
		if not objid:
			return None
		if objid in self.viewObjects:
			return self.viewObjects[objid]
		if objid in self.objects:
			return self.objects[objid]
		return None

	# Kinda ugly. If we ever use a separate ArchiveContext for storyboard scenes and their views, we can use just use getObject.
	# Basically this is like getObject, but only searches in the right one of 'objects' or 'viewObjects'
	def getObjectInCurrentContext(self, objid):
		if objid is None:
			return None
		if self.isParsingStoryboardView:
			return self.viewObjects.get(objid)
		else:
			return self.objects[objid]
		return None

	def resolveConnections(self):
		if not self.isStoryboard:
			self._resolveConnections_xib()
		else:
			self._resolveConnections_storyboard()
		self._resolveViewReferences()

	def _resolveViewReferences(self):
		for ref in self.viewReferences:
			view_id, obj, key = ref
			obj[key] = self.findObject(view_id)


	def _resolveConnections_xib(self):
		result = []
		for con in self.connections:
			dst = con['UIDestination']
			if isinstance(dst, NibProxyObject):
				result.append(con)
				continue

			# How does this happen?
			if isinstance(dst, XibObject):
				result.append(con)
				continue
			# I think this resolution code will be obsolete when we start using UpstreamPlaceholder's.
			assert isinstance(dst, basestring), "%s is not a string ID" % dst
			print 'Resolving standalone xib connection with id', dst
			if dst in self.objects:
				con['UIDestination'] = self.objects[dst]
				result.append(con)
				continue
			phid = makePlaceholderIdentifier()
			con['UIDestination'] = NibProxyObject(phid)
			self.upstreamPlaceholders[phid] = dst
			result.append(con)

		self.connections = result

	def _resolveConnections_storyboard(self):
		view_cons = []
		scene_cons = []

		upstreamPlaceholderTable = { } # src serial -> tuple( phid, src object )
		cachedProxyObjects = { }

		def placeholderIDForObject(obj):
			if obj.serial() in upstreamPlaceholderTable:
				phid = upstreamPlaceholderTable[obj.serial()][0]
			else:
				phid = "UpstreamPlaceholder-" + makexibid()
				upstreamPlaceholderTable[obj.serial()] = (phid, obj)
			return phid

		def proxyObjectForObject(obj):
			phid = placeholderIDForObject(obj)
			if cachedProxyObjects.get(phid):
				return cachedProxyObjects.get(phid)
			prox = NibProxyObject(phid)
			cachedProxyObjects[phid] = prox
			return prox

		for con in self.connections:
			label = con['UILabel']
			src = con['UISource']
			dst = con['UIDestination'] # Get the object ID.
			if not isinstance(dst, NibObject):
				dst = self.objects.get(dst) or self.viewObjects.get(dst)
			assert dst, "Can't find connection destination id %s" % (con['UIDestination'])
			con['UIDestination'] = dst

			src_top = src.xibid in self.objects
			dst_top = dst.xibid in self.objects

			if not src_top:
				assert(src.xibid in self.viewObjects)

			# Something outside the view (typically the view controller) pointing to something in the view.
			if (src_top, dst_top) == (True, False):
				con['UISource'] = proxyObjectForObject(src)
				view_cons.append(con)

			# Something in the view pointing to something not in the view.
			elif (src_top, dst_top) == (False, True):
				con['UIDestination'] = proxyObjectForObject(dst)
				view_cons.append(con)

			elif (src_top, dst_top) == (True, True):
				scene_cons.append(con)

			elif (src_top, dst_top) == (False, False):
				view_cons.append(con)


		externObjects = dict(upstreamPlaceholderTable.values())

		for ph_id, obj_id in self.upstreamPlaceholders.iteritems():
			obj = self.objects[obj_id]
			externObjects[ph_id] = obj

		if len(externObjects):
			self.storyboardViewController['UIExternalObjectsTableForViewLoading'] = externObjects

		scene_cons.extend(self.segueConnections)

		self.viewConnections = view_cons
		self.sceneConnections = scene_cons

		self.storyboardViewController.sceneConnections = scene_cons




def classSwapper(func):
	def inner(ctx, elem, parent, *args, **kwargs):
		object = func(ctx, elem, parent, *args, **kwargs)
		if object:
			customClass = elem.attrib.get("customClass")
			if customClass:
				object['UIOriginalClassName'] = object.classname()
				object['UIClassName'] = customClass
				object.setclassname("UIClassSwapper")

		return object
	return inner

def __xibparser_ParseXIBObject(ctx, elem, parent):
	tag = elem.tag
	fnname = "_xibparser_parse_" + tag
	parsefn = globals().get(fnname)
	# print "----- PARSETHING: " + tag, parsefn
	if parsefn:
		obj = parsefn(ctx, elem, parent)
		if obj and isinstance(obj, XibObject):
			obj.xibid = elem.attrib['id']
		return obj
	return None

def __xibparser_ParseChildren(ctx, elem, obj):
	children = [__xibparser_ParseXIBObject(ctx, child_element, obj) for child_element in elem]
	return [c for c in children if c]

def _xibparser_parse_placeholder(ctx, elem, parent):
	placeholderid = elem.attrib['placeholderIdentifier']
	obj = NibProxyObject(placeholderid)
	__xibparser_ParseChildren(ctx, elem, obj)
	ctx.addObject(elem.attrib['id'], obj)
	return obj


def _xibparser_parse_interfacebuilder_properties(ctx, elem, parent, obj):
	
	rid = elem.attrib.get('restorationIdentifier')
	if rid:
		obj['UIRestorationIdentifier'] = rid

	ibid = elem.attrib.get('id')
	if ibid:
		ctx.addObject(ibid, obj)


class XibObject(NibObject):
	def __init__(self, classname):
		NibObject.__init__(self, classname)
		self.xibid = None

	def originalclassname(self):
		if not self.classname:
			return None
		if self.classname != "UIClassSwapper":
			return self.classname()
		oc = self['UIOriginalClassName']
		return oc


class XibViewController(XibObject):
	def __init__(self, classname):
		XibObject.__init__(self, classname)
		self.xibattributes = { }

		# For storyboards:
		self.relationshipsegue = None
		self.sceneConnections = None 	# Populated in ArchiveContext.resolveConnections()

@classSwapper
def _xibparser_parse_viewController(ctx, elem, parent, **kwargs):
	obj = XibViewController(kwargs.get("uikit_class") or "UIViewController")

	if elem.attrib.get('sceneMemberID') == 'viewController':
		ctx.storyboardViewController = obj

	obj.xibattributes = elem.attrib or { }
	__xibparser_ParseChildren(ctx, elem, obj)
	_xibparser_parse_interfacebuilder_properties(ctx, elem, parent, obj)
	obj['UIStoryboardIdentifier'] = elem.attrib.get('storyboardIdentifier')

	return obj

def _xibparser_parse_navigationController(ctx, elem, parent):
	obj = _xibparser_parse_viewController(ctx, elem, parent, uikit_class = "UINavigationController")
	return obj

def _xibparser_parse_tableViewController(ctx, elem, parent):
	obj = _xibparser_parse_viewController(ctx, elem, parent, uikit_class = "UITableViewController")
	return obj


'''
List of attributes I've seen on 'view' elements

Unhandled

adjustsFontSizeToFit
baselineAdjustment
clipsSubviews
horizontalHuggingPriority
lineBreakMode
opaque
text
userInteractionEnabled
verticalHuggingPriority

contentHorizontalAlignment="center"
contentVerticalAlignment="center"
buttonType="roundedRect" 

	
Started
	key  -  'view' (for view controllers)

Done
	contentMode - TODO: Make sure the string values we check are correct.
	customClass
	restorationIdentifier
	translatesAutoresizingMaskIntoConstraints

WontDo
	fixedFrame - I think this is only for interface builder. (it gets set on UISearchBar)
	id - Not arhived in nib.
'''
@classSwapper
def _xibparser_parse_view(ctx, elem, parent, **kwargs):
	obj = XibObject(kwargs.get("uikit_class") or "UIView")
	obj.setrepr(elem)

	key = elem.get('key')
	if key == 'view':
		parent['UIView'] = obj
	elif key == 'tableFooterView':
		parent['UITableFooterView'] = obj
		parent.append('UISubviews', obj)
	elif key == 'tableHeaderView':
		parent['UITableHeaderView'] = obj
		parent.append('UISubviews', obj)
	elif key == 'contentView':
		if parent.originalclassname() != "UIVisualEffectView":
			print "Unhandled class '%s' to take UIView with key 'contentView'" % (parent.originalclassname())
		else:
			parent['UIVisualEffectViewContentView'] = obj
			obj.setclassname('_UIVisualEffectContentView')

	isMainView = key == 'view' # and isinstance(parent, XibViewController)?

	if elem.attrib.get('translatesAutoresizingMaskIntoConstraints') == 'NO':
		obj['UIViewDoesNotTranslateAutoresizingMaskIntoConstraints'] = True

	if 'contentMode' in elem.attrib.keys():
		mode = elem.attrib['contentMode']
		enum = [ 'scaleToFill', 'scaleAspectFit', 'scaleAspectFill', 'redraw', 'center', 'top', 'bottom', 'left', 'right', 'topLeft', 'topRight', 'bottomLeft', 'bottomRight' ]
		idx = enum.index(mode)
		if idx: # It doesn't encode the default value.
			obj['UIContentMode'] = NibByte(idx)

	obj['UIClipsToBounds'] = elem.attrib.get('clipsSubviews') == 'YES'

	# Default Values?
	obj['UIAutoresizingMask'] = NibByte(36) # Flexible right + bottom margin.
	obj['UIAutoresizeSubviews'] = True


	val = elem.attrib.get('text')
	if val:
		obj['UIText'] = val

	if isMainView:
		ctx.isParsingStoryboardView = True

	ctx.extraNibObjects.append(obj)

	# Parse these props first, in case any of our children point to us.
	_xibparser_parse_interfacebuilder_properties(ctx, elem, parent, obj)
	__xibparser_ParseChildren(ctx, elem, obj)
	

	if isMainView:
		ctx.isParsingStoryboardView = False
	
	return obj

def _xibparser_parse_searchBar(ctx, elem, parent):
	return _xibparser_parse_view(ctx, elem, parent, uikit_class = "UISearchBar")

def _xibparser_parse_imageView(ctx, elem, parent):
	return _xibparser_parse_view(ctx, elem, parent, uikit_class = "UIImageView")

def _xibparser_parse_textView(ctx, elem, parent):
	return _xibparser_parse_view(ctx, elem, parent, uikit_class = "UITextView")

def _xibparser_parse_label(ctx, elem, parent):
	cls = "UILabel"
	if ctx.isPrototypeList:
		cls = "UITableViewLabel"
	label = _xibparser_parse_view(ctx, elem, parent, uikit_class = cls)
	label.setIfEmpty("UIUserInteractionDisabled", True)
	label.setIfEmpty("UIViewContentHuggingPriority", "{251, 251}")
	return label

def _xibparser_parse_button(ctx, elem, parent):
	button = _xibparser_parse_view(ctx, elem, parent, uikit_class = "UIButton")

	btn_type = elem.attrib.get('buttonType')
	if btn_type:
		# Todo: Verify these string constants.
		idx = [ 'custom', 'system', 'detailDisclosure', 'infoLight', 'infoDark', 'contactAdd', 'roundedRect' ].index(btn_type)
		# From iOS 7 onward, roundedRect buttons become system buttons.
		idx = 1 if idx == 6 else idx
		button['UIButtonType'] = NibByte(idx)

	content = elem.attrib.get('')

	button['UIAdjustsImageWhenHighlighted'] = True
	button['UIAdjustsImageWhenDisabled'] = True
	# Todo: Default button font.

	# UIButtonStatefulContent = (10) @23
	# {
		# 0 : @35: UIButtonContent
			# UITitle = @12 Shout!
			# UIShadowColor = @55  ( 0.5 0.5 0.5 1)
	# }
	return button

def _xibparser_parse_navigationBar(ctx, elem, parent):
	bar = _xibparser_parse_view(ctx, elem, parent, uikit_class = "UINavigationBar")
	if elem.attrib.get('key') == 'navigationBar':
		parent['UINavigationBar'] = bar
		bar['UIDelegate'] = parent

	translucent = elem.attrib.get('translucent') != 'NO'
	bar['UIBarTranslucence'] = 1 if translucent else 2

	if elem.attrib.get('barStyle') == 'black':
		bar['UIBarStyle'] = 1

	return bar

def _xibparser_parse_visualEffectView(ctx, elem, parent):
	view = _xibparser_parse_view(ctx, elem, parent, uikit_class = "UIVisualEffectView")
	assert view.get('UIVisualEffectViewEffect')
	# view['UIVisualEffectViewGroupName'] = NibNil()
	return view

def _xibparser_parse_blurEffect(ctx, elem, parent):
	obj = NibObject('UIBlurEffect')
	obj['UIBlurEffectStyle'] = ['extraLight', 'light', 'dark'].index(elem.attrib['style'])

	if parent.originalclassname() == 'UIVisualEffectView':
		parent['UIVisualEffectViewEffect'] = obj
	elif parent.originalclassname() == 'UIVibrancyEffect':
		parent['UIVibrancyEffectBlurStyle'] = obj['UIBlurEffectStyle'] #['extraLight', 'light', 'dark'].index(elem.attrib['style'])

def _xibparser_parse_vibrancyEffect(ctx, elem, parent):
	obj = XibObject("UIVibrancyEffect")
	__xibparser_ParseChildren(ctx, elem, obj)
	parent['UIVisualEffectViewEffect'] = obj


'''
clipsSubviews
contentMode="scaleToFill"
alwaysBounceVertical="YES"
dataMode="prototypes" style="plain" separatorStyle="default" rowHeight="44" sectionHeaderHeight="22" sectionFooterHeight="22



Default UITableView in UITableViewController:

	UIBounds = (8) (0.0, 0.0, 600.0, 600.0)
	UICenter = (8) (300.0, 300.0)
	UIBackgroundColor = (10) @2
	UIOpaque = (5) True
	UIAutoresizeSubviews = (5) True
	UIAutoresizingMask = (0) 36
	UIClipsToBounds = (5) True
	UIBouncesZoom = (5) True
	UIAlwaysBounceVertical = (5) True
	UIContentSize = (8) (600.0, 0.0)
	UISeparatorStyle = (0) 1
	UISeparatorStyleIOS5AndLater = (0) 1
	UISectionHeaderHeight = (6) 22.0
	UISectionFooterHeight = (6) 22.0
	UIShowsSelectionImmediatelyOnTouchBegin = (5) True


'''
def _xibparser_parse_tableView(ctx, elem, parent):
	table = _xibparser_parse_view(ctx, elem, parent, uikit_class = "UITableView")

	sepstylemap = {
		'default' : (1, 1),
		None : (1, 1),
		'singleLine' : (1, 1),
		'none' : None,
		'singleLineEtched' : (1, 2)
	}
	sepstyle = sepstylemap[elem.attrib.get('separatorStyle')]
	if sepstyle:
		table['UISeparatorStyle'] = sepstyle[0]
		table['UISeparatorStyleIOS5AndLater'] = sepstyle[1]

	rowHeight = elem.attrib.get('rowHeight')
	table['UIRowHeight'] = rowHeight and float(rowHeight)

	return table


def _xibparser_parse_state(ctx, elem, parent):
	if parent.originalclassname() != "UIButton":
		print "'state' tag currently only supported for UIButtons. given", parent.originalclassname()
		return None

	content = NibObject("UIButtonContent")
	content['UITitle'] = elem.attrib.get('title')
	# content['UIShadowColor'] = XibColor.fromrgb(0.5, 0.5, 0.5)

	# Todo: Verify these constants.
	statevalue = ['normal', 'highlighted', 'disabled', 'selected' ].index(elem.attrib['key'])
	if statevalue:
		statevalue = 1 << (statevalue - 1)  # Translates 0, 1, 2, 3 to 0, 1 << 0, 1 << 1, 1 << 2

	buttonstates = parent.get('UIButtonStatefulContent')
	if not buttonstates:
		buttonstates = { }
		parent['UIButtonStatefulContent'] = buttonstates
	buttonstates[statevalue] = content

	__xibparser_ParseChildren(ctx, elem, content)


def _xibparser_parse_subviews(ctx, elem, parent):
	# Do we need to pass 'parent' here? Is there anything in XIBs where any of the subviews have a "key" attribute. Table views maybe?
	views = __xibparser_ParseChildren(ctx, elem, parent)
	parent.extend('UISubviews', views)

def _xibparser_parse_prototypes(ctx, elem, parent):

	prototypes = { }
	prototypeExternalObjects = { }

	for tableViewCell in elem:
		rid = tableViewCell.attrib.get('reuseIdentifier')
		if not rid:
			print "Prototype cell %s has no reuseIdentifier. Skipping." % (tableViewCell.attrib['id'])
			continue

		subcontext = ArchiveContext()
		subcontext.isPrototypeList = True
		subcontext.parentContext = ctx
		root = ParseXIBObjects([tableViewCell], subcontext)
		externObjects = { }
		for ph_id, obj_id in subcontext.upstreamPlaceholders.iteritems():
			obj = ctx.getObjectInCurrentContext(obj_id)
			if obj:
				externObjects[ph_id] = obj
				continue

			phid_to_parent = makePlaceholderIdentifier()
			externObjects[ph_id] = NibProxyObject(phid_to_parent)
			ctx.upstreamPlaceholders[phid_to_parent] = obj_id

		if len(externObjects):
			prototypeExternalObjects[rid] = externObjects

		prototypeNibData = CompileNibObjects([root])

		prototypeNib = NibObject("UINib")
		prototypeNib['captureEnclosingNIBBundleOnDecode'] = True
		prototypeNib['archiveData'] = NibData(prototypeNibData)


		prototypes[tableViewCell.attrib['reuseIdentifier']] = prototypeNib

	if len(prototypeExternalObjects):
		parent['UITableViewCellPrototypeNibExternalObjects'] = prototypeExternalObjects

	if not len(prototypes):
		return

	parent['UITableViewCellPrototypeNibs'] = prototypes

def _xibparser_parse_tableViewCell(ctx, elem, parent):
	stylemap = {
	'IBUITableViewCellStyleDefault' : None,
	'IBUITableViewCellStyleValue1' : 1,
	'IBUITableViewCellStyleValue2' : 2,
	'IBUITableViewCellStyleSubtitle' : 3,
	}
	selectmap = {
	'none' : 0,
	'blue' : 1,
	'gray' : 2,
	'default' : None,
	}
	accmap = {
	'disclosureIndicator' : 1,
	'detailDisclosureButton' : 2,
	'checkmark' : 3,
	'detailButton' : 4,
	}

	cell = _xibparser_parse_view(ctx, elem, parent, uikit_class='UITableViewCell')
	cell['UITextLabel'] = ctx.findObject(elem.attrib.get('textLabel'))
	cell['UIDetailTextLabel'] = ctx.findObject(elem.attrib.get('detailTextLabel'))
	cell['UIImageView'] = ctx.findObject(elem.attrib.get('imageView'))
	cell['UIReuseIdentifier'] = elem.attrib.get('reuseIdentifier')

	cell['UITableViewCellStyle'] = stylemap.get(elem.attrib.get('style'))
	cell['UISelectionStyle'] = selectmap.get(elem.attrib.get('selectionStyle'))
	cell.setIfNotDefault('UIIndentationWidth', float(elem.attrib.get('indentationWidth') or 0), 10.0)
	cell.setIfNotDefault('UIIndentationLevel', int(elem.attrib.get('indentationLevel') or 0), 0)
	cell['UIAccessoryType'] = accmap.get(elem.attrib.get('accessoryType'))
	cell['UIEditingAccessoryType'] = accmap.get(elem.attrib.get('editingAccessoryType'))
	cell['UIShowsReorderControl'] = elem.attrib.get('showsReorderControl') == 'YES' or None

	# I can't seem to see what effect shouldIndentWhileEditing="NO" has on the nib.

	return cell

def _xibparser_parse_tableViewCellContentView(ctx, elem, parent):
	view = _xibparser_parse_view(ctx, elem, parent, uikit_class = 'UITableViewCellContentView')
	parent['UIContentView'] = view
	parent['UISubviews'] = [ view ]
	return view


# Types of connections: outlet, action, segue, *outletConnection (any more?)
def _xibparser_parse_connections(ctx, elem, parent):
	__xibparser_ParseChildren(ctx, elem, parent)

def _xibparser_parse_outlet(ctx, elem, parent):
	con = NibObject("UIRuntimeOutletConnection")
	con['UILabel'] = elem.attrib.get('property')
	con['UISource'] = parent
	con['UIDestination'] = elem.attrib.get('destination')
	con.xibid = elem.attrib['id']

	# Add this to the list of connections we'll have to resolve later.
	ctx.connections.append(con)

def _xibparser_parse_action(ctx, elem, parent):

	etype = elem.attrib.get('eventType')

	#  @31: UIRuntimeEventConnection
	# UILabel = (10) @48  "shout:"
	# UISource = (10) @51  UIButton instance
	# UIDestination = (10) @16 UIProxyObject "UpstreamPlaceholder-cnh-Gb-aGf"
	# UIEventMask = (0) 64 UIControlEventTouchUpInside

	maskmap = {
		None : None,

		"touchDown" 			: 1 << 0,
		"touchDownRepeat"		: 1 << 1,
		"touchDragInside"		: 1 << 2,
		"touchDragOutside"		: 1 << 3,
		"touchDragEnter"		: 1 << 4,
		"touchDragExit"			: 1 << 5,
		"touchUpInside"			: 1 << 6,
		"touchUpOutside"		: 1 << 7,
		"touchCancel"			: 1 << 8,

		"valueChanged"			: 1 << 12,

		"editingDidBegin"		: 1 << 16,
		"editingChanged"		: 1 << 17,
		"editingDidEnd"			: 1 << 18,
		"editingDidEndOnExit"	: 1 << 19,
	}

	mask = maskmap[etype]

	con = NibObject("UIRuntimeEventConnection")
	con['UILabel'] = elem.attrib['selector']
	con['UISource'] = parent
	con['UIDestination'] = elem.attrib['destination']
	con['UIEventMask'] = mask

	ctx.connections.append(con)

def _xibparser_parse_segue(ctx, elem, parent):

	template = XibObject("")
	template.xibid = elem.attrib['id']
	template['UIIdentifier'] = elem.attrib.get('identifier')
	template['UIDestinationViewControllerIdentifier'] = elem.attrib['destination']

	kind = elem.attrib['kind']

	if kind in ['presentation','modal']:
		if elem.attrib.get('modalPresentationStyle'):
			enum = { "fullScreen" : 0, "pageSheet" : 1,	"formSheet" : 2, "currentContext" : 3, "overFullScreen" : 5, "overCurrentContext" : 6 }
			segue['UIModalPresentationStyle'] = enum.get(elem.attrib['modalPresentationStyle'])

		if elem.attrib.get('modalTransitionStyle'):
			enum = { "coverVertical" : 0, "flipHorizontal" : 1, "crossDissolve" : 2, "partialCurl" : 3 }
			segue['UIModalTransitionStyle'] = enum.get(elem.attrib['modalTransitionStyle'])

		if elem.attrib.get('animates') == 'NO':
			segue['UIAnimates'] = False

	if kind == 'show':
		template.setclassname('UIStoryboardShowSegueTemplate')
		template['UIActionName'] = "showViewController:sender:"

	elif kind == 'showDetail':
		template.setclassname('UIStoryboardShowSegueTemplate')
		template['UIActionName'] = "showDetailViewController:sender:"

	elif kind == 'presentation':
		template.setclassname('UIStoryboardPresentationSegueTemplate')


	## Deprecated segue types

	elif kind == 'push':
		template.setclassname("UIStoryboardPushSegueTemplate")
		template['UIDestinationContainmentContext'] = 0
		template['UISplitViewControllerIndex'] = 0

	elif kind == 'modal':
		template.setclassname("UIStoryboardModalSegueTemplate")

	elif kind == 'replace':
		template.setclassname("UIStoryboardReplaceSegueTemplate")

		template['UIDestinationContainmentContext'] = 1
		template['UISplitViewControllerIndex'] = elem.attrib.get('splitViewControllerTargetIndex')

	## Custom segue

	elif kind == 'custom':
		template.setclassname("UIStoryboardSegueTemplate")
		template['UISegueClassName'] = elem.attrib.get('customClass')

	elif kind == 'relationship':
		parent.relationshipsegue = elem
		return

	else:
		print 'Unknown segue kind', kind
		return


	# Get the context to install the segue in.
	sctx = ctx.contextForSegues()

	controller = sctx.storyboardViewController
	templateList = controller.get('UIStoryboardSegueTemplates')
	if not templateList:
		templateList = [ ]
		controller['UIStoryboardSegueTemplates'] = templateList
	templateList.append(template)
	sctx.addObject(template.xibid, template, True)

	vcConnection = NibObject('UIRuntimeOutletConnection')
	vcConnection['UILabel'] = 'viewController'
	vcConnection['UISource'] = template
	vcConnection['UIDestination'] = controller

	sctx.segueConnections.append(vcConnection)
	sctx.extraNibObjects.append(template)

	# TODO: What other types of IB objects can trigger segues?
	if parent.originalclassname() == 'UIButton':
		con = NibObject("UIRuntimeEventConnection")

		segue_phid = makePlaceholderIdentifier()

		con['UILabel'] = 'perform:'
		con['UISource'] = parent
		con['UIDestination'] = NibProxyObject(segue_phid)
		con['UIEventMask'] = 64
		ctx.connections.append(con)
		ctx.upstreamPlaceholders[segue_phid] = template.xibid

	elif parent.originalclassname() == 'UITableViewCell':

		label = 'selectionSegueTemplate'
		if elem.attrib.get('trigger') == "accessoryAction":
			label = 'accessoryActionSegueTemplate'

		segue_phid = makePlaceholderIdentifier()

		con = NibObject("UIRuntimeOutletConnection")
		con['UILabel'] = label
		con['UISource'] = parent
		con['UIDestination'] = NibProxyObject(segue_phid)
		ctx.connections.append(con)
		ctx.upstreamPlaceholders[segue_phid] = template.xibid

def _xibparser_parse_layoutGuides(ctx, elem, parent):
	__xibparser_ParseChildren(ctx, elem, parent)

def _xibparser_parse_viewControllerLayoutGuide(ctx, elem, parent):
	obj = XibObject("_UILayoutGuide")
	obj.xibid = elem.attrib['id']
	obj['UIOpaque'] = True
	obj['UIHidden'] = True
	obj['UIAutoresizeSubviews'] = True
	obj['UIViewDoesNotTranslateAutoresizingMaskIntoConstraints'] = True
	#UIViewAutolayoutConstraints = (10) @21
	#_UILayoutGuideConstraintsToRemove = (10) @30

	if elem.attrib.get('type') == 'bottom':
		obj['_UILayoutGuideIdentifier'] = "_UIViewControllerBottom"
	elif elem.attrib.get('type') == 'top':
		obj['_UILayoutGuideIdentifier'] = "_UIViewControllerTop"

	ctx.addObject(obj.xibid, obj)

	ctx.viewControllerLayoutGuides.append(obj)


def _xibparser_parse_constraints(ctx, elem, parent):
	__xibparser_ParseChildren(ctx, elem, parent)

def _xibparser_parse_constraint(ctx, elem, parent):
	constraint = _xibparser_get_constraint(ctx, elem, parent)
	if constraint:
		parent.append('UIViewAutolayoutConstraints', constraint)
		ctx.addObject(constraint.xibid, constraint)

		item = constraint['NSFirstItem']
		if isinstance(item, basestring):
			ctx.viewReferences.append( (item, constraint, 'NSFirstItem') )

		item = constraint.get('NSSecondItem')
		if item and isinstance(item, basestring):
			ctx.viewReferences.append( (item, constraint, 'NSSecondItem') )

def _xibparser_get_constraint(ctx, elem, parent):
	attributes = {
		None : 0,
		'left' : 1,
		'right' : 2,
		'top' : 3,
		'bottom' : 4,
		'leading' : 5,
		'trailing' : 6,
		'width' : 7,
		'height' : 8,

		# todo: verify these constants.
		'centerX' : 9,
		'centerY' : 10,
		'baseline' : 11,
	}

	attribute1 = attributes.get(elem.attrib.get('firstAttribute'))
	attribute2 = attributes.get(elem.attrib.get('secondAttribute'))
	constant = float(elem.attrib.get('constant') or 0)
	firstItem = elem.attrib.get('firstItem') or parent
	secondItem = elem.attrib.get('secondItem')
	priority = elem.attrib.get('priority')
	priority = priority and int(priority)

	con = XibObject('NSLayoutConstraint')
	con.xibid = elem.attrib['id']
	con['NSFirstItem'] = firstItem
	con['NSFirstAttribute'] = attribute1
	con['NSFirstAttributeV2'] = attribute1
	con['NSSecondAttribute'] = attribute2
	con['NSSecondAttributeV2'] = attribute2
	con['NSConstant'] = constant
	con['NSConstantV2'] = constant
	con['NSShouldBeArchived'] = True
	con['NSPriority'] = priority
	con['NSSecondItem'] = secondItem
	return con

def _xibparser_parse_items(ctx, elem, parent):
	if parent.originalclassname() != 'UINavigationBar':
		print "'items' tag only supported for UINavigationBar."
		return
	items = __xibparser_ParseChildren(ctx, elem, None)
	parent['UIItems'] = items

def _xibparser_parse_navigationItem(ctx, elem, parent):
	
	item = XibObject("UINavigationItem")
	item['UITitle'] = elem.attrib.get('title')

	if elem.attrib.get('key') == "navigationItem":
		parent['UINavigationItem'] = item
	__xibparser_ParseChildren(ctx, elem, item)
	return item

def _xibparser_parse_barButtonItem(ctx, elem, parent):
	item = XibObject("UIBarButtonItem")
	item.xibid = elem.attrib['id']
	ctx.addObject(item.xibid, item)

	item['UIStyle'] = 1 # Plain?
	item['UIEnabled'] = True
	item['UITitle'] = elem.attrib.get('title')

	sysItem = elem.attrib.get('systemItem')
	if sysItem:
		# TODO: Verify these constants.
		allSysItems = [ 'done', 'cancel', 'edit', 'save', 'add', 'flexibleSpace', 'fixedSpace', 'compose', 'reply',
			'action', 'organize', 'bookmarks', 'search', 'refresh', 'stop', 'camera', 'trash', 'play', 'pause',
			'rewind', 'fastForward', 'undo', 'redo', 'pageCurl' ]

		item['UIIsSystemItem'] = True
		item['UISystemItem'] = allSysItems.index(sysItem)

	keymap = {
	'backBarButtonItem' : 'UIBackBarButtonItem',
	'rightBarButtonItem' : 'UIRightBarButtonItem',
	}

	key = elem.attrib.get('key')
	if key in keymap:
		parent[key] = item

	if key == 'rightBarButtonItem':
		parent.append('UIRightBarButtonItems', item)

	# Parse children here.
	__xibparser_ParseChildren(ctx, elem, item)


# TODO: Finish getting the rest of the system colors.
def _xibparser_get_color(elem):
	obj = NibObject("UIColor")

	presets = {
		'darkTextColor' : (0.0,0.0,0.0,1.0)
	}

	r = None
	a = None
	scolor = elem.attrib.get('cocoaTouchSystemColor')
	if scolor:
		preset = presets.get(scolor)
		if preset:
			r,g,b,a = preset
		if r is None:
			if scolor == "groupTableViewBackgroundColor":
				obj['UISystemColorName'] = 'groupTableViewBackgroundColor'
				obj['UIPatternSelector'] = 'groupTableViewBackgroundColor'
				return obj

	if 'white' in elem.attrib.keys():
		r = g = b = float(elem.attrib['white'])

	if r is None:
		r = float(elem.attrib.get("red") or 0.0)
		g = float(elem.attrib.get("green") or 0.0)
		b = float(elem.attrib.get("blue") or 0.0)

	if a is None:
		a = float(elem.attrib.get("alpha") or 1.0)

	obj['UIColorComponentCount'] = NibByte(4)
	# obj['UIRed'] = NibFloatToWord(r)
	# obj['UIGreen'] = NibFloatToWord(g)
	# obj['UIBlue'] = NibFloatToWord(b)
	# obj['UIAlpha'] = NibFloatToWord(a)
	obj['UIRed'] = r
	obj['UIGreen'] = g
	obj['UIBlue'] = b
	obj['UIAlpha'] = a
	obj['UIColorSpace'] = NibByte(2) #todo: figure out what color spaces there are.
	obj['NSRGB'] = NibInlineString("%.3f %.3f %.3f" % (r, g, b))
	return obj

''' Maybe NSColorSpace 4 is calibratedWhiteColorSpace ?
 25: UIColor
	UISystemColorName = (10) @34
	UIColorComponentCount = (0) 2
	UIWhite = (6) 0.0
	UIAlpha = (6) 1.0
	NSWhite = (8) 0
	NSColorSpace = (0) 4
	'''
def _xibparser_parse_color(ctx, elem, parent):

	color = _xibparser_get_color(elem)

	# TODO: We could move this key handling somewhere else.
	key = elem.attrib.get('key')
	if key:
		XibToNib = {
			"backgroundColor" : "UIBackgroundColor",
			"textColor" : "UITextColor",
			"titleShadowColor" : "UIShadowColor",
			"titleColor" : "UITitleColor",
			"barTintColor" : "UIBarTintColor",
			"separatorColor" : "UISeparatorColor"
		}

		key = XibToNib.get(key)
		if key:
			parent[key] = color

	return object

# TODO: I think this function might need more logic when the bounds aren't set at 0, 0
def _xibparser_parse_rect(ctx, elem, parent):
	x = float(elem.attrib.get('x'))
	y = float(elem.attrib.get('y'))
	w = float(elem.attrib.get('width'))
	h = float(elem.attrib.get('height'))

	key = elem.attrib.get('key')
	if key == 'frame':

		cx = float(x + w / 2)
		cy = float(y + h / 2)
		bx = float(0)
		by = float(0)
		bw = float(w)
		bh = float(h)
		center = ( cx, cy )
		bounds = ( bx, by, bw, bh )
		parent['UICenter'] = center
		parent['UIBounds'] = bounds

def _xibparser_parse_inset(ctx, elem, parent):
	key = elem.attrib.get('key')
	if key != 'separatorInset':
		print "'inset' tag only supported for key 'separatorInset'."
		return
	minX = float(elem.attrib['minX'])
	maxX = float(elem.attrib['maxX'])
	minY = float(elem.attrib['minY'])
	maxY = float(elem.attrib['maxY'])

	inset = (minY, minX, maxY, maxX)

	# TODO: Uncomment this after we start honoring separator style for UITableView.
	if key == 'separatorInset':
		parent['UISeparatorInset'] = inset

def _xibparser_parse_autoresizingMask(ctx, elem, parent):

	if elem.attrib.get('key') != "autoresizingMask":
		return

	flex_left = elem.attrib.get('flexibleMinX') == 'YES'
	flex_width = elem.attrib.get('widthSizable') == 'YES'
	flex_right = elem.attrib.get('flexibleMaxX') == 'YES'
	flex_top = elem.attrib.get('flexibleMinY') == 'YES'
	flex_height = elem.attrib.get('heightSizable') == 'YES'
	flex_bottom = elem.attrib.get('flexibleMaxY') == 'YES'

	mask = 0
	for idx, value in enumerate([flex_left, flex_width, flex_right, flex_top, flex_height, flex_bottom]):
		if value:
			mask = mask | (1 << idx)

	parent['UIAutoresizingMask'] = NibByte(mask)

def _xibparser_parse_textInputTraits(ctx, elem, parent):
	if elem.attrib.get('key') != 'textInputTraits':
		return

	values =  { 
		'UIReturnKeyType' : NibByte(6),
		'UIEnablesReturnKeyAutomatically' : True,
		'UISecureTextEntry' : False,
		}

	# TODO: Read the traits object for overriddden values.
	for k,v, in values.iteritems():
		parent[k] = v

def _xibparser_parse_point(ctx, elem, parent):
	point = ( float(elem.attrib['x']), float(elem.attrib['y']) )

#TODO: 
def _xibparser_parse_fontDescription(ctx, elem, parent):
	if elem.attrib.get('key') != 'fontDescription':
		return

	size = float(elem.attrib.get('pointSize') or 0.0)
	fpsize = size
	fonttype = elem.attrib.get('type')
	fontstyle = elem.attrib.get('style')

	font = NibObject("UIFont")
	font['UIFontTraits'] = NibByte(0)
	name = None


	if fontstyle:
		if fontstyle == 'UICTFontTextStyleBody':
			name = ".HelveticaNeueInterface-Regular"
			font['UIIBTextStyle'] = 'UICTFontTextStyleBody'
			size = 16.0
			font['UISystemFont'] = True
		elif fontstyle == 'UICTFontTextStyleCaption1':
			name = ".HelveticaNeueInterface-Regular"
			font['UIIBTextStyle'] = 'UICTFontTextStyleCaption1'
			size = 11.0
			font['UISystemFont'] = True
		elif fontstyle == 'UICTFontTextStyleCaption2':
			name = ".HelveticaNeueInterface-Regular"
			font['UIIBTextStyle'] = 'UICTFontTextStyleCaption2'
			size = 11.0
			font['UISystemFont'] = True
		elif fontstyle == 'UICTFontTextStyleFootnote':
			name = ".HelveticaNeueInterface-Regular"
			font['UIIBTextStyle'] = 'UICTFontTextStyleCaption2'
			size = 12.0
			font['UISystemFont'] = True
		elif fontstyle == 'UICTFontTextStyleHeadline':
			name = ".HelveticaNeueInterface-MediumP4"
			font['UIIBTextStyle'] = 'UICTFontTextStyleHeadline'
			size = 16.0
			font['UISystemFont'] = True
			font['UIFontTraits'] = NibByte(2)
		elif fontstyle == 'UICTFontTextStyleSubhead':
			name = ".HelveticaNeueInterface-Regular"
			font['UIIBTextStyle'] = 'UICTFontTextStyleSubhead'
			size = 14.0
			font['UISystemFont'] = True

	elif fonttype == 'custom' or fonttype == None:
		# family = elem.attrib.get('family')
		name = elem.attrib['name']
		font['UISystemFont'] = False
		descriptor = NibObject('UIFontDescriptor')
		descriptor['UIFontDescriptorAttributes'] = {
			'NSFontSizeAttribute' : NibNSNumber(elem.attrib.get('pointSize')),
			'NSFontNameAttribute' : name
		}
		font['UIFontDescriptor'] = descriptor
	elif fonttype:

		descriptor = NibObject("UIFontDescriptor")
		attrs = { 'NSFontSizeAttribute' : size }

		if fonttype == 'system':
			name = '.HelveticaNeueInterface-Regular'
			font['UISystemFont'] = True
			attrs['NSCTFontUIUsageAttribute'] = 'CTFontRegularUsage'

		elif fonttype == 'boldSystem':
			name = '.HelveticaNeueInterface-MediumP4'
			font['UISystemFont'] = True
			font['UIFontTraits'] = NibByte(2)
			attrs['NSCTFontUIUsageAttribute'] = 'CTFontEmphasizedUsage'

		elif fonttype == 'italicSystem':
			name = '.HelveticaNeueInterface-Italic'
			font['UISystemFont'] = True
			font['UIFontTraits'] = NibByte(1)
			attrs['NSCTFontUIUsageAttribute'] = 'CTFontObliqueUsage'

		descriptor['UIFontDescriptorAttributes'] = attrs

	if not name:
		print "Couldn't find font name."
		return
	
	font['UIFontName'] = name
	font['NSName'] = name
	font['UIFontPointSize'] = fpsize
	font['NSSize'] = size


	parent['UIFont'] = font

	