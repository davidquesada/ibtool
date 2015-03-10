
import struct

NIB_TYPE_BYTE = 0x00
NIB_TYPE_SHORT = 0x01
NIB_TYPE_FALSE = 0x04
NIB_TYPE_TRUE = 0x05
NIB_TYPE_WORD = 0x06
NIB_TYPE_DOUBLE = 0x07
NIB_TYPE_STRING = 0x08  # Can also be used for tuples. e.g. CGPoint/Size/Rect
NIB_TYPE_OBJECT = 0x0A



# Input: Tuple of the four nib components. (Objects, Keys, Values, Classes)
# Output: A byte array containing the binary representation of the nib archive.
def WriteNib(nib):
	bytes = bytearray()
	bytes.extend("NIBArchive")
	bytes.extend([1,0,0,0])
	bytes.extend([9,0,0,0])

	objs = nib[0]
	keys = nib[1]
	vals = nib[2]
	clss = nib[3]

	objs_section = _nibWriteObjectsSection(objs)
	keys_section = _nibWriteKeysSection(keys)
	vals_section = _nibWriteValuesSection(vals)
	clss_section = _nibWriteClassesSection(clss)

	header_size = 50
	objs_start = header_size
	keys_start = objs_start + len(objs_section)
	vals_start = keys_start + len(keys_section)
	clss_start = vals_start + len(vals_section)

	for num in [ len(objs), objs_start,
				 len(keys), keys_start,
				 len(vals), vals_start,
				 len(clss), clss_start, ]:
		bytes.extend(struct.pack("<I", num))

	bytes.extend(objs_section)
	bytes.extend(keys_section)
	bytes.extend(vals_section)
	bytes.extend(clss_section)

	return bytes

def _nibWriteFlexNumber(btarray, number):
	cur_byte = 0
	while True:
		cur_byte = number & 0x7F
		number = number >> 7
		if not number:
			break
		btarray.append(cur_byte)
	cur_byte |= 0x80
	btarray.append(cur_byte)

def _nibWriteObjectsSection(objects):
	bytes = bytearray()
	for obj in objects:
		_nibWriteFlexNumber(bytes, obj[0])
		_nibWriteFlexNumber(bytes, obj[1])
		_nibWriteFlexNumber(bytes, obj[2])
	return bytes

def _nibWriteKeysSection(keys):
	bytes = bytearray()
	for key in keys:
		_nibWriteFlexNumber(bytes, len(key))
		bytes.extend(key)
	return bytes

def _nibWriteClassesSection(classes):
	bytes = bytearray()
	for cls in classes:
		_nibWriteFlexNumber(bytes, len(cls) + 1)
		bytes.append(0x80)
		bytes.extend(cls)
		bytes.append(0x00)
	return bytes

def _nibWriteValuesSection(values):
	bytes = bytearray()
	for value in values:
		keyidx = value[0]
		encoding_type = value[1]
		_nibWriteFlexNumber(bytes, keyidx)
		bytes.append(encoding_type)

		if encoding_type == NIB_TYPE_FALSE:
			continue
		if encoding_type == NIB_TYPE_TRUE:
			continue
		if encoding_type == NIB_TYPE_OBJECT:
			try:
				bytes.extend(struct.pack("<I", value[2]))
			except struct.error:
				print "Encoding object not in object list:", value[3]
				raise
			continue
		if encoding_type == NIB_TYPE_WORD:
			bytes.extend(struct.pack("<I", value[2]))
			continue
		if encoding_type == NIB_TYPE_BYTE:
			bytes.append(value[2])
			continue
		if encoding_type == NIB_TYPE_SHORT:
			bytes.append(struct.pack("<H", value[2]))
			continue
		if encoding_type == NIB_TYPE_STRING: # TODO struct support (Nibs use this encoding for CGRect)
			v = value[2]
			if isinstance(v, unicode):
				v = v.encode('utf-8')
			_nibWriteFlexNumber(bytes, len(v))
			bytes.extend(v)
			continue
		if encoding_type == NIB_TYPE_DOUBLE:
			bytes.extend(struct.pack("<d", value[2]))
			continue

		raise Exception("Bad encoding type: " + str(encoding_type))

	return bytes