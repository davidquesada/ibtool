import nibencoding
import struct

''' Base classes for Nib encoding '''

class NibObject:

	_total = 1000

	def __init__(self, classnme = "NSObject"):
		self._classname = classnme
		self._serial = NibObject._total
		NibObject._total += 1
		self.properties = { }
		self._nibidx = -1
		self._repr = None
		pass

	def setclassname(self, newname):
		self._classname = newname

	def classname(self):
		return self._classname

	def repr(self):
		return self._repr

	def setrepr(self, r):
		self._repr = r

	def nibidx(self):
		return self._nibidx

	def serial(self):
		return self._serial

	def get(self, key):
		return self.properties.get(key)

	def setIfEmpty(self, key, value):
		if key not in self.properties:
			self[key] = value
	def setIfNotDefault(self, key, value, default):
		if value != default:
			self[key] = value
	def append(self, key, value):
		if key in self.properties:
			assert(isinstance(self[key], list))
			self[key].append(value)
		else:
			self[key] = [ value ]
	def extend(self, key, values):
		if key in self.properties:
			assert(isinstance(self[key], list))
			self[key].extend(values)
		else:
			self[key] = list(values)

	def appendkv(self, dictKeyName, key, value):
		if not dictKeyName:
			return
		d = self.get(dictKeyName)
		if d is not None and not isinstance(d, dict):
			raise Exception("extendkv called non-dictionary NibObject property key")
		if d is None:
			d = { }
			self[dictKeyName] = d
		d[key] = value


	def __getitem__(self, key):
		return self.properties[key]

	def __setitem__(self, key, item):
		if item is None:
			return
		self.properties[key] = item

	def __delitem__(self, item):
		del self.properties[item]

	# Returns a list of tuples
	def getKeyValuePairs(self):
	 	return self.properties.items()

class NibString(NibObject):
	def __init__(self, text = "Hello World"):
		NibObject.__init__(self, "NSString")
		self._text = text
	def getKeyValuePairs(self):
		return [("NS.bytes", self._text)]
	def __repr__(self):
		return "%s %s" % (object.__repr__(self), self._text)

class NibData(NibObject):
	def __init__(self, data):
		NibObject.__init__(self, "NSData")
		self._data = data
	def getKeyValuePairs(self):
		# print "MARCO YOLO", type(self._data)
		# raise Exception("EVERYTHING IS OK")
		return [("NS.bytes", self._data)]

class NibInlineString:
	def __init__(self, text = ""):
		self._text = text

	def text(self):
		return self._text

class NibByte:
	def __init__(self, val = 0):
		self._val = val
	def val(self):
		return self._val

class NibNil:
	def __init__(self):
		pass

def NibFloatToWord(num):
	bytes = struct.pack("<f", num)
	return struct.unpack("<I", bytes)[0]

class NibList(NibObject):
	def __init__(self, items = []):
		NibObject.__init__(self, "NSArray")
		self._items = items
	def getKeyValuePairs(self):
		return [("NSInlinedValue", True)] + [("UINibEncoderEmptyKey", item) for item in self._items]

class NibNSNumber(NibObject):
	def __init__(self, value = 0):
		NibObject.__init__(self, "NSNumber")
		self._value = value

		if isinstance(value, basestring):
			try:
				self._value = int(value)
			except ValueError:
				self._value = float(value)
		elif value:
			self._value = value
		else:
			self._value = 0

	def value(self):
		return self._value

	def getKeyValuePairs(self):
		val = self._value
		if isinstance(val, float):
			return [('NS.dblval', val)]
		if val >= 0 and val < 256:
			return [('NS.intval', NibByte(val))]
		return ('NS.intval', val)

#TODO: Have more stuff use this.
#TODO: Make this recursive.
# Is this only for dictionaries?
def convertToNibObject(obj):
	if isinstance(obj, NibObject):
		return obj # Yep, here is where we would put recursion. IF WE HAD ANY.
	elif isinstance(obj, basestring):
		return NibString(obj)
	elif isinstance(obj, int) or isinstance(obj, float):
		return NibNSNumber(obj)
	elif isinstance(obj, NibByte):
		return NibNSNumber(obj.val())
	return obj

class NibDictionaryImpl(NibObject):
	def __init__(self, objects):
		NibObject.__init__(self, "NSDictionary")
		if isinstance(objects, dict):
			t = []
			for k,v in objects.iteritems():
				k = convertToNibObject(k)
				v = convertToNibObject(v)
				t.extend([k,v])
			objects = t
		self._objects = objects

	def getKeyValuePairs(self):
		pairs = [ ( 'NSInlinedValue', True ) ]
		pairs.extend([ ('UINibEncoderEmptyKey', obj ) for obj in self._objects ])
		return pairs

''' Convenience Classes '''

