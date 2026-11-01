import unittest
from scripts.install_boot_start import cron_content,BEGIN,END


class BootTests(unittest.TestCase):
    def test_preserves_existing_jobs_and_reinstall_does_not_duplicate(self):
        previous='MAILTO=""\n# an existing job\n7 * * * * /usr/bin/true\n'
        command='@reboot /bin/sh /home/orin/patrol-prototype/start_at_boot.sh'
        first=cron_content(previous,command)
        self.assertIn(previous,first)
        self.assertEqual(cron_content(first,command),first)
        self.assertEqual(first.count(BEGIN),1)
        removed=cron_content(first)
        self.assertNotIn(command,removed);self.assertIn(previous,removed)

    def test_refuses_broken_blocks(self):
        for text in (BEGIN+'\n',END+'\n',BEGIN+'\n'+BEGIN+'\n'+END):
            with self.assertRaises(ValueError):cron_content(text,'@reboot true')


if __name__=='__main__':unittest.main()
