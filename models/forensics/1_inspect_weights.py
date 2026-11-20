import sys, glob, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pth_reader import load
np.set_printoptions(linewidth=250, precision=3, suppress=True)
for p in sorted(glob.glob(sys.argv[1] + '/*.pth')):
    ck = load(p)
    print('=====', os.path.basename(p), list(ck.keys()))
    sd = ck['model_state_dict']
    for k, v in sd.items(): print('  ', k, v.shape, v.dtype)
    print('  meta', dict(getattr(sd, '_metadata', {})) if hasattr(sd, '_metadata') else None)
    print('  class_to_idx', ck['class_to_idx'])
    h = ck['history']
    print('  epochs', {k: len(v) for k, v in h.items()})
    for k, v in h.items(): print('   ', k, 'first', np.round(v[:3], 3), 'last', np.round(v[-3:], 3), 'best', round(max(v), 4) if 'acc' in k else round(min(v), 4))
    w = sd['conv1d.weight']
    bound = 1 / np.sqrt(79 * 3)
    print('  init bound', round(bound, 4), 'conv bias absmax', np.abs(sd['conv1d.bias']).max())
    print('  per-input-channel max|w|:'); print(np.abs(w).max(axis=(0, 2)))
    print('  per-input-channel rms:'); print(np.sqrt((w ** 2).mean(axis=(0, 2))))
    print('  bn1 nbt', sd['bn1.num_batches_tracked'], 'bn2 nbt', sd['bn2.num_batches_tracked'])
    print('  bn1 mean', sd['bn1.running_mean'][:8], 'var', sd['bn1.running_var'][:8])
