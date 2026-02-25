import unittest

from server.core.naming import slugify_student, slugify_submission


class NamingTests(unittest.TestCase):
    def test_student_slug(self):
        self.assertEqual(slugify_student("  Smith Jr "), "smith-jr")

    def test_submission_slug(self):
        self.assertEqual(slugify_submission("Lab 01_Blink!"), "lab-01_blink")

    def test_reserved_rejected(self):
        with self.assertRaises(ValueError):
            slugify_student("CON")


if __name__ == "__main__":
    unittest.main()
