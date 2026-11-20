import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pth_reader import load
np.set_printoptions(linewidth=220, precision=3, suppress=True)
d = sys.argv[1]
M = {n: load(f'{d}/{n}.pth')['model_state_dict'] for n in ['multimodal_raw', 'unimodal_glove_raw', 'unimodal_vision_raw', 'multimodal_augmented_60reps']}
names = ['t', 'g_valid'] + [f'g_{a}{i}' for i in range(21) for a in 'xyz'] + ['g_px', 'g_py', 'glove_valid'] + [f'flex{i}' for i in range(1, 6)] + ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z']
assert len(names) == 79
def lin(sd):
    W = sd['conv1d.weight'].astype(np.float64).sum(axis=2)   # (32, 79) : sum over taps
    y = sd['bn1.running_mean'].astype(np.float64) - sd['conv1d.bias'].astype(np.float64)
    return W, y
# 1) glove-only model: 32 equations, 16 unknown channel means (63..78)
W, y = lin(M['unimodal_glove_raw'])
A = W[:, 63:]
mu_g, res, rank, sv = np.linalg.lstsq(A, y, rcond=None)
pred = A @ mu_g
print('GLOVE model: rank', rank, 'rel residual', np.linalg.norm(y - pred) / np.linalg.norm(y), '|y|', np.linalg.norm(y))
for n, v in zip(names[63:], mu_g): print(f'   {n:12s} mean = {v: .3f}')
# control: pretend the live channels were a different block -> residual should be bad
for lo in (0, 20, 40):
    A2 = W[:, lo:lo + 16]; m2 = np.linalg.lstsq(A2, y, rcond=None)[0]
    print('   control block', lo, 'rel residual', np.linalg.norm(y - A2 @ m2) / np.linalg.norm(y))
# 2) vision + multimodal jointly: unknown mu[0..62] minus zeros at 2,3,4 ; multimodal uses mu_g for 63..78
Wv, yv = lin(M['unimodal_vision_raw']); Wm, ym = lin(M['multimodal_raw'])
keep = [c for c in range(63) if c not in (2, 3, 4)]
A = np.vstack([Wv[:, keep], Wm[:, keep]])
b = np.concatenate([yv, ym - Wm[:, 63:] @ mu_g])
mu_v, res, rank, sv = np.linalg.lstsq(A, b, rcond=None)
print('VISION+MULTI joint: eq', A.shape, 'rank', rank, 'rel residual', np.linalg.norm(b - A @ mu_v) / np.linalg.norm(b), 'cond', sv[0] / sv[-1])
for c, v in list(zip(keep, mu_v))[:12]: print(f'   {names[c]:10s} mean = {v: .3f}')
full = np.zeros(79); full[keep] = mu_v; full[63:] = mu_g
print('   landmark means (x,y,z per landmark, wrist-relative / palm size):'); print(full[2:65].reshape(21, 3))
np.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mu_est.npy'), full)
# multimodal alone with all 76 unknowns is underdetermined; instead check prediction of multimodal from vision-only fit
A1 = Wv[:, keep]; m1 = np.linalg.lstsq(A1, yv, rcond=None)[0]   # min-norm solution (underdetermined)
print('   vision-only min-norm: t', m1[0], 'g_valid', m1[1])
# 3) bn2 stats: forward half vs backward half
for n, sd in M.items():
    m, v = sd['bn2.running_mean'], sd['bn2.running_var']
    print(n); print('   fwd |mean| max %.3f mean %.3f  var mean %.4f max %.4f' % (np.abs(m[:32]).max(), np.abs(m[:32]).mean(), v[:32].mean(), v[:32].max()))
    print('   bwd |mean| max %.3f mean %.3f  var mean %.4f max %.4f' % (np.abs(m[32:]).max(), np.abs(m[32:]).mean(), v[32:].mean(), v[32:].max()))
    print('   fwd mean', m[:32]); print('   bwd mean', m[32:]); print('   fwd var', v[:32]); print('   bwd var', v[32:])
