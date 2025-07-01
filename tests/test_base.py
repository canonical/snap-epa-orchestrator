# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import tempfile
import unittest


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["TEST_TMPDIR"] = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
