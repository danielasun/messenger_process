# MessengerProcess

Small lightweight utility classes for interprocess communication. 

Primary use case is initializing long running processes that should exit when the main process finishes as well as 
signaling when cpu-intensive calculations are complete.

Requirements: None but uses `numpy` and `matplotlib` for some of the unittests.

Unittests: `python -m unittest tests.py` from source root.