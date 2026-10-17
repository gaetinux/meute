"""Test configuration: hypothesis profiles chosen by `HYPOTHESIS_PROFILE`."""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=1000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
