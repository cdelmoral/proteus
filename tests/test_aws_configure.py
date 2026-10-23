"""Exercise AWS configuration through the real configuration command."""
import unittest
import test_configure
from test_aws_enroll import VALUES


class AWSConfigureTest(unittest.TestCase):
    setUp = test_configure.ConfigureTest.setUp
    configure = test_configure.ConfigureTest.configure

    def answers(self, enabled='true', values=VALUES):
        return 'op://vault/github/token\nop://vault/signing/private key\n\n' + enabled + '\n' + '\n'.join(values) + '\n'

    def test_complete_configuration_keeps_answers_and_unrelated_values(self):
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text('unrelated=keep\n')
        result = self.configure(self.answers())
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = self.configuration.read_bytes()
        self.assertIn(b'unrelated=keep\n', saved)
        self.assertIn(b'proteus_aws_enabled=true\n', saved)
        result = self.configure('\n' * 11)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.configuration.read_bytes(), saved)
        result = self.configure('\n\n\nfalse\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'proteus_aws_enabled=false\n', self.configuration.read_bytes())
        self.assertIn(VALUES[-1], self.configuration.read_text())

    def test_rejects_partial_malformed_and_inconsistent_groups_without_saving(self):
        for index, value in ((0, ''), (0, '123'), (1, VALUES[1].replace('123456789012', '999999999999')),
                             (1, VALUES[1] + '/'), (2, 'not a region'), (3, VALUES[3].replace('us-east-1', 'us-west-2')),
                             (4, 'arn:bad'), (5, 'not a reference'), (6, VALUES[5])):
            with self.subTest(index=index, value=value):
                values = VALUES.copy()
                values[index] = value
                result = self.configure(self.answers(values=values))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.configuration.exists())
        self.assertNotEqual(self.configure(self.answers(enabled='yes')).returncode, 0)
        self.assertFalse(self.configuration.exists())

    def test_invalid_edit_preserves_complete_previous_config(self):
        self.assertEqual(self.configure(self.answers()).returncode, 0)
        original = self.configuration.read_bytes()
        self.assertNotEqual(self.configure('\n\n\ntrue\ninvalid\n').returncode, 0)
        self.assertEqual(self.configuration.read_bytes(), original)