class NibProxyObject(NibObject):
	def __init__(self, identifier):
		NibObject.__init__(self, "UIProxyObject")
		self['UIProxiedObjectIdentifier'] = identifier

''' Conversion Stuff '''


class CompilationContext():
	def __init__(self):
		self.class_set = set()
		self.serial_set = set() # a set of serial numbers for objects that have been added to the object list.

		self.object_list = []

	def addBinObject(self, obj):
		pass

	def addObjects(self, objects):
		for o in objects:
			self.addObject(o)

	def addObject(self, obj):

		if not isinstance(obj, NibObject):
			print "CompilationContext.addObject: Non-NibObject value:", obj
			raise Exception("Not supported.")

		serial = obj.serial()
		if serial in self.serial_set:
			return
		self.serial_set.add(serial)

		cls = obj.classname()
		if cls not in self.class_set:
			self.class_set.add(cls)

		obj._nibidx = len(self.object_list)
		self.object_list.append(obj)

		# Determine the set of objects to convert/add
		keyset = None
		objectset = None

		if isinstance(obj, NibDictionaryImpl):
			# objects = obj._objects
			# for i in range(0, len(objects))
			# self.addObjects(obj._objects)
			
			keyset = range(0, len(obj._objects))
			objectset = obj._objects

		elif isinstance(obj, NibList):
			# self.addObjects(obj._items)

			keyset = range(0, len(obj._items))
			objectset = obj._items

		else:
			keyset = list(obj.properties.keys())
			objectset = obj.properties

		# Add all the subobjects to the object set.

		for key in keyset:
			value = objectset[key]

			if isinstance(value, NibObject):
				self.addObject(value)
			elif isinstance(value, list):
				for itm in value:
					self.addObject(itm)
				value = NibList(value)
				self.addObject(value)
				objectset[key] = value
			elif isinstance(value, basestring):
				value = NibString(value)
				self.addObject(value)
				objectset[key] = value
			elif isinstance(value, dict):
				value = NibDictionaryImpl(value)
				self.addObject(value)
				objectset[key] = value

		


	def makeTuples(self):

		out_objects = []
		out_keys = []
		out_values = []
		out_classes = []

		def idx_of_class(cls):
			if cls in out_classes:
				return out_classes.index(cls)
			out_classes.append(cls)
			return len(out_classes) - 1
		def idx_of_key(key):
			if key in out_keys:
				return out_keys.index(key)
			out_keys.append(key)
			return len(out_keys) - 1

		for object in self.object_list:

			obj_values_start = len(out_values)
			kvpairs = object.getKeyValuePairs()
			for k,v in kvpairs:
				
				if isinstance(v, NibObject):
					key_idx = idx_of_key(k)
					vtuple = (key_idx, nibencoding.NIB_TYPE_OBJECT, v.nibidx(), v)
					out_values.append(vtuple)
				elif isinstance(v, basestring) or isinstance(v, bytearray):
					key_idx = idx_of_key(k)
					vtuple = (key_idx, nibencoding.NIB_TYPE_STRING, v)
					out_values.append(vtuple)
				elif isinstance(v, NibInlineString):
					key_idx = idx_of_key(k)
					vtuple = (key_idx, nibencoding.NIB_TYPE_STRING, v.text())
					out_values.append(vtuple)
				elif isinstance(v, NibByte):
					out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_BYTE, v.val()))
				elif v is True:
					out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_TRUE))
				elif v is False:
					out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_FALSE))
				elif isinstance(v, float):
					out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_DOUBLE, v))
				elif isinstance(v, int):
					if v < 0:
						raise Exception("Encoding negative integers is not supported yet.")
					elif v < 0x100:
						out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_BYTE, v))
					elif v < 0x10000:
						out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_SHORT, v))
					else:
						raise Exception("Encoding integers larger than short is not supported yet.")
					
				elif isinstance(v, tuple):
					for el in v:
						if not isinstance(el, float):
							raise Exception("Only tuples of floats are supported now. Type = " + str(type(el)))
					data = bytearray()
					data.append(0x07)
					data.extend(struct.pack('<' + 'd' * len(v), *v))
					out_values.append((idx_of_key(k), nibencoding.NIB_TYPE_STRING, data))

			obj_values_end = len(out_values)
			class_idx = idx_of_class(object.classname())
			out_objects.append((class_idx, obj_values_start, obj_values_end - obj_values_start))

		return (out_objects, out_keys, out_values, out_classes)



'''
This really has (at least) two phases.
1. Traverse/examine the object graph to find the objects/keys/values/classes that need to be encoded.
2. Once those lists are built and resolved, convert them into binary format.
'''
def CompileNibObjects(objects):
	
	ctx = CompilationContext()
	ctx.addObjects(objects)
	t = ctx.makeTuples()

	return nibencoding.WriteNib(t)
