#!/usr/bin/env python3

import debugpy
import runpy
import sys

debugpy.listen(("0.0.0.0", 5678))

mod_arg = sys.argv.index("-m") + 1
mod_name = sys.argv[mod_arg]

sys.argv = [mod_name] + sys.argv[mod_arg + 1:]
runpy.run_module(mod_name=mod_name, run_name="__main__", alter_sys=True)
