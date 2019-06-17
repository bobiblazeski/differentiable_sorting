import numpy as np

def softmax(a,b):
    """The softmaximum of softmax(a,b) = log(e^a + a^b)."""
    return np.log(np.exp(a)+np.exp(b))

def softmin(a,b):
    """
    Return the soft-minimum of a and b
    The soft-minimum can be derived directly from softmax(a,b).
    """
    return -softmax(-a, -b)

def softrank(a, b):
    """Return a,b in 'soft-sorted' order, with the smaller value first"""
    return softmin(a,b), softmax(a,b)

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
    for layer in range(1, layers+1):
        # we have 1..layer sub layers
        for sub in reversed(range(1, layer+1)):
            l, r = np.zeros((n//2, n)), np.zeros((n//2, n))            
            map_l, map_r = np.zeros((n, n//2)), np.zeros((n, n//2))                        
            out = 0 
            for i in range(0,n,2**sub):
                for j in range(2**(sub-1)):
                    ix = i + j
                    a, b = ix, ix+(2**(sub-1))                    
                    l[out, a] = 1
                    r[out, b] = 1
                    if (ix >> layer) & 1:                                            
                        a, b = b,a                                                            
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
        x = map_l @ np.minimum(a,b) + map_r @ np.maximum(a,b)        
    return x

def diff_bisort(matrices, x):    
    """
    Approximate differentiable sort. Takes a set of bitonic sort matrices generated by bitonic_matrices(n), sort 
    a sequence x of length n. Values may be distorted slightly but will be ordered.
    """  
    for l, r, map_l, map_r in matrices:
        a, b = softrank(l @ x, r @ x)        
        x = map_l @ a + map_r @ b
    return x

def softmax_smooth(a, b, smooth=0):
    """The smoothed softmaximum of softmax(a,b) = log(e^a + a^b).
    With smooth=0.0, is softmax; with smooth=1.0, averages a and b"""
    t = smooth / 2.0
    return np.log(np.exp((1-t) * a + b * t) + np.exp((1-t)*b + t *a) ) - np.log(1+smooth)

def softrank_smooth(a, b, smooth=0):
    """The smoothed compare and swap of a and b
    With smooth=0, if softrank; with smooth=1.0, geometrically averages a and b"""
    return -softmax_smooth(-a, -b, smooth), softmax_smooth(a, b, smooth)

def diff_bisort_smooth(matrices, x, smooth=0):
    """
    Approximate differentiable sort. Takes a set of bitonic sort matrices generated by bitonic_matrices(n), sort 
    a sequence x of length n. Values will be distorted slightly but will be ordered.
    """
    for l, r, map_l, map_r in matrices:
        a, b = softrank_smooth (l @ x, r @ x, smooth)
        x = map_l @ a + map_r @ b
    return x    