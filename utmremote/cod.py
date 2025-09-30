import enum
import struct
import types
import typing

from .data import Data, BitVector


def _get_type_hints(obj):
    if hasattr(obj, '__annotations__'):
        return typing.get_type_hints(obj)
    else:
        return {}


class UnkeyedContainerMetadata(enum.IntEnum):
    homogenouslySized = 0
    hetrogenous = enum.auto()
    nullable = enum.auto()


class KeyedContainerMetadata(enum.IntEnum):
    nonnull = 0
    nullable = enum.auto()


class CodDecoder:

    class Decoder:

        def __init__(self, val, data, shapes=None):
            if isinstance(val, type) or isinstance(val, types.GenericAlias):
                self.type = val
                self.val = None
            else:
                self.type = val.__class__
                self.val = val
            if not isinstance(data, Data):
                data = Data(data)
            self.data = data
            if shapes is None:
                shapes = {}
                shapeCount = data.popUleb128()
                for i in range(0, shapeCount):
                    keyCount = data.popUleb128()
                    shape = [data.slice(data.popUleb128()).decode('utf-8')
                             for _ in range(0, keyCount)]
                    if len(set(shape)) != len(shape):
                        raise ValueError("Duplicate keys")
                    shapes[i] = shape
            self.shapes = shapes

        def decode(self):
            if isinstance(self.type, types.GenericAlias):
                if self.type.__origin__ == list:
                    return self._decode_unkeyed_container(
                        *self.type.__args__)
                elif self.type.__origin__ == dict:
                    return self._decode_keyed_container(
                        dict(), *self.type.__args__)
            elif self.type == bool:
                return self.data.popFirst() != 0
            elif issubclass(self.type, int):
                val = 0
                for n in reversed(self.data.slice()):
                    val = (val << 8) | n
                return self.type(val)
            elif issubclass(self.type, str):
                return self.data.slice(self.data.popUleb128()).decode('utf-8')
            elif issubclass(self.type, Codable):
                return self._decode_keyed_container(
                    self.val if self.val is not None else self.type())
            elif issubclass(self.type, enum.Enum):
                val = self._decode_keyed_container(
                    dict(), str, dict[None, None])
                return getattr(self.type, next(iter(val.keys())))
            elif self.type == bytes:
                return self._decode_unkeyed_container(bytes)
            raise ValueError(f"Don't know how to decode {self.type}")

        def _decode_unkeyed_container(self, elttype):
            type = UnkeyedContainerMetadata(self.data.popFirst())
            indexCount = self.data.popUleb128()
            offset = 0
            offsets = []
            if type == UnkeyedContainerMetadata.homogenouslySized:
                size = self.data.popUleb128()
                offset = indexCount*size
                if self.type == bytes:
                    offsets = [slice(0, offset)]
                elif indexCount > 0:
                    offsets = [slice(offset, offset+size) for offset in
                               range(0, offset, size)]
            elif type == UnkeyedContainerMetadata.hetrogenous:
                for index in range(0, indexCount):
                    elen = self.data.popUleb128()
                    offsets.append(slice(offset, offset+elen))
                    offset += elen
            else:
                nulls = BitVector(indexCount, self.data)
                for index in range(0, indexCount):
                    if nulls[index]:
                        offsets.append(None)
                    else:
                        elen = self.data.popUleb128()
                        offsets.append(slice(offset, offset+elen))
                        offset += ellen
            if self.type == bytes:
                values = b''.join([bytes(self.data[pos])
                                   for pos in offsets if pos is not None])
            else:
                values = [
                    self.__class__(elttype, self.data[pos], self.shapes
                                   ).decode() if pos is not None else None
                    for pos in offsets]
            self.data = self.data[offset:]
            return values

        def _decode_keyed_container(self, container, ktype=None, vtype=None):
            type = KeyedContainerMetadata(self.data.popFirst())
            shape = self.shapes[self.data.popUleb128()]
            keys = {}
            offset = 0
            if type == KeyedContainerMetadata.nonnull:
                for key in shape:
                    elen = self.data.popUleb128()
                    keys[key] = slice(offset, offset+elen)
                    offset += elen
            else:
                nulls = BitVector(len(shape), self.data)
                for index, key in enumerate(shape):
                    if nulls[index]:
                        keys[key] = None
                    else:
                        elen = self.data.popUleb128()
                        keys[key] = slice(offset, offset+elen)
                        offset += elen
            if vtype is None:
                for key in _get_type_hints(container).keys():
                    setattr(container, key, None)
            for key, pos in keys.items():
                if pos is None:
                    value = None
                else:
                    value = self.__class__(
                        vtype or _get_type_hints(container)[key],
                        self.data[pos], self.shapes).decode()
                if ktype is None:
                    setattr(container, key, value)
                else:
                    container[ktype(key)] = value
            self.data = self.data[offset:]
            return container

    @classmethod
    def decode(cls, val, data):
        return cls.Decoder(val, data).decode()


