"""Test package.

Redirects user-level state to a temporary directory for the whole run.

`UserStore` defaults to `~/.loopforge`, which holds provider credentials. A
test that reached it would be editing the machine it runs on -- and one did:
the Agent resolves the approver from that store when a caller supplies none,
so any test exercising an approval created a database in the developer's home
directory. It was empty, and it should not have existed.

Set `LOOPFORGE_HOME` yourself to point a run at a specific store; this only
fills in the gap.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

if not os.environ.get("LOOPFORGE_HOME"):
    _home = tempfile.mkdtemp(prefix="loopforge-test-home-")
    os.environ["LOOPFORGE_HOME"] = _home
    atexit.register(shutil.rmtree, _home, ignore_errors=True)
