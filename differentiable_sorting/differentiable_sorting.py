from .bitonic_loops import bitonic_layer_loop, bitonic_swap_loop
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
    Also called \alpha-quasimax: 
            J. Cook.  Basic properties of the soft maximum.  
            Working Paper Series 70, UT MD Anderson CancerCenter Department of Biostatistics, 
            2011. http://biostats.bepress.com/mdandersonbiostat/paper7
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

    matrices = []
    for n, m, layer in bitonic_layer_loop(n):
        l, r = np.zeros((n // 2, n)), np.zeros((n // 2, n))
        map_l, map_r = np.zeros((n, n // 2)), np.zeros((n, n // 2))
        for a, b, out, swap in bitonic_swap_loop(n, m, layer):
            l[out, a] = 1
            r[out, b] = 1
            if swap:
                a,b = b,a
            map_l[a, out] = 1
            map_r[b, out] = 1
        matrices.append((l, r, map_l, map_r))
    return matrices


def bitonic_indices(n):
    """Compute a set of bitonic sort indices to sort a sequence of
    length n. n *must* be a power of 2. As opposed to the matrix
    operations, this requires only two index vectors of length n
    for each layer of the network.
                
    """
    # number of outer layers
    layers = int(np.log2(n))
    indices = []
    for n, m, layer in bitonic_layer_loop(n):
        weave = np.zeros(n, dtype="i4")
        unweave = np.zeros(n, dtype="i4")        
        for a, b, out, swap in bitonic_swap_loop(n, m, layer):
            weave[out] = a
            weave[out + n // 2] = b
            if swap:
                a, b = b, a
            unweave[a] = out
            unweave[b] = out + n // 2                    
        indices.append((weave, unweave))
    return indices



def bitonic_woven_matrices(n):
    """
    Combine the l,r and l_inv, r_inv matrices into single n x n multiplies, for
    use with bisort_weave/diff_bisort_weave, fusing together consecutive stages.
    This reduces the number of multiplies to (k)(k+1) + 1 multiplies, where k=np.log2(n)    
    """
    layers = int(np.log2(n))
    matrices = []
    last_unweave = np.eye(n)
    for n, m, layer in bitonic_layer_loop(n):    
        weave, unweave = np.zeros((n, n)), np.zeros((n, n))
        for a, b, out, swap in bitonic_swap_loop(n, m, layer):                        
                    weave[out, a] = 1
                    weave[out + n // 2, b] = 1
                    # flip comparison order as needed
                    if swap:
                        a, b = b, a
                    unweave[a, out] = 1
                    unweave[b, out + n // 2] = 1                    
        # fuse the unweave and weave steps
        matrices.append(weave @ last_unweave)
        last_unweave = unweave
    # make sure the last unweave is preserved
    matrices.append(last_unweave)
    return matrices



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

    



def diff_sort_indexed(indices, x, softmax=softmax):
    """
    Given a set of bitonic sort indices generated by bitonic_indices(n), sort 
    a sequence x of length n.
    """
    split = len(x) // 2
    for weave, unweave in indices:
        woven = x[weave]
        a, b = woven[:split], woven[split:]
        mx = softmax(a, b)
        mn = a + b - mx
        x = np.concatenate([mn, mx])[unweave]
    return x


def diff_sort_weave(fused, x, softmax=softmax):
    """
    Given a set of bitonic sort matrices generated by bitonic_woven_matrices(n), sort 
    a sequence x of length n.
    """
    split = len(x) // 2
    x = fused[0] @ x
    for mat in fused[1:]:
        a, b = x[:split], x[split:]
        mx = softmax(a, b)
        mn = a + b - mx
        x = mat @ np.concatenate([mn, mx])
    return x


### differentiable ranking
def order_matrix(original, sortd, sigma=0.1):
    """Apply a simple RBF kernel to the difference between original and sortd,
    with the kernel width set by sigma. Normalise each row to sum to 1.0."""
    diff = ((original).reshape(-1, 1) - sortd.reshape(1, -1)) ** 2
    rbf = np.exp(-(diff) / (2 * sigma ** 2))
    return (rbf.T / np.sum(rbf, axis=1)).T


def dargsort(original, sortd, sigma, transpose=False):
    """Take an input vector `original` and a sorted vector `sortd`
    along with an RBF kernel width `sigma`, return an approximate ranking.
    If transpose is True, returns approximate argsort (but note that ties have identical values)
    If transpose is False (default), returns ranking"""
    order = order_matrix(original, sortd, sigma=sigma)
    if transpose:
        order = order.T
    return order @ np.arange(len(original))


def diff_argsort(matrices, x, sigma=0.1, softmax=softmax, transpose=False):

    """Return the smoothed, differentiable ranking of each element of x. Sigma
    specifies the smoothing of the ranking. Note that this function is deceptively named,
    and in the default setting returns the *ranking*, not the argsort.
    
    If transpose is True, returns argsort (but note that ties are not broken in differentiable
    argsort);
    If False, returns ranking (likewise, ties are not broken).
    """
    sortd = diff_sort(matrices, x, softmax)
    return dargsort(x, sortd, sigma, transpose)


def diff_argsort_indexed(indices, x, sigma=0.1, softmax=softmax, transpose=False):
    """Return the smoothed, differentiable ranking of each element of x. Sigma
    specifies the smoothing of the ranking. Uses the indexed form
    to avoid multiplies.
    
    If transpose is True, returns argsort (but note that ties are not broken in differentiable
    argsort);
    If False, returns ranking (likewise, ties are not broken).
    """
    sortd = diff_sort_indexed(indices, x, softmax)
    return dargsort(x, sortd, sigma, transpose)
