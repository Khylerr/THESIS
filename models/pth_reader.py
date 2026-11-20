"""Read a PyTorch zip checkpoint WITHOUT torch and without running arbitrary pickle code.
Only OrderedDict, tensor rebuild and Float/Long storages are allowed; anything else raises."""
import pickle, zipfile, collections
import numpy as np

class _Storage:
    def __init__(self, dtype): self.dtype = dtype
_FLOAT, _LONG = _Storage('<f4'), _Storage('<i8')

def load(path):
    z = zipfile.ZipFile(path)
    pkl = [n for n in z.namelist() if n.endswith('/data.pkl')][0]
    root = pkl[:-len('data.pkl')]
    def rebuild(storage, offset, size, stride, requires_grad=False, hooks=None, metadata=None):
        arr = storage[offset:offset + int(np.prod(size, dtype=np.int64))] if len(size) else storage[offset:offset + 1]
        # contiguous check
        exp, s = [], 1
        for d in reversed(size): exp.append(s); s *= d
        assert tuple(reversed(exp)) == tuple(stride), (size, stride)
        return arr.reshape(size).copy()
    class U(pickle.Unpickler):
        def find_class(self, mod, name):
            if (mod, name) == ('collections', 'OrderedDict'): return collections.OrderedDict
            if (mod, name) == ('torch._utils', '_rebuild_tensor_v2'): return rebuild
            if (mod, name) == ('torch', 'FloatStorage'): return _FLOAT
            if (mod, name) == ('torch', 'LongStorage'): return _LONG
            raise pickle.UnpicklingError(f'blocked global {mod}.{name}')
        def persistent_load(self, pid):
            kind, st, key, loc, n = pid
            assert kind == 'storage'
            a = np.frombuffer(z.read(root + 'data/' + key), dtype=st.dtype)
            assert a.size == n, (a.size, n)
            return a
    return U(z.open(pkl)).load()
