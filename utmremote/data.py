class Data:

    def __init__(self, data=None, offset=0, end=None):
        data = bytearray() if data is None else bytes(data)
        self.data = data
        self.offset = offset
        self.end = len(data) if end is None else end

    def __len__(self):
        return self.end - self.offset if self.end > self.offset else 0

    def __bytes__(self):
        return bytes(self.data[self.offset:self.end])

    def __getitem__(self, offset):
        if isinstance(offset, slice):
            if offset.step is not None:
                raise IndexError("step not supported")
            start, stop = offset.start, offset.stop
            if start < 0 or (stop is not None and stop < 0):
                raise IndexError("negative slices not supported")
            if start is None:
                start = self.offset
            else:
                start += self.offset
            if stop is None or stop + self.offset > self.end:
                stop = self.end
            else:
                stop += self.offset
            return Data(self.data, start, stop)
        elif offset < 0 or offset + self.offset >= self.end:
            raise IndexError("index out of range")
        else:
            return self.data[offset + self.offset]

    def popFirst(self):
        if self.offset >= self.end:
            raise IndexError("pop from Empty list")
        self.offset += 1
        return self.data[self.offset-1]

    def slice(self, end=None):
        if end is None or end + self.offset > self.end:
            end = self.end
        else:
            end += self.offset
        r = bytes(self.data[self.offset:end])
        self.offset += len(r)
        return r

    def popUleb128(self):
        r, scale = 0, 0
        while True:
            bits = self.popFirst()
            r |= (bits & 0x7f) << scale
            scale += 7
            if (bits & 0x80) == 0:
                break
        return r

    def extend(self, x):
        x = bytes(x)
        self.data[self.end:self.end] = x
        self.end += len(x)

    def pushLast(self, x):
        self.extend(bytes([x]))

    def pushUleb128(self, x):
        while x >= 0x80:
            self.pushLast((x & 0x7f) | 0x80)
            x >>= 7
        self.pushLast(x)


class BitVector:

    def __init__(self, count, values=None):
        self.count = count
        count = (count + 7) >> 3
        if values is None or isinstance(values, list):
            self.data = bytearray(count)
            if values is not None:
                for index, value in enumerate(values):
                    self[index] = value
        elif isinstance(values, Data):
            self.data = values.slice(count)
        else:
            self.data = bytes(values)

    def __getitem__(self, index):
        if index < 0 or index >= self.count:
            raise IndexError('BitVector index out of range')
        return ((self.data[index >> 3] >> (index & 7)) & 1) != 0

    def __setitem__(self, index, value):
        if index < 0 or index >= self.count:
            raise IndexError('BitVector index out of range')
        if value:
            self.data[index >> 3] |= 1 << (index & 7)
        else:
            self.data[index >> 3] &= ~(1 << (index & 7))

    def __len__(self):
        return self.count

    def __bytes__(self):
        return bytes(self.data)


class UUID(str):
    pass
