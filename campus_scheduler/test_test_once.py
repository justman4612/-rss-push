from unittest import TestCase, main
from unittest.mock import patch
import dispatch
import test_once


class OneEmailTests(TestCase):
    def test_accepts_exactly_one(self):
        with patch.object(dispatch, "dispatch", return_value={"claimed": 1, "sent": 1, "failed": 0}) as call, patch.object(dispatch, "report"):
            self.assertEqual(test_once.main(), 0)
            call.assert_called_once()

    def test_zero_or_multiple_is_not_test_success(self):
        for n in (0, 2):
            with patch.object(dispatch, "dispatch", return_value={"claimed": n, "sent": n, "failed": 0}) as call, patch.object(dispatch, "report"):
                self.assertEqual(test_once.main(), 1)
                call.assert_called_once()

    def test_uncertain_result_not_retried(self):
        with patch.object(dispatch, "dispatch", side_effect=dispatch.DispatchError("Uncertain send")) as call, patch.object(dispatch, "report"):
            self.assertEqual(test_once.main(), 1)
            call.assert_called_once()


if __name__ == "__main__":
    main()
