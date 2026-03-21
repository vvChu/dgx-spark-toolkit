import torch

try:
    x = torch.zeros(31, 224, 6)
    x[31, 10] = 5
except Exception as e:
    print("TEST 1:", repr(e))

try:
    x = torch.zeros(31, 224, 6)
    x[10, 224] = 5
except Exception as e:
    print("TEST 2:", repr(e))

try:
    x = torch.zeros(31, 224, 6)
    x[31] = 5
except Exception as e:
    print("TEST 3:", repr(e))
