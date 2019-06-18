try:
    # try to use autoray to provide transparent JAX/autograd support
    from autoray import numpy as np
except ModuleNotFoundError:
    print("No autoray, using numpy (note: grad won't work!)")
    import numpy as np


### Softmax (log-sum-exp)
def softmax(a, b, alpha=1, normalize=0):
    """The softmaximum of softmax(a,b) = log(e^a + a^b).
    normalize should be zero if a or b could be negative and can be 1.0 (more accurate)
    if a and b are strictly positive.
    """
    return np.log(np.exp(a * alpha) + np.exp(b * alpha) - normalize) / alpha


### Smooth max
def smoothmax(a, b, alpha=1):
    return (a * np.exp(a * alpha) + b * np.exp(b * alpha)) / (
        np.exp(a * alpha) + np.exp(b * alpha)
    )


### relaxed softmax
def softmax_smooth(a, b, smooth=0):
    """The smoothed softmaximum of softmax(a,b) = log(e^a + a^b).
    With smooth=0.0, is softmax; with smooth=1.0, averages a and b"""
    t = smooth / 2.0
    return np.log(np.exp((1 - t) * a + b * t) + np.exp((1 - t) * b + t * a)) - np.log(
        1 + smooth
    )


def bitonic_matrices(n):
    """Compute a set of bitonic sort matrices to sort a sequence of
    length n. n *must* be a power of 2.
    
    See: https://en.wikipedia.org/wiki/Bitonic_sorter
    
    Set k=log2(n).
    There will be k "layers", i=1, 2, ... k
    
    Each ith layer will have i sub-steps, so there are (k*(k+1)) / 2 sorting steps total.
    
    For each step, we compute 4 matrices. l and r are binary matrices of size (k/2, k) and
    map_l and map_r are matrices of size (k, k/2).
    
    l and r "interleave" the inputs into two k/2 size vectors. map_l and map_r "uninterleave" these two k/2 vectors
    back into two k sized vectors that can be summed to get the correct output.
                    
    The result is such that to apply any layer's sorting, we can perform:
    
    l, r, map_l, map_r = layer[j]
    a, b =  l @ y, r @ y                
    permuted = map_l @ np.minimum(a, b) + map_r @ np.maximum(a,b)
        
    Applying this operation for each layer in sequence sorts the input vector.
            
    """
    # number of outer layers
    layers = int(np.log2(n))
    matrices = []
    for layer in range(1, layers + 1):
        # we have 1..layer sub layers
        for sub in reversed(range(1, layer + 1)):
            l, r = np.zeros((n // 2, n)), np.zeros((n // 2, n))
            map_l, map_r = np.zeros((n, n // 2)), np.zeros((n, n // 2))
            out = 0
            for i in range(0, n, 2 ** sub):
                for j in range(2 ** (sub - 1)):
                    ix = i + j
                    a, b = ix, ix + (2 ** (sub - 1))
                    l[out, a] = 1
                    r[out, b] = 1
                    if (ix >> layer) & 1:
                        a, b = b, a
                    map_l[a, out] = 1
                    map_r[b, out] = 1
                    out += 1
            matrices.append((l, r, map_l, map_r))
    return matrices


def bisort(matrices, x):
    """
    Given a set of bitonic sort matrices generated by bitonic_matrices(n), sort 
    a sequence x of length n.
    """
    for l, r, map_l, map_r in matrices:
        a, b = l @ x, r @ x
        x = map_l @ np.minimum(a, b) + map_r @ np.maximum(a, b)
    return x


def diff_sort(matrices, x, softmax=softmax):
    """
    Approximate differentiable sort. Takes a set of bitonic sort matrices generated by bitonic_matrices(n), sort 
    a sequence x of length n. Values may be distorted slightly but will be ordered.
    """
    for l, r, map_l, map_r in matrices:
        a, b = l @ x, r @ x
        mx = softmax(a, b)
        mn = a + b - mx
        x = map_l @ mn + map_r @ mx

    return x


def bitonic_woven_matrices(n):
    """Combine the l,r and l_inv, r_inv matrices into single nxn multiplies, for
    use with bisort_weave/diff_bisort_weave"""
    woven = []
    for l, r, l_inv, r_inv in bitonic_matrices(n):
        weave = np.vstack([l, r])
        unweave = np.hstack([l_inv, r_inv])
        woven.append((weave, unweave))
    return woven


def diff_sort_weave(matrices, x, softmax=softmax):
    """
    Given a set of bitonic sort matrices generated by bitonic_woven_matrices(n), sort 
    a sequence x of length n.
    """
    split = len(x) // 2
    for weave, unweave in matrices:
        woven = weave @ x
        a, b = woven[:split], woven[split:]
        mx = softmax(a, b)
        mn = a + b - mx
        x = unweave @ np.concatenate([mn, mx])
    return x


### differentiable ranking
def order_matrix(original, sortd, sigma=0.1):
    """Apply a simple RBF kernel to the difference between original and sortd,
    with the kernel width set by sigma. Normalise each row to sum to 1.0."""
    diff = (np.array(original).reshape(-1, 1) - sortd) ** 2
    rbf = np.exp(-(diff) / (2 * sigma ** 2))
    return (rbf.T / np.sum(rbf, axis=1)).T


def diff_argsort(matrices, x, sigma=0.1, softmax=softmax):
    """Return the smoothed, differentiable ranking of each element of x. Sigma
    specifies the smoothing of the ranking. """
    sortd = diff_sort(matrices, x, softmax)
    return order_matrix(x, sortd, sigma=sigma) @ np.arange(len(x))

