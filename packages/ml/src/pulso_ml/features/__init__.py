"""Point-in-time feature store (vault Intelligence/Feature Store & Leakage Test, DEC-275).

Only `repository` touches tables; feature code gets an `AsOf(cutoff)` and pure inputs.
"""