class CodEncoder:

    class Shapes:

        def __init__(self):
            self.shapeCounter = 0
            self.shapes = []
            self.shapeIds = dict()

        def lookupID(self, shape):
            key = ','.join(shape)
            if key in self.shapeIds:
                return self.shapeIds[key]
            id = self.shapeCounter
            self.shapeCounter += 1
            self.shapes.append(shape)
            self.shapeIds[key] = id
            return id

    class Encoder:

        def __init__(self, val, shapes):
            self.shapes = shapes
            self.val = val

        def encode(self, data):
            if isinstance(self.val, bool):
                data.pushLast(1 if self.val else 0)
            elif isinstance(self.val, int):
                data.extend(struct.pack('<q', self.val))
            elif isinstance(self.val, str):
                utf8 = self.val.encode('utf-8')
                data.pushUleb128(len(utf8))
                data.extend(utf8)
            elif (isinstance(self.val, Codable) or isinstance(self.val, dict)
                  or isinstance(self.val, enum.Enum)):
                self._encode_keyed_container(data)
            elif isinstance(self.val, list) or isinstance(self.val, bytes):
                self._encode_unkeyed_container(data)
            else:
                raise ValueError(f"Don't know how to encode {type(self.val)}")

        def _encode_unkeyed_container(self, data):
            if isinstance(self.val, bytes):
                data.pushLast(UnkeyedContainerMetadata.homogenouslySized)
                data.pushUleb128(len(self.val))
                data.pushUleb128(1)
                data.extend(self.val)
                return
            values = []
            for value in self.val:
                if value is None:
                    values.append(None)
                else:
                    d = Data()
                    self.__class__(value, self.shapes).encode(d)
                    values.append(d)
            if None in values:
                data.pushLast(UnkeyedContainerMetadata.nullable)
                data.pushUleb128(len(values))
                data.extend(BitVector(len(values), [
                    value is None for key in values]))
                for value in values:
                    data.pushUleb128(len(value))
            else:
                sizes = [len(value) for value in values]
                if len(set(sizes)) <= 1:
                    data.pushLast(UnkeyedContainerMetadata.homogenouslySized)
                    data.pushUleb128(len(values))
                    data.pushUleb128(sizes[0] if len(sizes) > 0 else 0)
                else:
                    data.pushLast(UnkeyedContainerMetadata.hetrogenous)
                    data.pushUleb128(len(values))
                    for size in sizes:
                        data.pushUleb128(size)
            for value in values:
                if value is not None:
                    data.extend(value)

        def _encode_keyed_container(self, data):
            if isinstance(self.val, dict):
                sortedKeys = sorted(self.val.keys())

                def get(key):
                    return self.val[key]
            elif isinstance(self.val, enum.Enum):
                sortedKeys = [self.val.name]

                def get(key):
                    return dict()
            else:
                sortedKeys = [
                    k for k in sorted(_get_type_hints(self.val).keys())
                    if getattr(self.val, k, None) is not None]

                def get(key):
                    return getattr(self.val, key, None)
            id = self.shapes.lookupID(sortedKeys)
            values = []
            for key in sortedKeys:
                value = get(key)
                if value is not None:
                    d = Data()
                    self.__class__(value, self.shapes).encode(d)
                    values.append(d)
            if len(values) == len(sortedKeys):
                data.pushLast(KeyedContainerMetadata.nonnull)
                data.pushUleb128(id)
            else:
                data.pushLast(KeyedContainerMetadata.nullable)
                data.pushUleb128(id)
                data.extend(BitVector(len(sortedKeys), [
                    get(key) is None for key in sortedKeys]))
            for value in values:
                data.pushUleb128(len(value))
            for value in values:
                data.extend(value)

    @classmethod
    def encode(cls, val):
        encoder = cls.Encoder(val, cls.Shapes())
        valueData = Data()
        encoder.encode(valueData)
        data = Data()
        data.pushUleb128(encoder.shapes.shapeCounter)
        for shape in encoder.shapes.shapes:
            data.pushUleb128(len(shape))
            for key in shape:
                utf8 = key.encode('utf-8')
                data.pushUleb128(len(utf8))
                data.extend(utf8)
        data.extend(valueData)
        return data


class Codable:

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and len(kwargs) == 0:
            self.decode(args[0])
        elif len(args) == 0:
            for key, val in kwargs.items():
                setattr(self, key, val)
        else:
            raise ValueError("invalid arguments")

    def encode(self):
        return CodEncoder.encode(self)

    def decode(self, data):
        return CodDecoder.decode(self, data)

    def __repr__(self):
        attributes = [f"{key}={getattr(self, key)!r}"
                      for key in _get_type_hints(self).keys()
                      if hasattr(self, key)]
        v_string = ", ".join(attributes)
        class_name = self.__class__.__qualname__
        return f"{class_name}({v_string})"
