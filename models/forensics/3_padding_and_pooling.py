# Which conv padding? Under "last LSTM output step" pooling the backward half of bn2 only sees the conv
# output at the LAST frame. Predict it from the recovered channel means for padding=1 vs padding=0.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pth_reader import load
d = sys.argv[1]
mu = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mu_est.npy'))
sig = lambda x: 1 / (1 + np.exp(-x))
rng = np.random.default_rng(0)
def bwd_first_step(sd, feat):   # feat (N, 32)
    g = feat @ sd['bilstm.weight_ih_l0_reverse'].T + sd['bilstm.bias_ih_l0_reverse'] + sd['bilstm.bias_hh_l0_reverse']
    i, f, gg, o = g[:, :32], g[:, 32:64], g[:, 64:96], g[:, 96:]
    c = sig(i) * np.tanh(gg)
    return sig(o) * np.tanh(c)
for name, mask in [('multimodal_raw', slice(0, 79)), ('unimodal_glove_raw', slice(63, 79)), ('unimodal_vision_raw', slice(0, 63))]:
    sd = {k: np.asarray(v, dtype=np.float64) for k, v in load(f'{d}/{name}.pth')['model_state_dict'].items()}
    x = np.zeros(79); x[mask] = mu[mask]
    W, b = sd['conv1d.weight'], sd['conv1d.bias']
    target = sd['bn2.running_mean'][32:]
    print(name)
    for pad in (1, 0):
        for t_mode in ('ramp', 'mean'):
            taps = np.repeat(x[:, None], 3, axis=1)          # (79, 3) stationary channels
            if mask.start == 0 and t_mode == 'ramp':
                taps[0] = [3.9, 3.9333, 3.9667] if pad == 0 else [3.9333, 3.9667, 0]
            if pad == 1: taps[:, 2] = 0                         # right zero padding at the last position
            conv = (W * taps[None]).sum(axis=(1, 2)) + b
            z = (conv - sd['bn1.running_mean']) / np.sqrt(sd['bn1.running_var'] + 1e-5) * sd['bn1.weight'] + sd['bn1.bias']
            z = np.maximum(z, 0)
            for p in (0.0, 0.3, 0.5):
                keep = (rng.random((4000, 32)) >= p) / (1 - p) if p > 0 else np.ones((1, 32))
                h = bwd_first_step(sd, z[None] * keep).mean(axis=0)
                r = np.corrcoef(h, target)[0, 1]
                print(f'   pad={pad} t={t_mode:4s} dropout={p}: corr={r: .3f}  rmse={np.sqrt(((h - target) ** 2).mean()):.3f}')
