# Binary search (source snippet)

Binary search finds a target value in a sorted array by repeatedly comparing it with the middle element
of the remaining interval. If the target is smaller than the middle element, the search continues in the
left half; if it is larger, in the right half. Each comparison discards half of the remaining candidates,
so after k comparisons at most n / 2^k candidates remain. The search therefore needs about log2(n)
comparisons: for one million elements, at most 20, whereas a linear scan may need a million.
