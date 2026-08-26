import unittest
from counter import increment

class TestCounter(unittest.TestCase):
    def test_increment_existing_behavior(self):
        self.assertEqual(increment(1), 2)
        self.assertEqual(increment(-1), 0)

if __name__ == '__main__':
    unittest.main()
