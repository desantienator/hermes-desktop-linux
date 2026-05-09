import json
import tempfile
import unittest
from pathlib import Path
from hermes_desktop_linux.models import ConnectionProfile, ProfileStore
from hermes_desktop_linux.remote import SSHClient

class CoreTests(unittest.TestCase):
    def test_profile_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'connections.json'
            store = ProfileStore(path)
            profiles = [ConnectionProfile(name='bob', host='example.test', user='adrian', port=2222, hermes_home='~/.hermes-test', ssh_alias='bobbox')]
            store.save(profiles)
            loaded = store.load()
            self.assertEqual(loaded, profiles)
            self.assertEqual(json.loads(path.read_text())[0]['name'], 'bob')

    def test_local_overview_runs(self):
        client = SSHClient(ConnectionProfile(name='local', host='localhost'))
        res = client.run_action('overview')
        self.assertTrue(res.ok, res.error)
        self.assertIn('host', res.data)
        self.assertIn('python', res.data)

    def test_local_files_runs(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'x.txt').write_text('hello')
            client = SSHClient(ConnectionProfile(name='local', host='localhost'))
            res = client.run_action('files', d)
            self.assertTrue(res.ok, res.error)
            self.assertTrue(any(item['name'] == 'x.txt' for item in res.data))

if __name__ == '__main__':
    unittest.main()
